"""Rotas de regras e alarmes (RF-PRO-02, RF-PRO-03, RF-PRO-05)."""

from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, Request

from adaptadores.rest.autenticacao import resolver_origem
from adaptadores.rest.comum import parametros_de_pagina
from adaptadores.rest.contrato_openapi import ValidadorDeCorpos
from adaptadores.rest.serializacao import alarme_json, pagina_json
from dominio.alarmes import ServicoDeAlarmes
from dominio.paginacao import ParametrosDePagina
from dominio.regras import ServicoDeRegras, regra_de_dict, regra_para_dict
from portas.autenticacao import Autenticador

PAGINA = Depends(parametros_de_pagina)
CORPO = Body(...)


def criar_rotas_de_regras(
    regras: ServicoDeRegras, alarmes: ServicoDeAlarmes, autenticador: Autenticador, corpos: ValidadorDeCorpos
) -> APIRouter:
    rotas = APIRouter(tags=["regras"])

    @rotas.get("/api/v1/regras")
    def listar_regras(request: Request, pagina: ParametrosDePagina = PAGINA) -> dict:
        return pagina_json(regras.listar(resolver_origem(request, autenticador), pagina), regra_para_dict)

    @rotas.post("/api/v1/regras", status_code=201)
    def criar_regra(request: Request, corpo: Any = CORPO) -> dict:
        origem = resolver_origem(request, autenticador)
        return regra_para_dict(regras.criar(origem, regra_de_dict(corpos.validar("Regra", corpo))))

    @rotas.get("/api/v1/alarmes")
    def listar_alarmes(
        request: Request,
        estado: Literal["ativo", "reconhecido", "resolvido"] | None = None,
        severidade: Literal["info", "aviso", "critico"] | None = None,
        pagina: ParametrosDePagina = PAGINA,
    ) -> dict:
        resultado = alarmes.listar(resolver_origem(request, autenticador), estado, severidade, pagina)
        return pagina_json(resultado, alarme_json)

    @rotas.post("/api/v1/alarmes/{id}/reconhecer")
    def reconhecer_alarme(request: Request, id: str) -> dict:
        return alarme_json(alarmes.reconhecer(resolver_origem(request, autenticador), id))

    @rotas.post("/api/v1/alarmes/{id}/resolver")
    def resolver_alarme(request: Request, id: str) -> dict:
        return alarme_json(alarmes.resolver(resolver_origem(request, autenticador), id))

    return rotas
