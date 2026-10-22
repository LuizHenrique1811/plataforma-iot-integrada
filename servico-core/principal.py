"""Raiz de composição: lê a configuração e liga cada porta ao seu adaptador (ADR-0005, ADR-0006).

Execução: uvicorn principal:criar_aplicacao --factory
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta

from fastapi import FastAPI

from adaptadores.acoes import ClienteWebhookHttp, NotificadorEmLog, PublicadorEmLog
from adaptadores.agendador import TarefaPeriodica
from adaptadores.contrato_jsonschema import ValidadorJsonSchema
from adaptadores.credenciais import GeradorDeCredenciaisSeguro
from adaptadores.memoria import (
    AlarmesEmMemoria,
    AutenticadorEmMemoria,
    CatalogoEmMemoria,
    ConsultasEmMemoria,
    FilaDeRejeitadasEmMemoria,
    RegrasEmMemoria,
    RepositorioEmMemoria,
)
from adaptadores.observabilidade import configurar_logs
from adaptadores.relogio import RelogioDoSistema
from adaptadores.rest.aplicacao import criar_app
from configuracao import Configuracao
from dominio.acoes import executores_padrao
from dominio.alarmes import ServicoDeAlarmes
from dominio.catalogo import ServicoDeCatalogo
from dominio.consultas import ServicoDeConsultas
from dominio.motor import MotorDeRegras
from dominio.pipeline import PipelineDeIngestao
from dominio.regras import ServicoDeRegras

log = logging.getLogger("servico_core")


def criar_aplicacao(config: Configuracao | None = None) -> FastAPI:
    config = config or Configuracao.do_ambiente()
    configurar_logs(config.log_nivel)
    relogio = RelogioDoSistema()
    ao_iniciar: list[Callable[[], None]] = []
    ao_encerrar: list[Callable[[], None]] = []

    if config.banco_url and config.banco_url.startswith("postgresql"):
        from adaptadores.postgres.conexao import aplicar_migracoes, criar_pool
        from adaptadores.postgres.regras import AlarmesPostgres, RegrasPostgres
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
        regras = RegrasPostgres(pool)
        alarmes = AlarmesPostgres(pool)
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
        regras = RegrasEmMemoria(catalogo, repositorio)
        alarmes = AlarmesEmMemoria()

    if config.mqtt_url:
        from adaptadores.mqtt import PublicadorMqtt

        publicador = PublicadorMqtt(config.mqtt_url, cliente_id=f"{config.mqtt_cliente}-pub")
        ao_iniciar.append(publicador.iniciar)
        ao_encerrar.insert(0, publicador.parar)
    else:
        publicador = PublicadorEmLog()
    webhook = ClienteWebhookHttp()
    ao_encerrar.insert(0, webhook.encerrar)

    motor = MotorDeRegras(
        regras,
        alarmes,
        executores_padrao(
            alarmes=alarmes,
            catalogo=catalogo,
            notificador=NotificadorEmLog(),
            publicador=publicador,
            webhook=webhook,
            relogio=relogio,
            origem=config.papel,
        ),
        ambito=config.papel,
    )
    verificador = TarefaPeriodica(
        "verificacao-ausencia", config.verificacao_ausencia_s, lambda: motor.verificar_ausencias(relogio.agora())
    )
    ao_iniciar.append(verificador.iniciar)
    ao_encerrar.insert(0, verificador.parar)

    pipeline = PipelineDeIngestao(
        ValidadorJsonSchema(config.contratos_dir),
        catalogo,
        repositorio,
        rejeitadas,
        relogio,
        limite_dado_atual=timedelta(seconds=config.limite_dado_atual_s),
        observadores=(motor,),
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
        # O consumidor para antes de tudo, para terminar de gravar o que está em andamento.
        ao_encerrar.insert(0, consumidor.parar)

    log.info("servico-core iniciado", extra={"entrada": config.papel})
    return criar_app(
        pipeline=pipeline,
        autenticador=autenticador,
        contratos_dir=config.contratos_dir,
        papel=config.papel,
        catalogo=ServicoDeCatalogo(catalogo, GeradorDeCredenciaisSeguro(), relogio),
        consultas=ServicoDeConsultas(consultas, catalogo, relogio),
        regras=ServicoDeRegras(regras, relogio, ao_mudar=motor.esquecer_cache),
        alarmes=ServicoDeAlarmes(alarmes, relogio),
        ao_iniciar=tuple(ao_iniciar),
        ao_encerrar=tuple(ao_encerrar),
    )
