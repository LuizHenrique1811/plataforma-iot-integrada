"""Regras, estado das regras e alarmes sobre PostgreSQL."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from adaptadores.postgres.repositorios import _listar
from dominio.erros import JaExiste
from dominio.paginacao import Ordenacao, Pagina, ParametrosDePagina
from dominio.regras import (
    Alarme,
    EstadoAlarme,
    EstadoDaRegra,
    Regra,
    Severidade,
    regra_de_dict,
    regra_para_dict,
)

_FILTRO_DISPOSITIVO = {"dispositivo": "d.id", "dominio": "d.dominio_id", "site": "d.site_id", "area": "d.area_id"}
_COLUNAS_ALARME = (
    "id, inquilino_id, regra_id, dispositivo_id, severidade, estado, ocorrido_em, mensagem, origem,"
    " reconhecido_em, resolvido_em, id_mensagem"
)


def _regra(linha: tuple) -> Regra:
    definicao, criado_em = linha
    regra = regra_de_dict(definicao)
    return Regra(regra.id, regra.nome, regra.condicao, regra.acoes, regra.ambito, regra.ativa, criado_em)


def _alarme(linha: tuple) -> Alarme:
    (identificador, inquilino, regra, dispositivo, severidade, estado, ocorrido_em, mensagem, origem,
     reconhecido_em, resolvido_em, id_mensagem) = linha  # fmt: skip
    return Alarme(
        str(identificador), inquilino, regra, dispositivo, Severidade(severidade), EstadoAlarme(estado), ocorrido_em,
        mensagem, origem, reconhecido_em, resolvido_em, str(id_mensagem) if id_mensagem else None,
    )  # fmt: skip


class RegrasPostgres:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def inserir_regra(self, inquilino: str, regra: Regra) -> None:
        try:
            with self._pool.connection() as conexao:
                conexao.execute(
                    "INSERT INTO regras (inquilino_id, id, nome, ambito, ativa, definicao, criado_em)"
                    " VALUES (%s, %s, %s, %s, %s, %s, COALESCE(%s, now()))",
                    (inquilino, regra.id, regra.nome, regra.ambito, regra.ativa, Jsonb(regra_para_dict(regra)),
                     regra.criado_em),
                )  # fmt: skip
        except UniqueViolation as erro:
            raise JaExiste("Já existe regra com esse identificador.") from erro

    def listar_regras(self, inquilino: str, pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Regra]:
        with self._pool.connection() as conexao:
            return _listar(
                conexao, "SELECT definicao, criado_em, id, nome FROM regras WHERE inquilino_id = %s", (inquilino,),
                pagina, ordenacao, {"id": "id", "nome": "nome", "criado_em": "criado_em"},
                lambda linha: _regra(linha[:2]),
            )  # fmt: skip

    def regras_ativas(self, inquilino: str, ambito: str) -> list[Regra]:
        with self._pool.connection() as conexao:
            linhas = conexao.execute(
                "SELECT definicao, criado_em FROM regras WHERE inquilino_id = %s AND ambito = %s AND ativa ORDER BY id",
                (inquilino, ambito),
            ).fetchall()
        return [_regra(linha) for linha in linhas]

    def regras_de_ausencia(self, ambito: str) -> list[tuple[str, Regra]]:
        with self._pool.connection() as conexao:
            linhas = conexao.execute(
                "SELECT inquilino_id, definicao, criado_em FROM regras"
                " WHERE ambito = %s AND ativa AND definicao->'condicao'->>'tipo' = 'ausencia'"
                " ORDER BY inquilino_id, id",
                (ambito,),
            ).fetchall()
        return [(linha[0], _regra(linha[1:])) for linha in linhas]

    def obter_estado(self, inquilino: str, regra: str, dispositivo: str) -> EstadoDaRegra | None:
        with self._pool.connection() as conexao:
            linha = conexao.execute(
                "SELECT condicao_ativa, desde, disparada FROM estado_regras"
                " WHERE inquilino_id = %s AND regra_id = %s AND dispositivo_id = %s",
                (inquilino, regra, dispositivo),
            ).fetchone()
        return EstadoDaRegra(*linha) if linha else None

    def salvar_estado(self, inquilino: str, regra: str, dispositivo: str, estado: EstadoDaRegra) -> None:
        with self._pool.connection() as conexao:
            conexao.execute(
                "INSERT INTO estado_regras (inquilino_id, regra_id, dispositivo_id, condicao_ativa, desde, disparada)"
                " VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (inquilino_id, regra_id, dispositivo_id) DO UPDATE SET"
                " condicao_ativa = EXCLUDED.condicao_ativa, desde = EXCLUDED.desde, disparada = EXCLUDED.disparada,"
                " atualizado_em = now()",
                (inquilino, regra, dispositivo, estado.condicao_ativa, estado.desde, estado.disparada),
            )

    def ultimas_leituras(
        self, inquilino: str, filtros: dict[str, str], grandeza: str
    ) -> list[tuple[str, datetime | None]]:
        condicoes = ["d.inquilino_id = %s", "d.revogado_em IS NULL"]
        condicoes += [f"{_FILTRO_DISPOSITIVO[campo]} = %s" for campo in filtros]
        with self._pool.connection() as conexao:
            linhas = conexao.execute(
                "SELECT d.id, COALESCE(u.medido_em, d.criado_em) FROM dispositivos d"
                " LEFT JOIN ultimo_estado u ON u.inquilino_id = d.inquilino_id AND u.dispositivo_id = d.id"
                f" AND u.grandeza = %s WHERE {' AND '.join(condicoes)} ORDER BY d.id",
                (grandeza, inquilino, *filtros.values()),
            ).fetchall()
        return [(linha[0], linha[1]) for linha in linhas]


class AlarmesPostgres:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def inserir_alarme(self, alarme: Alarme) -> bool:
        with self._pool.connection() as conexao:
            # O índice único parcial impede um segundo alarme aberto da mesma regra e dispositivo.
            inseridos = conexao.execute(
                f"INSERT INTO alarmes ({_COLUNAS_ALARME}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT DO NOTHING",
                (
                    uuid.UUID(alarme.id), alarme.inquilino, alarme.regra, alarme.dispositivo, alarme.severidade.value,
                    alarme.estado.value, alarme.ocorrido_em, alarme.mensagem, alarme.origem, alarme.reconhecido_em,
                    alarme.resolvido_em, uuid.UUID(alarme.id_mensagem) if alarme.id_mensagem else None,
                ),
            ).rowcount  # fmt: skip
        return inseridos > 0

    def obter_alarme(self, inquilino: str, alarme: str) -> Alarme | None:
        try:
            identificador = uuid.UUID(alarme)
        except ValueError:
            return None
        with self._pool.connection() as conexao:
            linha = conexao.execute(
                f"SELECT {_COLUNAS_ALARME} FROM alarmes WHERE inquilino_id = %s AND id = %s", (inquilino, identificador)
            ).fetchone()
        return _alarme(linha) if linha else None

    def atualizar_alarme(self, alarme: Alarme) -> None:
        with self._pool.connection() as conexao:
            conexao.execute(
                "UPDATE alarmes SET estado = %s, reconhecido_em = %s, resolvido_em = %s WHERE id = %s",
                (alarme.estado.value, alarme.reconhecido_em, alarme.resolvido_em, uuid.UUID(alarme.id)),
            )

    def resolver_abertos(self, inquilino: str, regra: str, dispositivo: str, quando: datetime) -> int:
        with self._pool.connection() as conexao:
            return conexao.execute(
                "UPDATE alarmes SET estado = 'resolvido', resolvido_em = %s WHERE inquilino_id = %s AND regra_id = %s"
                " AND dispositivo_id = %s AND estado <> 'resolvido' AND origem <> 'borda'",
                (quando, inquilino, regra, dispositivo),
            ).rowcount

    def listar_alarmes(
        self, inquilino: str, filtros: dict[str, Any], pagina: ParametrosDePagina, ordenacao: Ordenacao
    ) -> Pagina[Alarme]:
        colunas = {"estado": "estado", "severidade": "severidade"}
        condicoes = ["inquilino_id = %s"] + [f"{colunas[campo]} = %s" for campo in filtros]
        with self._pool.connection() as conexao:
            return _listar(
                conexao, f"SELECT {_COLUNAS_ALARME} FROM alarmes WHERE {' AND '.join(condicoes)}",
                (inquilino, *(str(valor) for valor in filtros.values())), pagina, ordenacao,
                {"ocorrido_em": "ocorrido_em", "severidade": "severidade", "estado": "estado"}, _alarme,
            )  # fmt: skip
