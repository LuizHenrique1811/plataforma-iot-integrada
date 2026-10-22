"""Catálogo, ingestão, consultas, DLQ e autenticação sobre PostgreSQL + TimescaleDB.

Todas as consultas filtram pelo inquilino da credencial (RF-SEG-03).
"""

from __future__ import annotations

import hmac
import json
import uuid
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from adaptadores.credenciais import hash_segredo
from dominio.catalogo import Area, ChaveDeApi, Dominio, Inquilino, Site
from dominio.consultas import Contato, MedicaoConsultada, RejeitadaConsultada
from dominio.erros import JaExiste
from dominio.modelos import (
    DispositivoCadastrado,
    GrandezaDoPerfil,
    Medida,
    MensagemAceita,
    MensagemRejeitada,
    Origem,
    Perfil,
    TipoOrigem,
)
from dominio.paginacao import Ordenacao, Pagina, ParametrosDePagina

_COLUNAS_DISPOSITIVO = (
    "inquilino_id, id, perfil_id, dominio_id, site_id, area_id, revogado_em, fabricante, firmware, criado_em"
)
# Campo de ordenação do domínio -> coluna. A lista fechada também impede SQL injetado no ORDER BY.
_ORDEM_PADRAO = {"id": "id", "nome": "nome", "criado_em": "criado_em"}
_ORDEM_DISPOSITIVO = {
    "id": "id",
    "criado_em": "criado_em",
    "perfil": "perfil_id",
    "dominio": "dominio_id",
    "site": "site_id",
}
_FILTRO_DISPOSITIVO = {"dominio": "dominio_id", "perfil": "perfil_id", "site": "site_id", "area": "area_id"}


def _listar(
    conexao: Connection,
    sql: str,
    parametros: Sequence[Any],
    pagina: ParametrosDePagina,
    ordenacao: Ordenacao,
    colunas: dict[str, str],
    construir: Callable[[tuple], Any],
) -> Pagina[Any]:
    total = conexao.execute(f"SELECT count(*) FROM ({sql}) AS consulta", parametros).fetchone()[0]
    direcao = "DESC" if ordenacao.decrescente else "ASC"
    linhas = conexao.execute(
        f"{sql} ORDER BY {colunas[ordenacao.campo]} {direcao} LIMIT %s OFFSET %s",
        (*parametros, pagina.tamanho, pagina.deslocamento),
    ).fetchall()
    return Pagina(tuple(construir(linha) for linha in linhas), pagina.pagina, pagina.tamanho, total)


def _perfil(linha: tuple) -> Perfil:
    grandezas = {
        item["grandeza"]: GrandezaDoPerfil(item["grandeza"], item["unidade"], item.get("minimo"), item.get("maximo"))
        for item in linha[2]
    }
    return Perfil(linha[0], linha[1], grandezas, linha[3])


