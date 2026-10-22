"""Montagem da aplicação FastAPI: rotas, contratos publicados, documentação e métricas."""

import mimetypes
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from adaptadores.rest.erros import ErroHttp, tratar_erro_http
from adaptadores.rest.ingestao import criar_rotas_de_ingestao
from dominio.pipeline import PipelineDeIngestao
from portas.autenticacao import Autenticador

VERSAO = "0.1.0"


def criar_app(
    *,
    pipeline: PipelineDeIngestao,
    autenticador: Autenticador,
    contratos_dir: Path,
    papel: str,
    ao_encerrar: tuple[Callable[[], None], ...] = (),
) -> FastAPI:
    @asynccontextmanager
    async def ciclo_de_vida(_: FastAPI):
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
    app.include_router(criar_rotas_de_ingestao(pipeline, autenticador))

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
