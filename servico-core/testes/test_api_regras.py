"""Regras e alarmes pela API, com a aplicação montada pela raiz de composição (UC-02, UC-04, RF-PRO-05)."""

import json
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from apoio import CONTRATOS, mensagem
from configuracao import Configuracao
from principal import criar_aplicacao

ADMIN = {"X-Chave-API": "admin", "X-Inquilino": "coop-cerrado"}


def instante(segundos_atras: float) -> str:
    return (datetime.now(UTC) - timedelta(seconds=segundos_atras)).isoformat().replace("+00:00", "Z")


@pytest.fixture
def cliente():
    with TestClient(criar_aplicacao(Configuracao(contratos_dir=CONTRATOS, chave_admin="admin"))) as cliente:
        yield cliente


def chave(cliente, papel: str) -> dict:
    return {"X-Chave-API": cliente.post("/api/v1/chaves", json={"papel": papel}, headers=ADMIN).json()["chave"]}


@pytest.fixture
def gestor(cliente):
    cliente.post("/api/v1/inquilinos", json={"id": "coop-cerrado", "nome": "Cooperativa"}, headers=ADMIN)
    cabecalhos = chave(cliente, "gestor")
    for caminho, corpo in (
        ("/api/v1/catalogo/dominios", {"id": "armazenagem", "nome": "Armazenagem"}),
        ("/api/v1/catalogo/dominios", {"id": "residuos", "nome": "Resíduos"}),
        (
            "/api/v1/catalogo/perfis",
            {
                "id": "termometria-silo",
                "nome": "Termometria de silo",
                "intervalo_envio_s": 900,
                "grandezas": [{"grandeza": "temperatura_graos", "unidade": "Cel", "minimo": -10, "maximo": 80}],
            },
        ),
        (
            "/api/v1/catalogo/perfis",
            {
                "id": "lixeira",
                "nome": "Lixeira com sensor de nível",
                "intervalo_envio_s": 600,
                "grandezas": [{"grandeza": "nivel_enchimento", "unidade": "%", "minimo": 0, "maximo": 100}],
            },
        ),
        ("/api/v1/sites", {"id": "fazenda-boa-vista", "nome": "Fazenda Boa Vista"}),
        ("/api/v1/sites/fazenda-boa-vista/areas", {"id": "silo-2", "nome": "Silo 2"}),
    ):
        assert cliente.post(caminho, json=corpo, headers=cabecalhos).status_code == 201
    return cabecalhos


def cadastrar(cliente, gestor, id_: str, perfil: str, dominio: str) -> dict:
    corpo = {"id": id_, "perfil": perfil, "dominio": dominio, "site": "fazenda-boa-vista"}
    resposta = cliente.post("/api/v1/dispositivos", json=corpo, headers=gestor)
    assert resposta.status_code == 201, resposta.text
    return {"Authorization": f"Bearer {resposta.json()['token']}"}


def enviar(cliente, token: dict, dispositivo: str, grandeza: str, valor: float, segundos_atras: float) -> None:
    carga = mensagem(
        dispositivo=dispositivo, timestamp=instante(segundos_atras), medidas=[{"grandeza": grandeza, "valor": valor}]
    )
    assert cliente.post("/api/v1/ingestao", json=carga, headers=token).status_code == 202


def test_uc02_alarme_de_temperatura_em_silo(cliente, gestor, caplog):
    # UC-02: "temperatura > 30 °C por 30 minutos -> alarme crítico + SMS" (janela de 60 s no teste).
    token = cadastrar(cliente, gestor, "silo-02", "termometria-silo", "armazenagem")
    corpo = {
        "id": "silo-quente",
        "nome": "Silo acima de 30 °C",
        "condicao": {"tipo": "janela", "grandeza": "temperatura_graos", "operador": ">", "valor": 30, "duracao_s": 60},
        "acoes": [
            {"tipo": "alarme", "severidade": "critico"},
            {"tipo": "notificar", "canal": "sms", "mensagem": "Silo 2 acima de 30 °C"},
        ],
    }
    criada = cliente.post("/api/v1/regras", json=corpo, headers=gestor)
    assert criada.status_code == 201, criada.text
    assert criada.json() == {**corpo, "ambito": "central", "ativa": True}

    enviar(cliente, token, "silo-02", "temperatura_graos", 31.0, segundos_atras=120)
    assert cliente.get("/api/v1/alarmes", headers=gestor).json()["total"] == 0
    inicio = time.monotonic()
    enviar(cliente, token, "silo-02", "temperatura_graos", 32.5, segundos_atras=30)
    assert time.monotonic() - inicio < 3  # RF-PRO-02: dispara em até 3 s

    [alarme] = cliente.get("/api/v1/alarmes?estado=ativo", headers=gestor).json()["itens"]
    assert (alarme["regra"], alarme["severidade"], alarme["dispositivo"], alarme["origem"]) == (
        "silo-quente",
        "critico",
        "silo-02",
        "central",
    )
    assert "notificação [sms]: Silo 2 acima de 30 °C" in caplog.text

    operador = chave(cliente, "operador")
    reconhecido = cliente.post(f"/api/v1/alarmes/{alarme['id']}/reconhecer", headers=operador)
    assert reconhecido.json()["estado"] == "reconhecido"
    assert cliente.post(f"/api/v1/alarmes/{alarme['id']}/reconhecer", headers=operador).status_code == 409
    resolvido = cliente.post(f"/api/v1/alarmes/{alarme['id']}/resolver", headers=operador).json()
    assert (resolvido["estado"], resolvido["resolvido_em"] is not None) == ("resolvido", True)