class CatalogoPostgres:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    # Catalogo -------------------------------------------------------------------------------

    def obter_dispositivo(self, inquilino: str, dispositivo: str) -> DispositivoCadastrado | None:
        with self._pool.connection() as conexao:
            linha = conexao.execute(
                f"SELECT {_COLUNAS_DISPOSITIVO} FROM dispositivos WHERE inquilino_id = %s AND id = %s",
                (inquilino, dispositivo),
            ).fetchone()
        return DispositivoCadastrado(*linha) if linha else None

    def obter_perfil(self, inquilino: str, perfil: str) -> Perfil | None:
        with self._pool.connection() as conexao:
            linha = conexao.execute(
                "SELECT id, nome, grandezas, intervalo_envio_s FROM perfis WHERE inquilino_id = %s AND id = %s",
                (inquilino, perfil),
            ).fetchone()
        return _perfil(linha) if linha else None

    # RepositorioDeCatalogo ------------------------------------------------------------------

    def existe_inquilino(self, inquilino: str) -> bool:
        return self._existe("SELECT 1 FROM inquilinos WHERE id = %s", (inquilino,))

    def inserir_inquilino(self, inquilino: Inquilino) -> None:
        self._inserir(
            "INSERT INTO inquilinos (id, nome, criado_em) VALUES (%s, %s, %s)",
            (inquilino.id, inquilino.nome, inquilino.criado_em),
            "inquilino",
        )

    def listar_inquilinos(self, pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Inquilino]:
        with self._pool.connection() as conexao:
            return _listar(
                conexao,
                "SELECT id, nome, criado_em FROM inquilinos",
                (),
                pagina,
                ordenacao,
                _ORDEM_PADRAO,
                lambda linha: Inquilino(*linha),
            )

    def inserir_chave(self, chave: ChaveDeApi, hash_segredo: str) -> None:
        self._inserir(
            "INSERT INTO chaves_api (id, inquilino_id, papel, hash, descricao, criado_em)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (chave.id, chave.inquilino, chave.papel, hash_segredo, chave.descricao, chave.criado_em),
            "chave",
        )

    def existe_dominio(self, inquilino: str, dominio: str) -> bool:
        return self._existe("SELECT 1 FROM dominios WHERE inquilino_id = %s AND id = %s", (inquilino, dominio))

    def inserir_dominio(self, inquilino: str, dominio: Dominio) -> None:
        self._inserir(
            "INSERT INTO dominios (inquilino_id, id, nome, descricao, criado_em) VALUES (%s, %s, %s, %s, %s)",
            (inquilino, dominio.id, dominio.nome, dominio.descricao, dominio.criado_em),
            "domínio",
        )

    def listar_dominios(self, inquilino: str, pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Dominio]:
        with self._pool.connection() as conexao:
            return _listar(
                conexao,
                "SELECT id, nome, descricao, criado_em FROM dominios WHERE inquilino_id = %s",
                (inquilino,),
                pagina,
                ordenacao,
                _ORDEM_PADRAO,
                lambda linha: Dominio(*linha),
            )

    def inserir_perfil(self, inquilino: str, perfil: Perfil, criado_em: datetime) -> None:
        grandezas = [
            {"grandeza": item.grandeza, "unidade": item.unidade, "minimo": item.minimo, "maximo": item.maximo}
            for item in perfil.grandezas.values()
        ]
        self._inserir(
            "INSERT INTO perfis (inquilino_id, id, nome, grandezas, intervalo_envio_s, criado_em)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (inquilino, perfil.id, perfil.nome, Jsonb(grandezas), perfil.intervalo_envio_s, criado_em),
            "perfil",
        )

    def listar_perfis(self, inquilino: str, pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Perfil]:
        with self._pool.connection() as conexao:
            return _listar(
                conexao,
                "SELECT id, nome, grandezas, intervalo_envio_s FROM perfis WHERE inquilino_id = %s",
                (inquilino,),
                pagina,
                ordenacao,
                _ORDEM_PADRAO,
                _perfil,
            )

    def existe_site(self, inquilino: str, site: str) -> bool:
        return self._existe("SELECT 1 FROM sites WHERE inquilino_id = %s AND id = %s", (inquilino, site))

    def inserir_site(self, inquilino: str, site: Site) -> None:
        self._inserir(
            "INSERT INTO sites (inquilino_id, id, nome, geo, criado_em) VALUES (%s, %s, %s, %s, %s)",
            (inquilino, site.id, site.nome, Jsonb(site.geo) if site.geo else None, site.criado_em),
            "local",
        )

    def listar_sites(self, inquilino: str, pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Site]:
        with self._pool.connection() as conexao:
            return _listar(
                conexao,
                "SELECT id, nome, geo, criado_em FROM sites WHERE inquilino_id = %s",
                (inquilino,),
                pagina,
                ordenacao,
                _ORDEM_PADRAO,
                lambda linha: Site(*linha),
            )

    def existe_area(self, inquilino: str, site: str, area: str) -> bool:
        return self._existe(
            "SELECT 1 FROM areas WHERE inquilino_id = %s AND site_id = %s AND id = %s", (inquilino, site, area)
        )

    def inserir_area(self, inquilino: str, area: Area) -> None:
        self._inserir(
            "INSERT INTO areas (inquilino_id, site_id, id, nome, geo, criado_em) VALUES (%s, %s, %s, %s, %s, %s)",
            (inquilino, area.site, area.id, area.nome, Jsonb(area.geo) if area.geo else None, area.criado_em),
            "área",
        )

    def listar_areas(self, inquilino: str, site: str, pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Area]:
        with self._pool.connection() as conexao:
            return _listar(
                conexao,
                "SELECT id, site_id, nome, geo, criado_em FROM areas WHERE inquilino_id = %s AND site_id = %s",
                (inquilino, site),
                pagina,
                ordenacao,
                _ORDEM_PADRAO,
                lambda linha: Area(*linha),
            )

    def inserir_dispositivo(self, dispositivo: DispositivoCadastrado, hash_token: str) -> None:
        self._inserir(
            "INSERT INTO dispositivos (inquilino_id, id, perfil_id, dominio_id, site_id, area_id, fabricante, firmware,"
            " token_hash, criado_em) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                dispositivo.inquilino,
                dispositivo.id,
                dispositivo.perfil,
                dispositivo.dominio,
                dispositivo.site,
                dispositivo.area,
                dispositivo.fabricante,
                dispositivo.firmware,
                hash_token,
                dispositivo.criado_em,
            ),
            "dispositivo",
        )

    def listar_dispositivos(
        self, inquilino: str, filtros: dict[str, str], pagina: ParametrosDePagina, ordenacao: Ordenacao
    ) -> Pagina[DispositivoCadastrado]:
        condicoes = ["inquilino_id = %s"] + [f"{_FILTRO_DISPOSITIVO[campo]} = %s" for campo in filtros]
        with self._pool.connection() as conexao:
            return _listar(
                conexao,
                f"SELECT {_COLUNAS_DISPOSITIVO} FROM dispositivos WHERE {' AND '.join(condicoes)}",
                (inquilino, *filtros.values()),
                pagina,
                ordenacao,
                _ORDEM_DISPOSITIVO,
                lambda linha: DispositivoCadastrado(*linha),
            )

    def revogar_credencial(self, inquilino: str, dispositivo: str, quando: datetime) -> bool:
        with self._pool.connection() as conexao:
            alteradas = conexao.execute(
                "UPDATE dispositivos SET revogado_em = COALESCE(revogado_em, %s), token_hash = NULL"
                " WHERE inquilino_id = %s AND id = %s",
                (quando, inquilino, dispositivo),
            ).rowcount
        return alteradas > 0

    def _existe(self, sql: str, parametros: tuple) -> bool:
        with self._pool.connection() as conexao:
            return conexao.execute(sql, parametros).fetchone() is not None

    def _inserir(self, sql: str, parametros: tuple, descricao: str) -> None:
        try:
            with self._pool.connection() as conexao:
                conexao.execute(sql, parametros)
        except UniqueViolation as erro:
            raise JaExiste(f"Já existe {descricao} com esse identificador.") from erro


