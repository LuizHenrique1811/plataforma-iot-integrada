"""Peças comuns às rotas: paginação, tradução de erros do domínio e de parâmetros."""

from datetime import UTC, datetime

from fastapi import Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from adaptadores.rest.erros import corpo_de_erro
from dominio.erros import AcessoNegado, DadosInvalidos, ErroDeDominio, JaExiste, NaoEncontrado
from dominio.modelos import ErroDeCampo
from dominio.paginacao import TAMANHO_PADRAO, ParametrosDePagina

_STATUS = {AcessoNegado: 403, NaoEncontrado: 404, JaExiste: 409, DadosInvalidos: 400}


def parametros_de_pagina(
    pagina: int = Query(1, description="Número da página, a partir de 1."),
    tamanho: int = Query(TAMANHO_PADRAO, description="Itens por página."),
    ordenar: str | None = Query(None, description="Campo de ordenação; prefixo - para decrescente."),
) -> ParametrosDePagina:
    return ParametrosDePagina(pagina, tamanho, ordenar)


def em_utc(valor: datetime | None) -> datetime | None:
    """Datas sem fuso nos parâmetros são lidas como UTC."""
    if valor is None or valor.tzinfo is not None:
        return valor
    return valor.replace(tzinfo=UTC)


async def tratar_erro_de_dominio(_: Request, erro: ErroDeDominio) -> JSONResponse:
    return JSONResponse(corpo_de_erro(erro.codigo, erro.mensagem, erro.erros), status_code=_STATUS.get(type(erro), 400))


async def tratar_parametros_invalidos(_: Request, erro: RequestValidationError) -> JSONResponse:
    # O FastAPI responderia 422; o contrato usa 400 com a lista de erros.
    erros = [
        ErroDeCampo(
            "/".join(str(parte) for parte in item["loc"] if parte not in ("query", "path", "body")), item["msg"]
        )
        for item in erro.errors()
    ]
    return JSONResponse(corpo_de_erro("parametros_invalidos", "Parâmetros inválidos.", erros), status_code=400)