def test_uc04_lixeira_cheia_com_webhook_e_resolucao_automatica(cliente, gestor):
    # UC-04: "nível > 80% por 10 minutos -> alarme + webhook"; o nível cai e o alarme é resolvido.
    recebidos, chegou = [], threading.Event()

    class SistemaDeRotas(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            recebidos.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.end_headers()
            chegou.set()

        def log_message(self, *_):
            pass

    servidor = HTTPServer(("127.0.0.1", 0), SistemaDeRotas)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        token = cadastrar(cliente, gestor, "lixeira-17", "lixeira", "residuos")
        corpo = {
            "id": "lixeira-cheia",
            "nome": "Lixeira cheia",
            "condicao": {
                "tipo": "janela",
                "grandeza": "nivel_enchimento",
                "operador": ">",
                "valor": 80,
                "duracao_s": 60,
                "dominio": "residuos",
            },
            "acoes": [
                {"tipo": "alarme", "severidade": "aviso"},
                {"tipo": "webhook", "url": f"http://127.0.0.1:{servidor.server_port}/rotas"},
            ],
        }
        assert cliente.post("/api/v1/regras", json=corpo, headers=gestor).status_code == 201
        enviar(cliente, token, "lixeira-17", "nivel_enchimento", 85, segundos_atras=90)
        enviar(cliente, token, "lixeira-17", "nivel_enchimento", 90, segundos_atras=20)
        assert chegou.wait(5), "o webhook não chegou ao sistema de rotas"
        assert (recebidos[0]["regra"], recebidos[0]["dispositivo"], recebidos[0]["valor"]) == (
            "lixeira-cheia",
            "lixeira-17",
            90.0,
        )

        enviar(cliente, token, "lixeira-17", "nivel_enchimento", 5, segundos_atras=1)
        [alarme] = cliente.get("/api/v1/alarmes", headers=gestor).json()["itens"]
        assert alarme["estado"] == "resolvido"
    finally:
        servidor.shutdown()


def test_dado_atrasado_nao_gera_alarme_pela_api(cliente, gestor):
    # RF-ING-04
    token = cadastrar(cliente, gestor, "silo-02", "termometria-silo", "armazenagem")
    corpo = {
        "id": "r",
        "nome": "R",
        "condicao": {"tipo": "limite", "grandeza": "temperatura_graos", "operador": ">", "valor": 30},
        "acoes": [{"tipo": "alarme"}],
    }
    cliente.post("/api/v1/regras", json=corpo, headers=gestor)
    enviar(cliente, token, "silo-02", "temperatura_graos", 45, segundos_atras=48 * 3600)
    assert cliente.get("/api/v1/alarmes", headers=gestor).json()["total"] == 0
    assert cliente.get("/api/v1/dispositivos/silo-02/telemetria", headers=gestor).json()["total"] == 1


def test_regra_fora_do_contrato_ou_inconsistente(cliente, gestor):
    fora = {"id": "r", "nome": "R", "condicao": {"tipo": "media", "grandeza": "x"}, "acoes": []}
    resposta = cliente.post("/api/v1/regras", json=fora, headers=gestor)
    assert resposta.status_code == 400
    assert {erro["caminho"] for erro in resposta.json()["erros"]} == {"/condicao/tipo", "/acoes"}

    sem_operador = {
        "id": "r",
        "nome": "R",
        "condicao": {"tipo": "limite", "grandeza": "x"},
        "acoes": [{"tipo": "alarme"}],
    }
    resposta = cliente.post("/api/v1/regras", json=sem_operador, headers=gestor)
    assert resposta.status_code == 400
    assert {erro["caminho"] for erro in resposta.json()["erros"]} == {"/condicao/operador", "/condicao/valor"}


def test_papeis_em_regras_e_alarmes(cliente, gestor):
    corpo = {
        "id": "r",
        "nome": "R",
        "condicao": {"tipo": "limite", "grandeza": "x", "operador": ">", "valor": 1},
        "acoes": [{"tipo": "alarme"}],
    }
    operador = chave(cliente, "operador")
    assert cliente.post("/api/v1/regras", json=corpo, headers=operador).status_code == 403
    assert cliente.post("/api/v1/regras", json=corpo, headers=gestor).status_code == 201
    assert cliente.post("/api/v1/regras", json=corpo, headers=gestor).status_code == 409
    assert cliente.get("/api/v1/regras", headers=operador).json()["itens"][0]["id"] == "r"
    leitor = chave(cliente, "leitor")
    assert cliente.post("/api/v1/alarmes/qualquer/reconhecer", headers=leitor).status_code == 403


def test_alarme_inexistente_e_filtro_invalido(cliente, gestor):
    assert cliente.post("/api/v1/alarmes/nao-existe/resolver", headers=gestor).status_code == 404
    assert cliente.get("/api/v1/alarmes?estado=quebrado", headers=gestor).status_code == 400
