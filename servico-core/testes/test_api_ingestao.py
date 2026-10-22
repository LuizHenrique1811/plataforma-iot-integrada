"""API REST de ingestão (RF-ING-02, RF-ING-03) e rotas de operação."""

import json

import pytest
from fastapi.testclient import TestClient

from adaptadores.memoria import AutenticadorEmMemoria
from adaptadores.rest.aplicacao import criar_app
from apoio import CONTRATOS, mensagem

TOKEN_SOLO = {"Authorization": "Bearer token-solo"}
CHAVE_BORDA = {"X-Chave-API": "chave-borda"}


@pytest.fixture
def cliente(pipeline):
    autenticador = AutenticadorEmMemoria(chave_admin="chave-admin")
    autenticador.registrar_token("token-solo", "coop-cerrado", "solo-talhao07-02")
    autenticador.registrar_chave("chave-borda", "coop-cerrado", "no_borda")
    autenticador.registrar_chave("chave-leitor", "coop-cerrado", "leitor")
    app = criar_app(pipeline=pipeline, autenticador=autenticador, contratos_dir=CONTRATOS, papel="central")
    with TestClient(app) as cliente:
        yield cliente


def exemplo(nome: str) -> dict:
    return json.loads((CONTRATOS / "exemplos" / "mensagem" / "validos" / nome).read_text(encoding="utf-8"))


def test_mensagem_valida_retorna_202(cliente):
    carga = exemplo("telemetria-rural-borda.json")
    resposta = cliente.post("/api/v1/ingestao", json=carga, headers=TOKEN_SOLO)
    assert resposta.status_code == 202
    assert resposta.json() == {"situacao": "aceita", "id_mensagem": carga["id_mensagem"]}


def test_reenvio_retorna_202_duplicada(cliente):
    carga = mensagem()
    cliente.post("/api/v1/ingestao", json=carga, headers=TOKEN_SOLO)
    resposta = cliente.post("/api/v1/ingestao", json=carga, headers=TOKEN_SOLO)
    assert resposta.status_code == 202
    assert resposta.json()["situacao"] == "duplicada"


def test_mensagem_invalida_retorna_400_com_a_lista_de_erros(cliente, rejeitadas):
    resposta = cliente.post("/api/v1/ingestao", json=mensagem(id_mensagem="x", tipo="leitura"), headers=TOKEN_SOLO)
    assert resposta.status_code == 400
    corpo = resposta.json()
    assert corpo["codigo"] == "fora_do_contrato"
    assert {erro["caminho"] for erro in corpo["erros"]} >= {"/id_mensagem", "/tipo"}
    assert len(rejeitadas.itens) == 1


def test_corpo_que_nao_e_json_retorna_400_e_vai_para_a_dlq(cliente, rejeitadas):
    resposta = cliente.post(
        "/api/v1/ingestao", content=b"{nao e json", headers={**TOKEN_SOLO, "Content-Type": "application/json"}
    )
    assert resposta.status_code == 400
    assert resposta.json()["codigo"] == "json_invalido"
    assert rejeitadas.itens[0].carga == "{nao e json"


def test_sem_credencial_retorna_401(cliente):
    resposta = cliente.post("/api/v1/ingestao", json=mensagem())
    assert resposta.status_code == 401
    assert resposta.json()["codigo"] == "nao_autenticado"


def test_credencial_invalida_retorna_401(cliente):
    resposta = cliente.post("/api/v1/ingestao", json=mensagem(), headers={"Authorization": "Bearer errado"})
    assert resposta.status_code == 401
    assert resposta.json()["codigo"] == "credencial_invalida"


def test_mensagem_de_outro_dispositivo_retorna_403(cliente):
    resposta = cliente.post("/api/v1/ingestao", json=mensagem(dispositivo="outro"), headers=TOKEN_SOLO)
    assert resposta.status_code == 403
    assert resposta.json()["codigo"] == "dispositivo_divergente"


def test_papel_sem_permissao_retorna_403(cliente):
    resposta = cliente.post("/api/v1/ingestao", json=mensagem(), headers={"X-Chave-API": "chave-leitor"})
    assert resposta.status_code == 403


def test_dispositivo_desconhecido_retorna_422(cliente):
    resposta = cliente.post("/api/v1/ingestao", json=mensagem(dispositivo="nao-existe"), headers=CHAVE_BORDA)
    assert resposta.status_code == 422
    assert resposta.json()["codigo"] == "dispositivo_desconhecido"


def test_administrador_escolhe_o_inquilino_pelo_cabecalho(cliente):
    cabecalhos = {"X-Chave-API": "chave-admin", "X-Inquilino": "coop-cerrado"}
    assert cliente.post("/api/v1/ingestao", json=mensagem(), headers=cabecalhos).status_code == 202


def test_lote_de_5000_com_3_invalidas_grava_4997_e_informa_as_3(cliente):
    # Critério de aceitação do RF-ING-03.
    mensagens = [mensagem() for _ in range(5000)]
    for indice in (10, 2500, 4999):
        mensagens[indice] = mensagem(medidas=[])
    resposta = cliente.post(
        "/api/v1/ingestao/lote", json={"versao": "1.0", "mensagens": mensagens}, headers=CHAVE_BORDA
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert (corpo["total"], corpo["aceitas"], corpo["rejeitadas"]) == (5000, 4997, 3)
    recusadas = [item["indice"] for item in corpo["resultados"] if item["situacao"] == "rejeitada"]
    assert recusadas == [10, 2500, 4999]


def test_lote_exige_chave_de_api(cliente):
    resposta = cliente.post(
        "/api/v1/ingestao/lote", json={"versao": "1.0", "mensagens": [mensagem()]}, headers=TOKEN_SOLO
    )
    assert resposta.status_code == 403


def test_lote_com_envelope_invalido_retorna_400(cliente):
    resposta = cliente.post("/api/v1/ingestao/lote", json={"mensagens": []}, headers=CHAVE_BORDA)
    assert resposta.status_code == 400
    assert resposta.json()["codigo"] == "fora_do_contrato"


def test_lote_que_nao_e_json_retorna_400(cliente):
    resposta = cliente.post(
        "/api/v1/ingestao/lote", content=b"[", headers={**CHAVE_BORDA, "Content-Type": "application/json"}
    )
    assert resposta.status_code == 400


def test_saude(cliente):
    assert cliente.get("/saude").json() == {"situacao": "ok", "papel": "central", "versao": "0.3.0"}


def test_contratos_publicados_e_documentacao_interativa(cliente):
    # RF-INT-01 e RF-APP-01 (ADR-0019).
    assert cliente.get("/contratos/openapi.yaml").status_code == 200
    assert cliente.get("/contratos/json-schema/mensagem-canonica-1.0.json").json()["title"] == "Mensagem canônica"
    documentacao = cliente.get("/docs")
    assert documentacao.status_code == 200
    assert "/contratos/openapi.yaml" in documentacao.text


def test_metricas_no_formato_prometheus(cliente):
    # RF-OBS-01
    cliente.post("/api/v1/ingestao", json=mensagem(), headers=TOKEN_SOLO)
    resposta = cliente.get("/metrics")
    assert resposta.status_code == 200
    assert 'iot_mensagens_total{entrada="http",motivo="",situacao="aceita"}' in resposta.text
    assert "iot_ingestao_duracao_segundos_bucket" in resposta.text
