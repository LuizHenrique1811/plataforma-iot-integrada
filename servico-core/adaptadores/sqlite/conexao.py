"""Conexão SQLite com a mesma interface que os repositórios SQL usam do psycopg_pool (ADR-0020).

Os repositórios SQL da central rodam na borda sem cópia: este módulo traduz o pouco de SQL que difere
entre PostgreSQL e SQLite e converte tipos (datas, JSON, UUID, booleanos) nos dois sentidos.

Durabilidade (RNF-07, ADR-0016): modo WAL com synchronous=FULL. Cifragem (RF-SEG-05, ADR-0014): com
chave, o arquivo é aberto pelo SQLCipher; sem chave, pelo sqlite3 da biblioteca padrão.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import threading
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from psycopg.errors import ForeignKeyViolation, UniqueViolation
from psycopg.types.json import Jsonb

PASTA_MIGRACOES = Path(__file__).parent / "migracoes"
_AGORA_SQLITE = "strftime('%Y-%m-%dT%H:%M:%f+00:00','now')"
# PostgreSQL -> SQLite. A ordem importa: os marcadores %s são trocados antes de inserir o strftime.
_TRADUCOES = (
    ("%s", "?"),
    ("GREATEST(", "MAX("),
    ("now()", _AGORA_SQLITE),
    ("definicao->'condicao'->>'tipo'", "json_extract(definicao, '$.condicao.tipo')"),
)
_CHAVE_HEX = re.compile(r"[0-9a-f]{64}")

log = logging.getLogger(__name__)


def traduzir(sql: str) -> str:
    for de, para in _TRADUCOES:
        sql = sql.replace(de, para)
    return sql


def _instante(valor: datetime) -> str:
    # Largura fixa em UTC: a ordem alfabética do texto é a ordem cronológica, como nas comparações SQL.
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=UTC)
    return valor.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def _registrar_tipos(modulo: Any) -> None:
    modulo.register_adapter(datetime, _instante)
    modulo.register_adapter(uuid.UUID, str)
    modulo.register_adapter(Jsonb, lambda valor: json.dumps(valor.obj))
    modulo.register_converter("TIMESTAMPTZ", lambda dados: datetime.fromisoformat(dados.decode()))
    modulo.register_converter("JSONB", lambda dados: json.loads(dados))
    modulo.register_converter("BOOLEAN", lambda dados: bool(int(dados)))
    modulo.register_converter("UUID", lambda dados: dados.decode())


@contextmanager
def _como_no_postgres(erro_de_integridade: type[Exception]) -> Iterator[None]:
    """Converte violações do SQLite nos erros do psycopg que os repositórios já tratam (ex.: JaExiste)."""
    try:
        yield
    except erro_de_integridade as erro:
        texto = str(erro)
        if "UNIQUE" in texto or "PRIMARY KEY" in texto:
            raise UniqueViolation(texto) from erro
        if "FOREIGN KEY" in texto:
            raise ForeignKeyViolation(texto) from erro
        raise


class _Conexao:
    def __init__(self, bruta: Any, erro_de_integridade: type[Exception]) -> None:
        self._bruta = bruta
        self._erro_de_integridade = erro_de_integridade

    def execute(self, sql: str, parametros: Sequence[Any] = ()) -> Any:
        with _como_no_postgres(self._erro_de_integridade):
            if not parametros and sql.count(";") > 1:
                self._bruta.executescript(traduzir(sql))
                return self._bruta.cursor()
            return self._bruta.execute(traduzir(sql), tuple(parametros))

    def executemany(self, sql: str, linhas: Sequence[Sequence[Any]]) -> Any:
        with _como_no_postgres(self._erro_de_integridade):
            return self._bruta.executemany(traduzir(sql), [tuple(linha) for linha in linhas])

    @contextmanager
    def transaction(self) -> Iterator[_Conexao]:
        try:
            yield self
        except BaseException:
            self._bruta.rollback()
            raise
        self._bruta.commit()

    @contextmanager
    def cursor(self) -> Iterator[_Conexao]:
        yield self

    # O modo pipeline do psycopg poupa idas e voltas pela rede; o SQLite é local, então aqui não faz nada.
    @contextmanager
    def pipeline(self) -> Iterator[_Conexao]:
        yield self

    def sync(self) -> None:
        pass


class PoolSqlite:
    """Uma conexão compartilhada e serializada: na borda, o SQLite grava uma transação por vez de todo modo."""

    def __init__(self, caminho: str, chave_hex: str | None = None) -> None:
        if chave_hex is not None and not _CHAVE_HEX.fullmatch(chave_hex):
            raise ValueError("a chave da fila deve ter 64 dígitos hexadecimais")
        if chave_hex:
            import sqlcipher3 as modulo
        else:
            modulo = sqlite3
        _registrar_tipos(modulo)
        self.cifrado = chave_hex is not None
        self._trava = threading.RLock()
        self._erro_de_integridade = modulo.IntegrityError
        self._bruta = modulo.connect(caminho, detect_types=modulo.PARSE_DECLTYPES, check_same_thread=False, timeout=30)
        if chave_hex:
            # Precisa ser a primeira instrução; com a chave errada, a próxima leitura falha.
            self._bruta.execute(f"PRAGMA key = \"x'{chave_hex}'\"")
        self._bruta.execute("PRAGMA journal_mode = WAL")
        self._bruta.execute("PRAGMA synchronous = FULL")
        self._bruta.execute("PRAGMA foreign_keys = ON")

    @contextmanager
    def connection(self) -> Iterator[_Conexao]:
        with self._trava:
            try:
                yield _Conexao(self._bruta, self._erro_de_integridade)
            except BaseException:
                self._bruta.rollback()
                raise
            self._bruta.commit()

    def close(self) -> None:
        with self._trava:
            self._bruta.close()


def chave_do_arquivo(caminho: str) -> str:
    """Chave de 256 bits derivada do conteúdo do arquivo de segredo (Docker secret, ADR-0014)."""
    conteudo = Path(caminho).read_bytes().strip()
    if not conteudo:
        raise ValueError(f"arquivo de chave vazio: {caminho}")
    return hashlib.sha256(conteudo).hexdigest()


def caminho_da_url(url: str) -> str:
    """sqlite:////dados/borda.db -> /dados/borda.db; sqlite:///borda.db -> borda.db."""
    endereco = urlparse(url)
    if endereco.scheme != "sqlite":
        raise ValueError(f"URL SQLite inválida: {url}")
    return endereco.path[1:] if endereco.path.startswith("/") else endereco.path


