"""Raiz de composição: lê a configuração e liga cada porta ao seu adaptador (ADR-0005, ADR-0006).

Execução: uvicorn principal:criar_aplicacao --factory
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta

from fastapi import FastAPI

from adaptadores.contrato_jsonschema import ValidadorJsonSchema
from adaptadores.credenciais import GeradorDeCredenciaisSeguro
from adaptadores.memoria import (
    AutenticadorEmMemoria,
    CatalogoEmMemoria,
    ConsultasEmMemoria,
    FilaDeRejeitadasEmMemoria,
    RepositorioEmMemoria,
)
from adaptadores.observabilidade import configurar_logs
from adaptadores.relogio import RelogioDoSistema
from adaptadores.rest.aplicacao import criar_app
from configuracao import Configuracao
from dominio.catalogo import ServicoDeCatalogo
from dominio.consultas import ServicoDeConsultas
from dominio.pipeline import PipelineDeIngestao

log = logging.getLogger("servico_core")


def criar_aplicacao(config: Configuracao | None = None) -> FastAPI:
    config = config or Configuracao.do_ambiente()
    configurar_logs(config.log_nivel)
    relogio = RelogioDoSistema()
    ao_iniciar: list[Callable[[], None]] = []
    ao_encerrar: list[Callable[[], None]] = []

    if config.banco_url and config.banco_url.startswith("postgresql"):
        from adaptadores.postgres.conexao import aplicar_migracoes, criar_pool
        from adaptadores.postgres.repositorios import (
            AutenticadorPostgres,
            CatalogoPostgres,
            ConsultasPostgres,
            FilaDeRejeitadasPostgres,
            RepositorioDeIngestaoPostgres,
        )

        pool = criar_pool(config.banco_url)
        aplicar_migracoes(pool)
        catalogo = CatalogoPostgres(pool)
        repositorio = RepositorioDeIngestaoPostgres(pool)
        rejeitadas = FilaDeRejeitadasPostgres(pool)
        consultas = ConsultasPostgres(pool)
        autenticador = AutenticadorPostgres(pool, chave_admin=config.chave_admin)
        ao_encerrar.append(pool.close)
    elif config.banco_url:
        raise ValueError(f"BANCO_URL não suportada ainda: {config.banco_url.split(':', 1)[0]}")
    else:
        log.warning("BANCO_URL vazia: usando adaptadores em memória; nada é persistido")
        catalogo = CatalogoEmMemoria()
        repositorio = RepositorioEmMemoria()
        rejeitadas = FilaDeRejeitadasEmMemoria()
        consultas = ConsultasEmMemoria(repositorio, rejeitadas)
        autenticador = AutenticadorEmMemoria(chave_admin=config.chave_admin, catalogo=catalogo)

    pipeline = PipelineDeIngestao(
        ValidadorJsonSchema(config.contratos_dir),
        catalogo,
        repositorio,
        rejeitadas,
        relogio,
        limite_dado_atual=timedelta(seconds=config.limite_dado_atual_s),
    )

    if config.mqtt_url:
        from adaptadores.mqtt import ConsumidorMqtt

        consumidor = ConsumidorMqtt(
            pipeline,
            config.mqtt_url,
            cliente_id=config.mqtt_cliente,
            grupo=config.mqtt_grupo,
            trabalhadores=config.mqtt_trabalhadores,
        )
        ao_iniciar.append(consumidor.iniciar)
        # O consumidor para antes de o pool fechar, para terminar de gravar o que está em andamento.
        ao_encerrar.insert(0, consumidor.parar)

    log.info("servico-core iniciado", extra={"entrada": config.papel})
    return criar_app(
        pipeline=pipeline,
        autenticador=autenticador,
        contratos_dir=config.contratos_dir,
        papel=config.papel,
        catalogo=ServicoDeCatalogo(catalogo, GeradorDeCredenciaisSeguro(), relogio),
        consultas=ServicoDeConsultas(consultas, catalogo, relogio),
        ao_iniciar=tuple(ao_iniciar),
        ao_encerrar=tuple(ao_encerrar),
    )