class RepositorioDeIngestaoPostgres:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def ja_recebida(self, id_mensagem: str) -> bool:
        with self._pool.connection() as conexao:
            return (
                conexao.execute(
                    "SELECT 1 FROM mensagens_recebidas WHERE id_mensagem = %s", (uuid.UUID(id_mensagem),)
                ).fetchone()
                is not None
            )

    def persistir(self, mensagem: MensagemAceita) -> bool:
        id_mensagem = uuid.UUID(mensagem.id_mensagem)
        with self._pool.connection() as conexao, conexao.transaction():
            inseridas = conexao.execute(
                "INSERT INTO mensagens_recebidas (id_mensagem, inquilino_id, recebido_em)"
                " VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (id_mensagem, mensagem.inquilino, mensagem.recebido_em),
            ).rowcount
            if inseridas == 0:
                return False
            with conexao.cursor() as cursor:
                if mensagem.medidas:
                    cursor.executemany(
                        "INSERT INTO medicoes (medido_em, inquilino_id, dispositivo_id, grandeza, valor, valor_texto,"
                        " unidade, suspeita, id_mensagem, dominio_id, site_id, area_id, via, origem_timestamp,"
                        " recebido_em) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        [
                            (
                                mensagem.timestamp,
                                mensagem.inquilino,
                                mensagem.dispositivo,
                                medida.grandeza,
                                *_valores(medida),
                                medida.unidade,
                                medida.suspeita,
                                id_mensagem,
                                mensagem.dominio,
                                mensagem.site,
                                mensagem.area,
                                mensagem.via,
                                mensagem.origem_timestamp,
                                mensagem.recebido_em,
                            )
                            for medida in mensagem.medidas
                        ],
                    )
                    # Dado atrasado não sobrescreve o último estado (ADR-0017).
                    cursor.executemany(
                        "INSERT INTO ultimo_estado (inquilino_id, dispositivo_id, grandeza, valor, valor_texto,"
                        " unidade, suspeita, medido_em, id_mensagem) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                        " ON CONFLICT (inquilino_id, dispositivo_id, grandeza) DO UPDATE SET"
                        " valor = EXCLUDED.valor, valor_texto = EXCLUDED.valor_texto, unidade = EXCLUDED.unidade,"
                        " suspeita = EXCLUDED.suspeita, medido_em = EXCLUDED.medido_em,"
                        " id_mensagem = EXCLUDED.id_mensagem"
                        " WHERE ultimo_estado.medido_em < EXCLUDED.medido_em",
                        [
                            (
                                mensagem.inquilino,
                                mensagem.dispositivo,
                                medida.grandeza,
                                *_valores(medida),
                                medida.unidade,
                                medida.suspeita,
                                mensagem.timestamp,
                                id_mensagem,
                            )
                            for medida in mensagem.medidas
                        ],
                    )
                if mensagem.tipo in ("evento", "estado"):
                    evento = mensagem.evento or {}
                    cursor.execute(
                        "INSERT INTO eventos (ocorrido_em, inquilino_id, dispositivo_id, tipo, nome, severidade,"
                        " dados, id_mensagem, via, recebido_em) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            mensagem.timestamp,
                            mensagem.inquilino,
                            mensagem.dispositivo,
                            mensagem.tipo,
                            evento.get("nome"),
                            evento.get("severidade"),
                            Jsonb(evento.get("detalhes") if mensagem.tipo == "evento" else mensagem.estado),
                            id_mensagem,
                            mensagem.via,
                            mensagem.recebido_em,
                        ),
                    )
                # Último contato (ADR-0010): também só avança com medição mais nova.
                cursor.execute(
                    "INSERT INTO ultimo_contato (inquilino_id, dispositivo_id, medido_em, recebido_em, via)"
                    " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (inquilino_id, dispositivo_id) DO UPDATE SET"
                    " medido_em = EXCLUDED.medido_em, recebido_em = EXCLUDED.recebido_em, via = EXCLUDED.via"
                    " WHERE ultimo_contato.medido_em < EXCLUDED.medido_em",
                    (mensagem.inquilino, mensagem.dispositivo, mensagem.timestamp, mensagem.recebido_em, mensagem.via),
                )
                if mensagem.via:
                    cursor.execute(
                        "INSERT INTO contato_da_borda (inquilino_id, via, recebido_em) VALUES (%s, %s, %s)"
                        " ON CONFLICT (inquilino_id, via) DO UPDATE SET"
                        " recebido_em = GREATEST(contato_da_borda.recebido_em, EXCLUDED.recebido_em)",
                        (mensagem.inquilino, mensagem.via, mensagem.recebido_em),
                    )
        return True