def abrir(url: str, arquivo_de_chave: str | None = None) -> PoolSqlite:
    caminho = caminho_da_url(url)
    if caminho != ":memory:":
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    if arquivo_de_chave is None:
        log.warning("fila da borda sem cifragem: defina CHAVE_FILA_ARQUIVO (RF-SEG-05, ADR-0014)")
        return PoolSqlite(caminho)
    return PoolSqlite(caminho, chave_do_arquivo(arquivo_de_chave))


def aplicar_migracoes(pool: PoolSqlite, pasta: Path = PASTA_MIGRACOES) -> list[str]:
    aplicadas = []
    with pool.connection() as conexao:
        conexao.execute(
            "CREATE TABLE IF NOT EXISTS migracoes_aplicadas (nome TEXT PRIMARY KEY, aplicada_em TEXT NOT NULL)"
        )
        ja_aplicadas = {linha[0] for linha in conexao.execute("SELECT nome FROM migracoes_aplicadas").fetchall()}
        for arquivo in sorted(pasta.glob("*.sql")):
            if arquivo.name in ja_aplicadas:
                continue
            conexao._bruta.executescript(arquivo.read_text(encoding="utf-8"))
            conexao.execute(
                "INSERT INTO migracoes_aplicadas (nome, aplicada_em) VALUES (%s, %s)",
                (arquivo.name, datetime.now(UTC)),
            )
            aplicadas.append(arquivo.name)
            log.info("migração aplicada: %s", arquivo.name)
    return aplicadas
