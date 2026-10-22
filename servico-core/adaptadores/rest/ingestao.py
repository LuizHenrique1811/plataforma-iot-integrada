"""Rotas de ingestão: POST /api/v1/ingestao e POST /api/v1/ingestao/lote (RF-ING-02, RF-ING-03)."""

import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from adaptadores.observabilidade import observar
from adaptadores.rest.autenticacao import resolver_origem
from adaptadores.rest.erros import ErroHttp, corpo_de_erro
from dominio.modelos import Etapa, Motivo, ResultadoIngestao, Situacao, TipoOrigem
from dominio.pipeline import PipelineDeIngestao
from portas.autenticacao import Autenticador

_STATUS_POR_ETAPA = {Etapa.VALIDACAO: 400, Etapa.AUTORIZACAO: 403, Etapa.ENRIQUECIMENTO: 422}

_MENSAGENS = {
    Motivo.JSON_INVALIDO: "O corpo não é um JSON válido.",
    Motivo.FORA_DO_CONTRATO: "A mensagem não segue o contrato da sua versão.",
    Motivo.VERSAO_NAO_SUPORTADA: "Versão da mensagem não suportada.",
    Motivo.ORIGEM_NAO_AUTORIZADA: "A credencial não pode enviar mensagens.",
    Motivo.DISPOSITIVO_DIVERGENTE: "A mensagem é de outro dispositivo.",
    Motivo.DISPOSITIVO_DESCONHECIDO: "Dispositivo não cadastrado no inquilino.",
    Motivo.PERFIL_DESCONHECIDO: "O perfil do dispositivo não existe.",
    Motivo.CREDENCIAL_REVOGADA: "A credencial do dispositivo foi revogada antes da medição.",
    Motivo.TIPO_NAO_ACEITO: "Esse tipo de mensagem não é aceito na ingestão.",
    Motivo.GRANDEZA_FORA_DO_PERFIL: "Grandeza não definida no perfil do dispositivo.",
    Motivo.UNIDADE_INCOMPATIVEL: "Unidade sem conversão para a unidade do perfil.",
    Motivo.TOPICO_DIVERGENTE: "O tópico MQTT não corresponde à mensagem ou ao dispositivo.",
}


def criar_rotas_de_ingestao(pipeline: PipelineDeIngestao, autenticador: Autenticador) -> APIRouter:
    rotas = APIRouter(tags=["ingestao"])

    @rotas.post("/api/v1/ingestao")
    async def ingerir_mensagem(request: Request) -> JSONResponse:
        origem = resolver_origem(request, autenticador)
        corpo = await request.body()
        inicio = time.perf_counter()
        try:
            carga = json.loads(corpo)
        except ValueError as erro:
            texto = corpo.decode("utf-8", errors="replace")
            resultado = await run_in_threadpool(pipeline.registrar_carga_ilegivel, texto, origem, str(erro))
        else:
            resultado = await run_in_threadpool(pipeline.processar, carga, origem)
        observar(resultado, "http", time.perf_counter() - inicio)
        if resultado.situacao is Situacao.REJEITADA:
            rejeicao = resultado.rejeicao
            return JSONResponse(
                corpo_de_erro(rejeicao.motivo.value, _MENSAGENS[rejeicao.motivo], rejeicao.erros),
                status_code=_STATUS_POR_ETAPA[rejeicao.etapa],
            )
        return JSONResponse(_resultado_json(resultado), status_code=202)

    @rotas.post("/api/v1/ingestao/lote")
    async def ingerir_lote(request: Request) -> JSONResponse:
        origem = resolver_origem(request, autenticador)
        if origem.tipo is not TipoOrigem.CHAVE:
            raise ErroHttp(403, "origem_nao_autorizada", "Lotes exigem chave de API (nó de borda ou integração).")
        try:
            carga = json.loads(await request.body())
        except ValueError as erro:
            raise ErroHttp(400, Motivo.JSON_INVALIDO.value, f"O corpo não é um JSON válido: {erro}") from erro
        inicio = time.perf_counter()
        lote = await run_in_threadpool(pipeline.processar_lote, carga, origem)
        if lote.erros_envelope:
            return JSONResponse(
                corpo_de_erro(
                    Motivo.FORA_DO_CONTRATO.value, "O envelope do lote não segue o contrato.", lote.erros_envelope
                ),
                status_code=400,
            )
        duracao_media = (time.perf_counter() - inicio) / max(len(lote.resultados), 1)
        for resultado in lote.resultados:
            observar(resultado, "lote", duracao_media)
        return JSONResponse(
            {
                "total": len(lote.resultados),
                "aceitas": lote.contar(Situacao.ACEITA),
                "duplicadas": lote.contar(Situacao.DUPLICADA),
                "rejeitadas": lote.contar(Situacao.REJEITADA),
                "resultados": [
                    {"indice": indice, **_resultado_json(resultado)} for indice, resultado in enumerate(lote.resultados)
                ],
            }
        )

    return rotas


def _resultado_json(resultado: ResultadoIngestao) -> dict:
    corpo: dict = {"situacao": resultado.situacao.value}
    if resultado.id_mensagem:
        corpo["id_mensagem"] = resultado.id_mensagem
    if resultado.rejeicao:
        corpo["etapa"] = resultado.rejeicao.etapa.value
        corpo["motivo"] = resultado.rejeicao.motivo.value
        corpo["erros"] = [{"caminho": erro.caminho, "mensagem": erro.mensagem} for erro in resultado.rejeicao.erros]
    return corpo