class ConsultasPostgres:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def medicoes(
        self,
        inquilino: str,
        dispositivo: str,
        grandeza: str | None,
        inicio: datetime | None,
        fim: datetime | None,
        pagina: ParametrosDePagina,
        ordenacao: Ordenacao,
    ) -> Pagina[MedicaoConsultada]:
        condicoes = ["inquilino_id = %s", "dispositivo_id = %s"]
        parametros: list[Any] = [inquilino, dispositivo]
        for condicao, valor in (("grandeza = %s", grandeza), ("medido_em >= %s", inicio), ("medido_em < %s", fim)):
            if valor is not None:
                condicoes.append(condicao)
                parametros.append(valor)
        sql = (
            "SELECT medido_em, grandeza, valor, valor_texto, unidade, suspeita, id_mensagem, via"
            f" FROM medicoes WHERE {' AND '.join(condicoes)}"
        )
        with self._pool.connection() as conexao:
            return _listar(conexao, sql, parametros, pagina, ordenacao, {"timestamp": "medido_em"}, _medicao_consultada)

    def ultimo_estado(self, inquilino: str, dispositivo: str) -> list[MedicaoConsultada]:
        with self._pool.connection() as conexao:
            linhas = conexao.execute(
                "SELECT medido_em, grandeza, valor, valor_texto, unidade, suspeita, id_mensagem, NULL"
                " FROM ultimo_estado WHERE inquilino_id = %s AND dispositivo_id = %s ORDER BY grandeza",
                (inquilino, dispositivo),
            ).fetchall()
        return [_medicao_consultada(linha) for linha in linhas]

    def ultimo_contato(self, inquilino: str, dispositivo: str) -> Contato | None:
        with self._pool.connection() as conexao:
            linha = conexao.execute(
                "SELECT medido_em, via FROM ultimo_contato WHERE inquilino_id = %s AND dispositivo_id = %s",
                (inquilino, dispositivo),
            ).fetchone()
        return Contato(*linha) if linha else None

    def contato_da_borda(self, inquilino: str, via: str) -> datetime | None:
        with self._pool.connection() as conexao:
            linha = conexao.execute(
                "SELECT recebido_em FROM contato_da_borda WHERE inquilino_id = %s AND via = %s", (inquilino, via)
            ).fetchone()
        return linha[0] if linha else None

    def rejeitadas(
        self, inquilino: str, pagina: ParametrosDePagina, ordenacao: Ordenacao
    ) -> Pagina[RejeitadaConsultada]:
        with self._pool.connection() as conexao:
            return _listar(
                conexao,
                "SELECT id, recebido_em, etapa, motivo, erros, origem, COALESCE(carga, to_jsonb(carga_texto))"
                " FROM rejeitadas WHERE inquilino_id = %s",
                (inquilino,),
                pagina,
                ordenacao,
                {"recebido_em": "recebido_em"},
                lambda linha: RejeitadaConsultada(
                    linha[0], linha[1], linha[2], linha[3], tuple(linha[4]), linha[5], linha[6]
                ),
            )


