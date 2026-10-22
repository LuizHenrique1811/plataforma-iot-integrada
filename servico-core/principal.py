"""Raiz de composição: lê a configuração e liga cada porta ao seu adaptador (ADR-0005, ADR-0006).

A mesma imagem serve à central (PostgreSQL) e à borda (SQLite cifrado, fila e sincronização).
Execução: uvicorn principal:criar_aplicacao --factory
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
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
from adaptadores.observabilidade import configurar_logs, observar_sincronizacao
from adaptadores.relogio import RelogioDoSistema
from adaptadores.rest.aplicacao import criar_app
from configuracao import Configuracao
from dominio.acoes import aviso_de_resolucao, executores_da_borda, executores_padrao
from dominio.alarmes import ServicoDeAlarmes
from dominio.catalogo import ServicoDeCatalogo
from dominio.consultas import ServicoDeConsultas
from dominio.motor import MotorDeRegras
from dominio.pipeline import PipelineDeIngestao
from dominio.regras import ServicoDeRegras
from dominio.sincronizacao import SincronizadorDeBorda
from portas.sincronizacao import ClienteDaCentral, FilaDeSincronizacao

log = logging.getLogger("servico_core")


@dataclass
class Servico:
    app: FastAPI
    pipeline: PipelineDeIngestao
    motor: MotorDeRegras
    fila: FilaDeSincronizacao | None = None
    sincronizador: SincronizadorDeBorda | None = None


def criar_aplicacao(config: Configuracao | None = None) -> FastAPI:
    return montar_servico(config or Configuracao.do_ambiente()).app


def montar_servico(config: Configuracao, *, cliente_da_central: ClienteDaCentral | None = None) -> Servico:
    configurar_logs(config.log_nivel)
    relogio = RelogioDoSistema()
    ao_iniciar: list[Callable[[], None]] = []
    ao_encerrar: list[Callable[[], None]] = []
    fila = None
    borda = config.papel == "borda"

    if borda:
        if not (config.banco_url or "").startswith("sqlite"):
            raise ValueError("a borda usa BANCO_URL=sqlite:///caminho (fila persistente)")
        if not config.borda_id:
            raise ValueError("defina BORDA_ID, o identificador do nó de borda")
        from adaptadores.postgres.regras import AlarmesPostgres, RegrasPostgres
        from adaptadores.postgres.repositorios import (
            AutenticadorPostgres,
            CatalogoPostgres,
            ConsultasPostgres,
            FilaDeRejeitadasPostgres,
        )
        from adaptadores.sqlite.conexao import abrir, aplicar_migracoes
        from adaptadores.sqlite.fila import FilaSqlite, RepositorioDeIngestaoDaBorda

        # Os mesmos repositórios SQL da central, sobre SQLite (ADR-0020).
        pool = abrir(config.banco_url, config.chave_fila_arquivo)
        aplicar_migracoes(pool)
        repositorio = RepositorioDeIngestaoDaBorda(pool, config.borda_id)
        fila = FilaSqlite(pool)
    elif config.banco_url and config.banco_url.startswith("postgresql"):
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
        repositorio = RepositorioDeIngestaoPostgres(pool)
    elif config.banco_url:
        raise ValueError(f"BANCO_URL não suportada na central: {config.banco_url.split(':', 1)[0]}")
    else:
        pool = None

    if pool is not None:
        catalogo = CatalogoPostgres(pool)
        rejeitadas = FilaDeRejeitadasPostgres(pool)
        consultas = ConsultasPostgres(pool)
        autenticador = AutenticadorPostgres(pool, chave_admin=config.chave_admin)
        regras = RegrasPostgres(pool)
        alarmes = AlarmesPostgres(pool)
        ao_encerrar.append(pool.close)
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

    saidas = dict(
        alarmes=alarmes,
        catalogo=catalogo,
        notificador=NotificadorEmLog(),
        publicador=publicador,
        webhook=webhook,
        relogio=relogio,
    )
    if borda:
        executores = executores_da_borda(**saidas, fila=fila, borda=config.borda_id)
    else:
        executores = executores_padrao(**saidas, origem=config.papel)
    motor = MotorDeRegras(
        regras,
        alarmes,
        executores,
        ambito=config.papel,
        ao_resolver=aviso_de_resolucao(fila, config.borda_id) if borda else None,
    )
    # Com várias réplicas, só uma verifica ausências (as demais usam VERIFICACAO_AUSENCIA_S=0, ADR-0022).
    if config.verificacao_ausencia_s > 0:
        verificador = TarefaPeriodica(
            "verificacao-ausencia", config.verificacao_ausencia_s, lambda: motor.verificar_ausencias(relogio.agora())
        )
        ao_iniciar.append(verificador.iniciar)
        ao_encerrar.insert(0, verificador.parar)

    sincronizador = None
    if borda:
        if cliente_da_central is None and config.central_url and config.chave_central:
            from adaptadores.central import ClienteDaCentralHttp

            cliente_da_central = ClienteDaCentralHttp(config.central_url, config.chave_central, config.borda_id)
        if cliente_da_central is None:
            log.warning("borda sem CENTRAL_URL e CHAVE_CENTRAL: a fila acumula até a central ser configurada")
        else:
            sincronizador = SincronizadorDeBorda(fila, cliente_da_central, tamanho_do_lote=config.tamanho_do_lote)
            tarefa = TarefaPeriodica(
                "sincronizacao", config.sincronizacao_s, lambda: observar_sincronizacao(sincronizador.sincronizar())
            )
            ao_iniciar.append(tarefa.iniciar)
            ao_encerrar.insert(0, tarefa.parar)

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
            sessao_persistente=config.mqtt_sessao_persistente,
        )
        ao_iniciar.append(consumidor.iniciar)
        # O consumidor para antes de tudo, para terminar de gravar o que está em andamento.
        ao_encerrar.insert(0, consumidor.parar)

    log.info("servico-core iniciado", extra={"entrada": config.papel})
    app = criar_app(
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
    return Servico(app, pipeline, motor, fila, sincronizador)
