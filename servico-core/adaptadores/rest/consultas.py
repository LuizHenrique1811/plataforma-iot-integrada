"""Rotas de consulta: histórico, último estado e DLQ (RF-DAD-01, RF-DAD-02, RF-DIS-06)."""

from datetime import datetime

from fastapi import APIRouter, Depends, Request

from adaptadores.rest.autenticacao import resolver_origem
from adaptadores.rest.comum import em_utc, parametros_de_pagina
from adaptadores.rest.serializacao import estado_json, medicao_json, pagina_json, rejeitada_json
from dominio.consultas import ServicoDeConsultas
from dominio.paginacao import ParametrosDePagina
from portas.autenticacao import Autenticador

PAGINA = Depends(parametros_de_pagina)


def criar_rotas_de_consulta(servico: ServicoDeConsultas, autenticador: Autenticador) -> APIRouter:
    rotas = APIRouter()

    @rotas.get("/api/v1/dispositivos/{id}/telemetria", tags=["dispositivos"])
    def consultar_telemetria(
        request: Request,
        id: str,
        grandeza: str | None = None,
        inicio: datetime | None = None,
        fim: datetime | None = None,
        pagina: ParametrosDePagina = PAGINA,
    ) -> dict:
        resultado = servico.telemetria(
            resolver_origem(request, autenticador), id, grandeza, em_utc(inicio), em_utc(fim), pagina
        )
        return pagina_json(resultado, medicao_json)

    @rotas.get("/api/v1/dispositivos/{id}/estado", tags=["dispositivos"])
    def obter_estado(request: Request, id: str) -> dict:
        return estado_json(servico.estado(resolver_origem(request, autenticador), id))

    @rotas.get("/api/v1/rejeitadas", tags=["administracao"])
    def listar_rejeitadas(request: Request, pagina: ParametrosDePagina = PAGINA) -> dict:
        return pagina_json(servico.rejeitadas(resolver_origem(request, autenticador), pagina), rejeitada_json)

    return rotas
