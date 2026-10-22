"""Rotas de catálogo, cadastro, inquilinos e chaves (RF-CEN-01 a 03, RF-DIS-01, RF-DIS-02, RF-SEG-02)."""

from typing import Any

from fastapi import APIRouter, Body, Depends, Request, Response

from adaptadores.rest.autenticacao import resolver_origem
from adaptadores.rest.comum import parametros_de_pagina
from adaptadores.rest.contrato_openapi import ValidadorDeCorpos
from adaptadores.rest.serializacao import (
    area_json,
    chave_json,
    dispositivo_json,
    dominio_json,
    inquilino_json,
    pagina_json,
    perfil_json,
    site_json,
)
from dominio.catalogo import Area, Dominio, Inquilino, ServicoDeCatalogo, Site
from dominio.erros import DadosInvalidos
from dominio.modelos import DispositivoCadastrado, ErroDeCampo, GrandezaDoPerfil, Perfil
from dominio.paginacao import ParametrosDePagina
from portas.autenticacao import Autenticador

PAGINA = Depends(parametros_de_pagina)
CORPO = Body(...)


def criar_rotas_de_catalogo(
    servico: ServicoDeCatalogo, autenticador: Autenticador, corpos: ValidadorDeCorpos
) -> APIRouter:
    rotas = APIRouter()

    def origem(request: Request):
        return resolver_origem(request, autenticador)

    # Inquilinos e chaves --------------------------------------------------------------------

    @rotas.get("/api/v1/inquilinos", tags=["administracao"])
    def listar_inquilinos(request: Request, pagina: ParametrosDePagina = PAGINA) -> dict:
        return pagina_json(servico.listar_inquilinos(origem(request), pagina), inquilino_json)

    @rotas.post("/api/v1/inquilinos", status_code=201, tags=["administracao"])
    def criar_inquilino(request: Request, corpo: Any = CORPO) -> dict:
        quem = origem(request)
        dados = corpos.validar("Inquilino", corpo)
        return inquilino_json(servico.criar_inquilino(quem, Inquilino(dados["id"], dados["nome"])))

    @rotas.post("/api/v1/chaves", status_code=201, tags=["administracao"])
    def criar_chave(request: Request, corpo: Any = CORPO) -> dict:
        quem = origem(request)
        dados = corpos.validar("Chave", corpo)
        chave, segredo = servico.emitir_chave(quem, dados["papel"], dados.get("descricao"))
        return chave_json(chave, segredo)

    # Catálogo -------------------------------------------------------------------------------

    @rotas.get("/api/v1/catalogo/dominios", tags=["catalogo"])
    def listar_dominios(request: Request, pagina: ParametrosDePagina = PAGINA) -> dict:
        return pagina_json(servico.listar_dominios(origem(request), pagina), dominio_json)

    @rotas.post("/api/v1/catalogo/dominios", status_code=201, tags=["catalogo"])
    def criar_dominio(request: Request, corpo: Any = CORPO) -> dict:
        quem = origem(request)
        dados = corpos.validar("Dominio", corpo)
        return dominio_json(servico.criar_dominio(quem, Dominio(dados["id"], dados["nome"], dados.get("descricao"))))

    @rotas.get("/api/v1/catalogo/perfis", tags=["catalogo"])
    def listar_perfis(request: Request, pagina: ParametrosDePagina = PAGINA) -> dict:
        return pagina_json(servico.listar_perfis(origem(request), pagina), perfil_json)

    @rotas.post("/api/v1/catalogo/perfis", status_code=201, tags=["catalogo"])
    def criar_perfil(request: Request, corpo: Any = CORPO) -> dict:
        quem = origem(request)
        dados = corpos.validar("Perfil", corpo)
        return perfil_json(servico.criar_perfil(quem, _perfil(dados)))

    @rotas.get("/api/v1/sites", tags=["catalogo"])
    def listar_sites(request: Request, pagina: ParametrosDePagina = PAGINA) -> dict:
        return pagina_json(servico.listar_sites(origem(request), pagina), site_json)

    @rotas.post("/api/v1/sites", status_code=201, tags=["catalogo"])
    def criar_site(request: Request, corpo: Any = CORPO) -> dict:
        quem = origem(request)
        dados = corpos.validar("Site", corpo)
        return site_json(servico.criar_site(quem, Site(dados["id"], dados["nome"], dados.get("geo"))))

    @rotas.get("/api/v1/sites/{id}/areas", tags=["catalogo"])
    def listar_areas(request: Request, id: str, pagina: ParametrosDePagina = PAGINA) -> dict:
        return pagina_json(servico.listar_areas(origem(request), id, pagina), area_json)

    @rotas.post("/api/v1/sites/{id}/areas", status_code=201, tags=["catalogo"])
    def criar_area(request: Request, id: str, corpo: Any = CORPO) -> dict:
        quem = origem(request)
        dados = corpos.validar("Area", corpo)
        return area_json(servico.criar_area(quem, Area(dados["id"], id, dados["nome"], dados.get("geo"))))

    # Dispositivos ---------------------------------------------------------------------------

    @rotas.get("/api/v1/dispositivos", tags=["dispositivos"])
    def listar_dispositivos(
        request: Request,
        dominio: str | None = None,
        perfil: str | None = None,
        site: str | None = None,
        area: str | None = None,
        pagina: ParametrosDePagina = PAGINA,
    ) -> dict:
        filtros = {"dominio": dominio, "perfil": perfil, "site": site, "area": area}
        return pagina_json(servico.listar_dispositivos(origem(request), filtros, pagina), dispositivo_json)

    @rotas.post("/api/v1/dispositivos", status_code=201, tags=["dispositivos"])
    def cadastrar_dispositivo(request: Request, corpo: Any = CORPO) -> dict:
        quem = origem(request)
        dados = corpos.validar("Dispositivo", corpo)
        dispositivo, token = servico.cadastrar_dispositivo(
            quem,
            DispositivoCadastrado(
                inquilino="",
                id=dados["id"],
                perfil=dados["perfil"],
                dominio=dados["dominio"],
                site=dados["site"],
                area=dados.get("area"),
                fabricante=dados.get("fabricante"),
                firmware=dados.get("firmware"),
            ),
        )
        return dispositivo_json(dispositivo, token)

    @rotas.get("/api/v1/dispositivos/{id}", tags=["dispositivos"])
    def obter_dispositivo(request: Request, id: str) -> dict:
        return dispositivo_json(servico.obter_dispositivo(origem(request), id))

    @rotas.delete("/api/v1/dispositivos/{id}/credencial", status_code=204, tags=["dispositivos"])
    def revogar_credencial(request: Request, id: str) -> Response:
        servico.revogar_credencial(origem(request), id)
        return Response(status_code=204)

    return rotas


def _perfil(dados: dict[str, Any]) -> Perfil:
    grandezas: dict[str, GrandezaDoPerfil] = {}
    for indice, item in enumerate(dados["grandezas"]):
        if item["grandeza"] in grandezas:
            raise DadosInvalidos("Perfil inválido.", [ErroDeCampo(f"/grandezas/{indice}", "grandeza repetida")])
        grandezas[item["grandeza"]] = GrandezaDoPerfil(
            item["grandeza"], item["unidade"], item.get("minimo"), item.get("maximo")
        )
    return Perfil(dados["id"], dados["nome"], grandezas, dados["intervalo_envio_s"])