def _medicao_consultada(linha: tuple) -> MedicaoConsultada:
    medido_em, grandeza, valor, valor_texto, unidade, suspeita, id_mensagem, via = linha
    if valor_texto in ("true", "false"):
        valor = valor_texto == "true"
    elif valor_texto is not None:
        valor = valor_texto
    return MedicaoConsultada(medido_em, grandeza, valor, unidade, suspeita, str(id_mensagem), via)


class FilaDeRejeitadasPostgres:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def registrar(self, rejeitada: MensagemRejeitada) -> None:
        carga_json, carga_texto = _separar_carga(rejeitada.carga)
        with self._pool.connection() as conexao:
            conexao.execute(
                "INSERT INTO rejeitadas (recebido_em, inquilino_id, etapa, motivo, erros, carga, carga_texto, origem)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    rejeitada.recebido_em,
                    rejeitada.inquilino,
                    rejeitada.etapa.value,
                    rejeitada.motivo.value,
                    Jsonb([{"caminho": erro.caminho, "mensagem": erro.mensagem} for erro in rejeitada.erros]),
                    carga_json,
                    carga_texto,
                    rejeitada.origem,
                ),
            )


class AutenticadorPostgres:
    def __init__(self, pool: ConnectionPool, chave_admin: str | None = None) -> None:
        self._pool = pool
        self._chave_admin = chave_admin

    def por_token_dispositivo(self, token: str) -> Origem | None:
        with self._pool.connection() as conexao:
            linha = conexao.execute(
                "SELECT inquilino_id, id FROM dispositivos WHERE token_hash = %s AND revogado_em IS NULL",
                (hash_segredo(token),),
            ).fetchone()
        return Origem(TipoOrigem.DISPOSITIVO, inquilino=linha[0], dispositivo=linha[1]) if linha else None

    def por_chave(self, chave: str) -> Origem | None:
        if self._chave_admin and hmac.compare_digest(chave, self._chave_admin):
            return Origem(TipoOrigem.CHAVE, inquilino=None, papel="administrador")
        with self._pool.connection() as conexao:
            linha = conexao.execute(
                "SELECT inquilino_id, papel FROM chaves_api WHERE hash = %s AND revogado_em IS NULL",
                (hash_segredo(chave),),
            ).fetchone()
        return Origem(TipoOrigem.CHAVE, inquilino=linha[0], papel=linha[1]) if linha else None


def _valores(medida: Medida) -> tuple[float | None, str | None]:
    """Valor numérico na coluna valor; booleano também como texto, para não perder o tipo."""
    if isinstance(medida.valor, bool):
        return (1.0 if medida.valor else 0.0), json.dumps(medida.valor)
    if isinstance(medida.valor, (int, float)):
        return float(medida.valor), None
    return None, str(medida.valor)


def _separar_carga(carga: Any) -> tuple[Jsonb | None, str | None]:
    if isinstance(carga, (dict, list)):
        return Jsonb(carga), None
    return None, None if carga is None else str(carga)
