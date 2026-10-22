"""Fila de sincronização e ingestão da borda sobre SQLite (RF-EDG-01)."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg.types.json import Jsonb

from adaptadores.postgres.repositorios import RepositorioDeIngestaoPostgres
from adaptadores.sqlite.conexao import PoolSqlite
from dominio.modelos import MensagemAceita
from dominio.sincronizacao import ItemDaFila, prioridade_de

_ENFILEIRAR = (
    "INSERT INTO fila_sincronizacao (id_mensagem, prioridade, carga) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING"
)


class FilaSqlite:
    def __init__(self, pool: PoolSqlite) -> None:
        self._pool = pool

    def enfileirar(self, carga: dict[str, Any], prioridade: int) -> None:
        with self._pool.connection() as conexao:
            conexao.execute(_ENFILEIRAR, (uuid.UUID(carga["id_mensagem"]), prioridade, Jsonb(carga)))

    def proximas(self, limite: int) -> list[ItemDaFila]:
        with self._pool.connection() as conexao:
            linhas = conexao.execute(
                "SELECT seq, carga FROM fila_sincronizacao ORDER BY prioridade, seq LIMIT %s", (limite,)
            ).fetchall()
        return [ItemDaFila(linha[0], linha[1]) for linha in linhas]

    def remover(self, sequencias: list[int]) -> None:
        if not sequencias:
            return
        marcadores = ", ".join(["%s"] * len(sequencias))
        with self._pool.connection() as conexao:
            conexao.execute(f"DELETE FROM fila_sincronizacao WHERE seq IN ({marcadores})", sequencias)

    def pendentes(self) -> int:
        with self._pool.connection() as conexao:
            return conexao.execute("SELECT count(*) FROM fila_sincronizacao").fetchone()[0]


class RepositorioDeIngestaoDaBorda(RepositorioDeIngestaoPostgres):
    """Grava como a central e, na mesma transação, enfileira a mensagem para a central.

    Se a gravação falha, nada vai para a fila; se a fila falha, nada é gravado: não há como a central
    perder uma mensagem que a borda aceitou (RNF-10).
    """

    def __init__(self, pool: PoolSqlite, borda: str) -> None:
        super().__init__(pool)
        self._borda = borda

    def _depois_de_gravar(self, cursor: Any, mensagem: MensagemAceita) -> None:
        carga = dict(mensagem.carga)
        carga.setdefault("via", self._borda)
        cursor.execute(_ENFILEIRAR, (uuid.UUID(carga["id_mensagem"]), prioridade_de(carga), Jsonb(carga)))
