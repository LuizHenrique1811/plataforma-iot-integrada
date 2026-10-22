"""Catálogo, ingestão, DLQ e autenticação sobre PostgreSQL + TimescaleDB."""

from __future__ import annotations

import hmac
import json
import uuid
from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from adaptadores.credenciais import hash_segredo
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


class CatalogoPostgres:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def obter_dispositivo(self, inquilino: str, dispositivo: str) -> DispositivoCadastrado | None:
        with self._pool.connection() as conexao:
            linha = conexao.execute(
                "SELECT inquilino_id, id, perfil_id, dominio_id, site_id, area_id, revogado_em"
                " FROM dispositivos WHERE inquilino_id = %s AND id = %s",
                (inquilino, dispositivo),
            ).fetchone()
        return DispositivoCadastrado(*linha) if linha else None

    def obter_perfil(self, inquilino: str, perfil: str) -> Perfil | None:
        with self._pool.connection() as conexao:
            linha = conexao.execute(
                "SELECT id, nome, grandezas, intervalo_envio_s FROM perfis WHERE inquilino_id = %s AND id = %s",
                (inquilino, perfil),
            ).fetchone()
        if linha is None:
            return None
        grandezas = {
            item["grandeza"]: GrandezaDoPerfil(
                item["grandeza"], item["unidade"], item.get("minimo"), item.get("maximo")
            )
            for item in linha[2]
        }
        return Perfil(linha[0], linha[1], grandezas, linha[3])


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
        return True


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
