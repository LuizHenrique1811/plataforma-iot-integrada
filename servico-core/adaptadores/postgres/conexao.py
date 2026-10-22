"""Pool de conexões e migrações em SQL puro, aplicadas na inicialização."""

import logging
from pathlib import Path

from psycopg_pool import ConnectionPool

PASTA_MIGRACOES = Path(__file__).parent / "migracoes"
_TRAVA_MIGRACOES = 461_100  # pg_advisory_xact_lock: várias réplicas não aplicam a mesma migração juntas

log = logging.getLogger(__name__)


def criar_pool(url: str, tamanho_maximo: int = 10) -> ConnectionPool:
    # autocommit: uma consulta avulsa não abre transação (nem custa um COMMIT a mais, ADR-0022). Gravações com
    # mais de um comando usam conexao.transaction() explicitamente.
    pool = ConnectionPool(url, min_size=1, max_size=tamanho_maximo, open=False, kwargs={"autocommit": True})
    pool.open(wait=True, timeout=30)
    return pool


def aplicar_migracoes(pool: ConnectionPool, pasta: Path = PASTA_MIGRACOES) -> list[str]:
    aplicadas = []
    with pool.connection() as conexao, conexao.transaction():
        conexao.execute("SELECT pg_advisory_xact_lock(%s)", (_TRAVA_MIGRACOES,))
        conexao.execute(
            "CREATE TABLE IF NOT EXISTS migracoes_aplicadas ("
            " nome text PRIMARY KEY, aplicada_em timestamptz NOT NULL DEFAULT now())"
        )
        ja_aplicadas = {linha[0] for linha in conexao.execute("SELECT nome FROM migracoes_aplicadas")}
        for arquivo in sorted(pasta.glob("*.sql")):
            if arquivo.name in ja_aplicadas:
                continue
            conexao.execute(arquivo.read_text(encoding="utf-8"))
            conexao.execute("INSERT INTO migracoes_aplicadas (nome) VALUES (%s)", (arquivo.name,))
            aplicadas.append(arquivo.name)
            log.info("migração aplicada: %s", arquivo.name)
    return aplicadas
