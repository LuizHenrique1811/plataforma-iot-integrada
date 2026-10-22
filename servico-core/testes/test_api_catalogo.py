"""Catálogo, cadastro e consultas pela API, com a aplicação montada pela raiz de composição (em memória)."""

import pytest
from fastapi.testclient import TestClient

from apoio import CONTRATOS, mensagem
from configuracao import Configuracao
from principal import criar_aplicacao

ADMIN = {"X-Chave-API": "admin", "X-Inquilino": "coop-cerrado"}


@pytest.fixture
def cliente():
    with TestClient(criar_aplicacao(Configuracao(contratos_dir=CONTRATOS, chave_admin="admin"))) as cliente:
        yield cliente


def emitir_chave(cliente, papel: str) -> dict:
    resposta = cliente.post("/api/v1/chaves", json={"papel": papel}, headers=ADMIN)
    assert resposta.status_code == 201, resposta.text
    return {"X-Chave-API": resposta.json()["chave"]}


@pytest.fixture
def gestor(cliente):
    assert (
        cliente.post(
            "/api/v1/inquilinos", json={"id": "coop-cerrado", "nome": "Cooperativa"}, headers=ADMIN
        ).status_code
        == 201
    )
    cabecalhos = emitir_chave(cliente, "gestor")
    for caminho, corpo in (
        ("/api/v1/catalogo/dominios", {"id": "agricultura", "nome": "Agricultura"}),
        (
            "/api/v1/catalogo/perfis",
            {
                "id": "sensor-solo",
                "nome": "Sensor de solo",
                "intervalo_envio_s": 900,
                "grandezas": [
                    {"grandeza": "umidade_solo", "unidade": "%", "minimo": 0, "maximo": 100},
                    {"grandeza": "temperatura_solo", "unidade": "Cel"},
                ],
            },
        ),
        ("/api/v1/sites", {"id": "fazenda-boa-vista", "nome": "Fazenda Boa Vista"}),
        ("/api/v1/sites/fazenda-boa-vista/areas", {"id": "talhao-07", "nome": "Talhão 07"}),
    ):
        resposta = cliente.post(caminho, json=corpo, headers=cabecalhos)
        assert resposta.status_code == 201, resposta.text
    return cabecalhos


def cadastrar(cliente, gestor, id_: str = "solo-talhao07-02") -> str:
    corpo = {
        "id": id_,
        "perfil": "sensor-solo",
        "dominio": "agricultura",
        "site": "fazenda-boa-vista",
        "area": "talhao-07",
    }
    resposta = cliente.post("/api/v1/dispositivos", json=corpo, headers=gestor)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["token"]


def test_do_cadastro_a_consulta(cliente, gestor):
    token = cadastrar(cliente, gestor)
    dispositivo = {"Authorization": f"Bearer {token}"}

    carga = mensagem(
        timestamp=None,
        medidas=[{"grandeza": "umidade_solo", "valor": 23.5}, {"grandeza": "temperatura_solo", "valor": 21.8}],
    )
    assert cliente.post("/api/v1/ingestao", json=carga, headers=dispositivo).status_code == 202

    telemetria = cliente.get(
        "/api/v1/dispositivos/solo-talhao07-02/telemetria?grandeza=umidade_solo", headers=gestor
    ).json()
    assert telemetria["total"] == 1
    assert telemetria["itens"][0]["valor"] == 23.5
    assert telemetria["itens"][0]["id_mensagem"] == carga["id_mensagem"]

    estado = cliente.get("/api/v1/dispositivos/solo-talhao07-02/estado", headers=gestor).json()
    assert estado["situacao"] == "online"
    assert {item["grandeza"] for item in estado["grandezas"]} == {"umidade_solo", "temperatura_solo"}

    detalhe = cliente.get("/api/v1/dispositivos/solo-talhao07-02", headers=gestor).json()
    assert (detalhe["inquilino"], detalhe["area"], detalhe["revogado_em"]) == ("coop-cerrado", "talhao-07", None)
    assert "token" not in detalhe

    listagem = cliente.get("/api/v1/dispositivos?site=fazenda-boa-vista", headers=gestor).json()
    assert (listagem["total"], listagem["pagina"], listagem["tamanho"]) == (1, 1, 50)

    # RF-DIS-02: credencial revogada é recusada na conexão seguinte.
    assert cliente.delete("/api/v1/dispositivos/solo-talhao07-02/credencial", headers=gestor).status_code == 204
    assert cliente.post("/api/v1/ingestao", json=mensagem(timestamp=None), headers=dispositivo).status_code == 401


