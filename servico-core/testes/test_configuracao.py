import pytest
from fastapi.testclient import TestClient

from apoio import CONTRATOS, mensagem
from configuracao import Configuracao
from principal import criar_aplicacao


def test_configuracao_padrao_do_ambiente():
    config = Configuracao.do_ambiente({})
    assert config.papel == "central"
    assert config.banco_url is None
    assert (config.contratos_dir / "json-schema").is_dir()


def test_configuracao_lida_do_ambiente():
    config = Configuracao.do_ambiente(
        {"PAPEL": "borda", "BANCO_URL": "postgresql://x", "CONTRATOS_DIR": str(CONTRATOS), "LIMITE_DADO_ATUAL_S": "60"}
    )
    assert (config.papel, config.banco_url, config.limite_dado_atual_s) == ("borda", "postgresql://x", 60)


@pytest.mark.parametrize(("valor", "persistente"), [(None, True), ("1", True), ("0", False), ("false", False)])
def test_sessao_mqtt_das_replicas(valor, persistente):
    ambiente = {"MQTT_GRUPO": "ingestao", "MQTT_TRABALHADORES": "2"}
    if valor is not None:
        ambiente["MQTT_SESSAO_PERSISTENTE"] = valor
    config = Configuracao.do_ambiente(ambiente)
    lidos = (config.mqtt_grupo, config.mqtt_trabalhadores, config.mqtt_sessao_persistente)
    assert lidos == ("ingestao", 2, persistente)


def test_papel_invalido():
    with pytest.raises(ValueError):
        Configuracao.do_ambiente({"PAPEL": "satelite"})


def test_banco_ainda_nao_suportado():
    with pytest.raises(ValueError):
        criar_aplicacao(Configuracao(banco_url="sqlite:///fila.db", contratos_dir=CONTRATOS))


def test_aplicacao_em_memoria_sobe_e_recusa_dispositivo_sem_cadastro():
    app = criar_aplicacao(Configuracao(contratos_dir=CONTRATOS, chave_admin="admin"))
    with TestClient(app) as cliente:
        assert cliente.get("/saude").status_code == 200
        cabecalhos = {"X-Chave-API": "admin", "X-Inquilino": "coop-cerrado"}
        assert cliente.post("/api/v1/ingestao", json=mensagem(), headers=cabecalhos).status_code == 422
