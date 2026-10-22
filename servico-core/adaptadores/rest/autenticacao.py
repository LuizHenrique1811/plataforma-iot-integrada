"""Resolve a origem da requisição a partir dos cabeçalhos (ADR-0018)."""

from dataclasses import replace

from fastapi import Request

from adaptadores.rest.erros import ErroHttp
from dominio.modelos import Origem
from portas.autenticacao import Autenticador


def resolver_origem(request: Request, autenticador: Autenticador) -> Origem:
    chave = request.headers.get("x-chave-api")
    autorizacao = request.headers.get("authorization", "")
    if chave:
        origem = autenticador.por_chave(chave)
    elif autorizacao.lower().startswith("bearer "):
        origem = autenticador.por_token_dispositivo(autorizacao[7:].strip())
    else:
        raise ErroHttp(
            401,
            "nao_autenticado",
            "Envie o token do dispositivo (Authorization: Bearer) ou a chave de API (X-Chave-API).",
        )
    if origem is None:
        raise ErroHttp(401, "credencial_invalida", "Credencial inválida ou revogada.")
    # O administrador da plataforma não pertence a um inquilino e escolhe em qual atuar.
    inquilino = request.headers.get("x-inquilino")
    if origem.inquilino is None and origem.papel == "administrador" and inquilino:
        origem = replace(origem, inquilino=inquilino)
    return origem
