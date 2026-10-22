"""Erros HTTP no formato Erro do contrato: {codigo, mensagem, erros?}."""

from fastapi import Request
from fastapi.responses import JSONResponse

from dominio.modelos import ErroDeCampo


class ErroHttp(Exception):
    def __init__(self, status: int, codigo: str, mensagem: str, erros: list[ErroDeCampo] | tuple = ()) -> None:
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo
        self.mensagem = mensagem
        self.erros = erros


def corpo_de_erro(codigo: str, mensagem: str, erros=()) -> dict:
    corpo = {"codigo": codigo, "mensagem": mensagem}
    if erros:
        corpo["erros"] = [{"caminho": erro.caminho, "mensagem": erro.mensagem} for erro in erros]
    return corpo


async def tratar_erro_http(_: Request, erro: ErroHttp) -> JSONResponse:
    return JSONResponse(corpo_de_erro(erro.codigo, erro.mensagem, erro.erros), status_code=erro.status)