def test_uc06_cenario_novo_de_reservatorios_sem_programar(cliente, gestor):
    # UC-06 / RNF-08: domínio, perfil, local e dispositivo novos só por API.
    for caminho, corpo in (
        ("/api/v1/catalogo/dominios", {"id": "recursos_hidricos", "nome": "Recursos hídricos"}),
        (
            "/api/v1/catalogo/perfis",
            {
                "id": "nivel-reservatorio",
                "nome": "Nível de reservatório",
                "intervalo_envio_s": 1800,
                "grandezas": [{"grandeza": "nivel", "unidade": "m", "minimo": 0, "maximo": 10}],
            },
        ),
        ("/api/v1/sites", {"id": "represa-norte", "nome": "Represa Norte"}),
        (
            "/api/v1/dispositivos",
            {"id": "nivel-01", "perfil": "nivel-reservatorio", "dominio": "recursos_hidricos", "site": "represa-norte"},
        ),
    ):
        resposta = cliente.post(caminho, json=corpo, headers=gestor)
        assert resposta.status_code == 201, resposta.text
    token = resposta.json()["token"]

    carga = mensagem(
        dispositivo="nivel-01", timestamp=None, medidas=[{"grandeza": "nivel", "valor": 420, "unidade": "cm"}]
    )
    assert cliente.post("/api/v1/ingestao", json=carga, headers={"Authorization": f"Bearer {token}"}).status_code == 202
    estado = cliente.get("/api/v1/dispositivos/nivel-01/estado", headers=gestor).json()
    assert estado["grandezas"][0]["valor"] == pytest.approx(4.2)
    assert estado["grandezas"][0]["unidade"] == "m"


def test_operador_nao_cadastra_dispositivo(cliente, gestor):
    # Critério do RF-SEG-02.
    operador = emitir_chave(cliente, "operador")
    corpo = {"id": "x", "perfil": "sensor-solo", "dominio": "agricultura", "site": "fazenda-boa-vista"}
    resposta = cliente.post("/api/v1/dispositivos", json=corpo, headers=operador)
    assert resposta.status_code == 403
    assert resposta.json()["codigo"] == "acesso_negado"
    assert cliente.get("/api/v1/catalogo/dominios", headers=operador).status_code == 200


def test_token_de_dispositivo_nao_gerencia_o_catalogo(cliente, gestor):
    token = cadastrar(cliente, gestor)
    resposta = cliente.get("/api/v1/catalogo/dominios", headers={"Authorization": f"Bearer {token}"})
    assert resposta.status_code == 403


def test_corpo_fora_do_contrato_retorna_400_com_os_erros(cliente, gestor):
    resposta = cliente.post("/api/v1/catalogo/dominios", json={"id": "com espaço"}, headers=gestor)
    assert resposta.status_code == 400
    corpo = resposta.json()
    assert corpo["codigo"] == "dados_invalidos"
    assert {erro["caminho"] for erro in corpo["erros"]} == {"", "/id"}


def test_grandeza_repetida_no_perfil(cliente, gestor):
    grandeza = {"grandeza": "nivel", "unidade": "m"}
    corpo = {"id": "p", "nome": "P", "intervalo_envio_s": 60, "grandezas": [grandeza, grandeza]}
    resposta = cliente.post("/api/v1/catalogo/perfis", json=corpo, headers=gestor)
    assert resposta.status_code == 400
    assert resposta.json()["erros"][0]["caminho"] == "/grandezas/1"


