"""Montagem da aplicação FastAPI: rotas, contratos publicados, documentação e métricas."""

import mimetypes
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.exceptions import HTTPException as StarletteHTTPException

from adaptadores.rest.catalogo import criar_rotas_de_catalogo
from adaptadores.rest.comum import tratar_erro_de_dominio, tratar_http_generico, tratar_parametros_invalidos
from adaptadores.rest.consultas import criar_rotas_de_consulta
from adaptadores.rest.contrato_openapi import ValidadorDeCorpos
from adaptadores.rest.erros import ErroHttp, tratar_erro_http
from adaptadores.rest.ingestao import criar_rotas_de_ingestao
from adaptadores.rest.regras import criar_rotas_de_regras
from dominio.alarmes import ServicoDeAlarmes
from dominio.catalogo import ServicoDeCatalogo
from dominio.consultas import ServicoDeConsultas
from dominio.erros import ErroDeDominio
from dominio.pipeline import PipelineDeIngestao
from dominio.regras import ServicoDeRegras
from portas.autenticacao import Autenticador

VERSAO = "0.3.0"


def criar_app(
    *,
    pipeline: PipelineDeIngestao,
    autenticador: Autenticador,
    contratos_dir: Path,
    papel: str,
    catalogo: ServicoDeCatalogo | None = None,
    consultas: ServicoDeConsultas | None = None,
    regras: ServicoDeRegras | None = None,
    alarmes: ServicoDeAlarmes | None = None,
    ao_iniciar: tuple[Callable[[], None], ...] = (),
    ao_encerrar: tuple[Callable[[], None], ...] = (),
) -> FastAPI:
    @asynccontextmanager
    async def ciclo_de_vida(_: FastAPI):
        for iniciar in ao_iniciar:
            iniciar()
        yield
        for encerrar in ao_encerrar:
            encerrar()

    # docs_url e openapi_url desligados: a documentação vem do contrato escrito à mão (RF-APP-01).
    app = FastAPI(
        title="Plataforma IoT Integrada",
        version=VERSAO,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=ciclo_de_vida,
    )
    app.add_exception_handler(ErroHttp, tratar_erro_http)
    app.add_exception_handler(ErroDeDominio, tratar_erro_de_dominio)
    app.add_exception_handler(RequestValidationError, tratar_parametros_invalidos)
    app.add_exception_handler(StarletteHTTPException, tratar_http_generico)
    app.include_router(criar_rotas_de_ingestao(pipeline, autenticador))
    corpos = ValidadorDeCorpos(contratos_dir)
    if catalogo is not None:
        app.include_router(criar_rotas_de_catalogo(catalogo, autenticador, corpos))
    if consultas is not None:
        app.include_router(criar_rotas_de_consulta(consultas, autenticador))
    if regras is not None and alarmes is not None:
        app.include_router(criar_rotas_de_regras(regras, alarmes, autenticador, corpos))

    @app.get("/saude", tags=["operacao"])
    def saude() -> dict:
        return {"situacao": "ok", "papel": papel, "versao": VERSAO}

    @app.get("/metrics", tags=["operacao"])
    def metricas() -> Response:
        # Formato Prometheus sem subir o servidor Prometheus (RF-OBS-01, ADR-0007).
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/docs", include_in_schema=False)
    def documentacao():
        # Painel de cadastro simplificado (ADR-0019), gerado de contratos/openapi.yaml.
        return get_swagger_ui_html(openapi_url="/contratos/openapi.yaml", title="Plataforma IoT Integrada - API")

    # Contratos publicados por URL (RF-INT-01); as versões ficam no nome dos arquivos.
    mimetypes.add_type("application/yaml", ".yaml")
    app.mount("/contratos", StaticFiles(directory=contratos_dir), name="contratos")
    return app
