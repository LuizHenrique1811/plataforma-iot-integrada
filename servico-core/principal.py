"""Raiz de composição: lê a configuração e liga cada porta ao seu adaptador (ADR-0005, ADR-0006).

Execução: uvicorn principal:criar_aplicacao --factory
"""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import FastAPI

from adaptadores.contrato_jsonschema import ValidadorJsonSchema
from adaptadores.memoria import (
    AutenticadorEmMemoria,
    CatalogoEmMemoria,
    FilaDeRejeitadasEmMemoria,
    RepositorioEmMemoria,
)
from adaptadores.observabilidade import configurar_logs
from adaptadores.relogio import RelogioDoSistema
from adaptadores.rest.aplicacao import criar_app
from configuracao import Configuracao
from dominio.pipeline import PipelineDeIngestao

log = logging.getLogger("servico_core")


def criar_aplicacao(config: Configuracao | None = None) -> FastAPI:
    config = config or Configuracao.do_ambiente()
    configurar_logs(config.log_nivel)
    ao_encerrar = ()

    if config.banco_url and config.banco_url.startswith("postgresql"):
        from adaptadores.postgres.conexao import aplicar_migracoes, criar_pool
        from adaptadores.postgres.repositorios import (
            AutenticadorPostgres,
            CatalogoPostgres,
            FilaDeRejeitadasPostgres,
            RepositorioDeIngestaoPostgres,
        )

        pool = criar_pool(config.banco_url)
        aplicar_migracoes(pool)
        catalogo = CatalogoPostgres(pool)
        repositorio = RepositorioDeIngestaoPostgres(pool)
        rejeitadas = FilaDeRejeitadasPostgres(pool)
        autenticador = AutenticadorPostgres(pool, chave_admin=config.chave_admin)
        ao_encerrar = (pool.close,)
    elif config.banco_url:
        raise ValueError(f"BANCO_URL não suportada ainda: {config.banco_url.split(':', 1)[0]}")
    else:
        log.warning("BANCO_URL vazia: usando adaptadores em memória; nada é persistido")
        catalogo = CatalogoEmMemoria()
        repositorio = RepositorioEmMemoria()
        rejeitadas = FilaDeRejeitadasEmMemoria()
        autenticador = AutenticadorEmMemoria(chave_admin=config.chave_admin)

    pipeline = PipelineDeIngestao(
        ValidadorJsonSchema(config.contratos_dir),
        catalogo,
        repositorio,
        rejeitadas,
        RelogioDoSistema(),
        limite_dado_atual=timedelta(seconds=config.limite_dado_atual_s),
    )
    log.info("servico-core iniciado", extra={"entrada": config.papel})
    return criar_app(
        pipeline=pipeline,
        autenticador=autenticador,
        contratos_dir=config.contratos_dir,
        papel=config.papel,
        ao_encerrar=ao_encerrar,
    )