def test_json_invalido_retorna_400(cliente, gestor):
    resposta = cliente.post("/api/v1/sites", content=b"{", headers={**gestor, "Content-Type": "application/json"})
    assert resposta.status_code == 400
    assert resposta.json()["codigo"] == "parametros_invalidos"


def test_identificador_repetido_retorna_409(cliente, gestor):
    resposta = cliente.post("/api/v1/catalogo/dominios", json={"id": "agricultura", "nome": "De novo"}, headers=gestor)
    assert resposta.status_code == 409


def test_area_em_local_inexistente_retorna_404(cliente, gestor):
    assert (
        cliente.post("/api/v1/sites/nao-existe/areas", json={"id": "a", "nome": "A"}, headers=gestor).status_code == 404
    )
    assert cliente.get("/api/v1/sites/nao-existe/areas", headers=gestor).status_code == 404


def test_paginacao_invalida_retorna_400(cliente, gestor):
    assert cliente.get("/api/v1/sites?tamanho=1000", headers=gestor).status_code == 400
    resposta = cliente.get("/api/v1/sites?pagina=abc", headers=gestor)
    assert resposta.status_code == 400
    assert resposta.json()["erros"][0]["caminho"] == "pagina"
    assert cliente.get("/api/v1/sites?ordenar=-senha", headers=gestor).status_code == 400


def test_listagens_com_o_mesmo_envelope(cliente, gestor):
    # RF-APP-07: todas as listagens aceitam os mesmos parâmetros e respondem no mesmo envelope.
    for caminho in (
        "/api/v1/catalogo/dominios",
        "/api/v1/catalogo/perfis",
        "/api/v1/sites",
        "/api/v1/sites/fazenda-boa-vista/areas",
        "/api/v1/dispositivos",
        "/api/v1/rejeitadas",
    ):
        corpo = cliente.get(f"{caminho}?pagina=1&tamanho=10", headers=gestor).json()
        assert set(corpo) == {"itens", "pagina", "tamanho", "total"}, caminho
    inquilinos = cliente.get("/api/v1/inquilinos", headers={"X-Chave-API": "admin"}).json()
    assert inquilinos["itens"] == [{"id": "coop-cerrado", "nome": "Cooperativa"}]


def test_consultas_de_dispositivo_inexistente_retornam_404(cliente, gestor):
    assert cliente.get("/api/v1/dispositivos/nao-existe", headers=gestor).status_code == 404
    assert cliente.get("/api/v1/dispositivos/nao-existe/telemetria", headers=gestor).status_code == 404
    assert cliente.get("/api/v1/dispositivos/nao-existe/estado", headers=gestor).status_code == 404
    assert cliente.delete("/api/v1/dispositivos/nao-existe/credencial", headers=gestor).status_code == 404


def test_rejeitadas_consultadas_pela_api(cliente, gestor):
    token = cadastrar(cliente, gestor)
    cliente.post("/api/v1/ingestao", json=mensagem(id_mensagem="x"), headers={"Authorization": f"Bearer {token}"})
    rejeitadas = cliente.get("/api/v1/rejeitadas", headers=gestor).json()
    assert rejeitadas["total"] == 1
    assert rejeitadas["itens"][0]["motivo"] == "fora_do_contrato"
    assert rejeitadas["itens"][0]["carga"]["id_mensagem"] == "x"


def test_telemetria_com_intervalo_sem_fuso(cliente, gestor):
    cadastrar(cliente, gestor)
    caminho = "/api/v1/dispositivos/solo-talhao07-02/telemetria?inicio=2026-10-19T00:00:00&fim=2026-10-20T00:00:00"
    assert cliente.get(caminho, headers=gestor).json()["total"] == 0
