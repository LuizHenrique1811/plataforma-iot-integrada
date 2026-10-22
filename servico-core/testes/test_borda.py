"""Nó de borda montado pela raiz de composição: API local, regra local sem link e eventos para a central (RF-EDG-03)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from test_sincronizacao import CentralFalsa

from adaptadores.contrato_jsonschema import ValidadorJsonSchema
from apoio import CONTRATOS, mensagem
from configuracao import Configuracao
from principal import montar_servico

ADMIN = {"X-Chave-API": "admin-borda", "X-Inquilino": "coop-cerrado"}


@pytest.fixture
def central():
    return CentralFalsa()


@pytest.fixture
def borda(tmp_path, central):
    chave = tmp_path / "segredos" / "chave-fila"
    chave.parent.mkdir()
    chave.write_text("segredo da fazenda", encoding="utf-8")
    config = Configuracao(
        papel="borda",
        banco_url=f"sqlite:///{tmp_path / 'dados' / 'borda.db'}",
        borda_id="borda-fazenda-boa-vista",
        chave_fila_arquivo=str(chave),
        chave_admin="admin-borda",
        contratos_dir=CONTRATOS,
        sincronizacao_s=3600,
    )
    servico = montar_servico(config, cliente_da_central=central)
    with TestClient(servico.app) as cliente:
        servico.cliente = cliente
        yield servico


def montar_catalogo(cliente) -> str:
    cliente.post("/api/v1/inquilinos", json={"id": "coop-cerrado", "nome": "Cooperativa"}, headers=ADMIN)
    for caminho, corpo in (
        ("/api/v1/catalogo/dominios", {"id": "agricultura", "nome": "Agricultura"}),
        ("/api/v1/catalogo/perfis", {"id": "sensor-solo", "nome": "Sensor de solo", "intervalo_envio_s": 900,
                                     "grandezas": [{"grandeza": "umidade_solo", "unidade": "%"}]}),
        ("/api/v1/sites", {"id": "fazenda-boa-vista", "nome": "Fazenda Boa Vista"}),
        ("/api/v1/sites/fazenda-boa-vista/areas", {"id": "talhao-07", "nome": "Talhão 07"}),
        ("/api/v1/dispositivos", {"id": "valvula-talhao07", "perfil": "sensor-solo", "dominio": "agricultura",
                                  "site": "fazenda-boa-vista", "area": "talhao-07"}),
        ("/api/v1/regras", {
            "id": "irrigacao-talhao07", "nome": "Irrigar com solo seco", "ambito": "borda",
            "condicao": {"tipo": "limite", "grandeza": "umidade_solo", "operador": "<", "valor": 20,
                         "area": "talhao-07"},
            "acoes": [{"tipo": "alarme", "severidade": "critico", "mensagem": "Solo seco no talhão 07"},
                      {"tipo": "comando", "dispositivo": "valvula-talhao07", "comando": {"nome": "abrir"}}],
        }),
    ):  # fmt: skip
        assert cliente.post(caminho, json=corpo, headers=ADMIN).status_code == 201
    resposta = cliente.post(
        "/api/v1/dispositivos",
        json={"id": "solo-talhao07-02", "perfil": "sensor-solo", "dominio": "agricultura",
              "site": "fazenda-boa-vista", "area": "talhao-07"},
        headers=ADMIN,
    )  # fmt: skip
    return resposta.json()["token"]


def test_regra_local_dispara_sem_link_e_o_evento_sincroniza_depois(borda, central):
    # Critério do RF-EDG-03: a regra de irrigação dispara com o link desligado; o evento é sincronizado depois.
    central.conectada = False
    token = montar_catalogo(borda.cliente)
    agora = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    seca = mensagem(timestamp=agora, medidas=[{"grandeza": "umidade_solo", "valor": 14.2}])
    resposta = borda.cliente.post("/api/v1/ingestao", json=seca, headers={"Authorization": f"Bearer {token}"})
    assert resposta.status_code == 202

    [alarme] = borda.cliente.get("/api/v1/alarmes", headers=ADMIN).json()["itens"]
    assert (alarme["origem"], alarme["severidade"]) == ("borda", "critico")
    assert borda.fila.pendentes() == 3  # telemetria, evento de alarme e evento de comando
    assert borda.sincronizador.sincronizar().erro == "link desligado"

    central.conectada = True
    resultado = borda.sincronizador.sincronizar()
    assert (resultado.enviadas, resultado.pendentes) == (3, 0)
    enviadas = list(central.gravadas.values())
    # Eventos saem primeiro (RF-EDG-05), todos no contrato canônico e com a borda no campo via.
    assert [carga["tipo"] for carga in enviadas] == ["evento", "evento", "telemetria"]
    assert {carga["evento"]["nome"] for carga in enviadas[:2]} == {"alarme", "comando_enviado"}
    validador = ValidadorJsonSchema(CONTRATOS)
    assert all(validador.validar(carga) == [] for carga in enviadas)
    assert {carga["via"] for carga in enviadas} == {"borda-fazenda-boa-vista"}
    evento_alarme = next(c for c in enviadas if c["tipo"] == "evento" and c["evento"]["nome"] == "alarme")
    assert evento_alarme["timestamp"] == agora  # o horário em que a regra disparou (RF-PRO-05)
    assert evento_alarme["evento"]["detalhes"]["regra"] == "irrigacao-talhao07"


def test_regras_da_central_nao_rodam_na_borda(borda):
    token = montar_catalogo(borda.cliente)
    corpo = {"id": "so-na-central", "nome": "Central", "ambito": "central",
             "condicao": {"tipo": "limite", "grandeza": "umidade_solo", "operador": "<", "valor": 99},
             "acoes": [{"tipo": "alarme"}]}  # fmt: skip
    borda.cliente.post("/api/v1/regras", json=corpo, headers=ADMIN)
    carga = mensagem(timestamp=None, medidas=[{"grandeza": "umidade_solo", "valor": 50}])
    borda.cliente.post("/api/v1/ingestao", json=carga, headers={"Authorization": f"Bearer {token}"})
    assert borda.cliente.get("/api/v1/alarmes", headers=ADMIN).json()["total"] == 0


def test_saude_informa_o_papel(borda):
    assert borda.cliente.get("/saude").json()["papel"] == "borda"


@pytest.mark.parametrize(
    ("campos", "mensagem_de_erro"),
    [({"banco_url": None}, "sqlite"), ({"borda_id": None}, "BORDA_ID")],
)
def test_configuracao_obrigatoria_da_borda(tmp_path, campos, mensagem_de_erro):
    base = {
        "papel": "borda",
        "banco_url": f"sqlite:///{tmp_path / 'b.db'}",
        "borda_id": "b",
        "contratos_dir": CONTRATOS,
    }
    with pytest.raises(ValueError, match=mensagem_de_erro):
        montar_servico(Configuracao(**{**base, **campos}))


def test_borda_sem_central_configurada_so_acumula(tmp_path):
    config = Configuracao(
        papel="borda", banco_url=f"sqlite:///{tmp_path / 'b.db'}", borda_id="b", contratos_dir=CONTRATOS
    )
    assert montar_servico(config).sincronizador is None


def test_recurso_repetido_na_borda_responde_409(borda):
    montar_catalogo(borda.cliente)
    resposta = borda.cliente.post("/api/v1/inquilinos", json={"id": "coop-cerrado", "nome": "De novo"}, headers=ADMIN)
    assert (resposta.status_code, resposta.json()["codigo"]) == (409, "ja_existe")


def test_alarme_local_se_resolve_na_borda_e_avisa_a_central(borda, central):
    token = {"Authorization": f"Bearer {montar_catalogo(borda.cliente)}"}
    for valor in (14.0, 35.0):  # seca e depois volta a ter umidade
        carga = mensagem(timestamp=None, medidas=[{"grandeza": "umidade_solo", "valor": valor}])
        assert borda.cliente.post("/api/v1/ingestao", json=carga, headers=token).status_code == 202

    [alarme] = borda.cliente.get("/api/v1/alarmes", headers=ADMIN).json()["itens"]
    assert alarme["estado"] == "resolvido"
    borda.sincronizador.sincronizar()
    eventos = [carga["evento"]["nome"] for carga in central.gravadas.values() if carga["tipo"] == "evento"]
    assert eventos == ["alarme", "comando_enviado", "alarme_resolvido"]
    resolvido = next(c for c in central.gravadas.values() if c.get("evento", {}).get("nome") == "alarme_resolvido")
    assert ValidadorJsonSchema(CONTRATOS).validar(resolvido) == []
    assert resolvido["evento"]["detalhes"] == {"regra": "irrigacao-talhao07"}
