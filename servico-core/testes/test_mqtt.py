"""Consumidor MQTT (RF-ING-01): tópicos, confirmação após gravar e integração com um Mosquitto real."""

import json
import os
import time
import uuid
from types import SimpleNamespace

import pytest

from adaptadores.mqtt import ConsumidorMqtt, interpretar_topico, processar_publicacao
from apoio import mensagem
from dominio.modelos import Motivo, Situacao, TipoOrigem

TOPICO = "coop-cerrado/fazenda-boa-vista/agricultura/solo-talhao07-02/telemetria"
URL_TESTE = os.environ.get("MQTT_URL_TESTE")


def publicacao(carga, topico: str = TOPICO, mid: int = 1, qos: int = 1):
    payload = carga if isinstance(carga, bytes) else json.dumps(carga).encode()
    return SimpleNamespace(topic=topico, payload=payload, mid=mid, qos=qos)


class ClienteFalso:
    def __init__(self) -> None:
        self.confirmadas: list[tuple[int, int]] = []

    def ack(self, mid: int, qos: int) -> None:
        self.confirmadas.append((mid, qos))


def test_topico_canonico():
    origem = interpretar_topico(TOPICO)
    assert origem.tipo is TipoOrigem.MQTT
    assert (origem.inquilino, origem.site, origem.dominio, origem.dispositivo, origem.canal) == (
        "coop-cerrado",
        "fazenda-boa-vista",
        "agricultura",
        "solo-talhao07-02",
        "telemetria",
    )


@pytest.mark.parametrize("topico", ["a/b/c/telemetria", "a/b/c/d/comando", "a//c/d/telemetria", "a/b/c/d/e/telemetria"])
def test_topico_fora_da_convencao(topico, pipeline):
    assert interpretar_topico(topico) is None
    assert processar_publicacao(pipeline, topico, b"{}") is None


def test_publicacao_valida_e_aceita(pipeline, repositorio):
    resultado = processar_publicacao(pipeline, TOPICO, json.dumps(mensagem()).encode())
    assert resultado.situacao is Situacao.ACEITA
    assert repositorio.mensagens[0].site == "fazenda-boa-vista"


def test_publicacao_que_nao_e_json_vai_para_a_dlq(pipeline, rejeitadas):
    resultado = processar_publicacao(pipeline, TOPICO, b"\xff{")
    assert resultado.rejeicao.motivo is Motivo.JSON_INVALIDO
    assert "canal=telemetria" in rejeitadas.itens[0].origem


@pytest.mark.parametrize(
    ("topico", "carga", "motivo"),
    [
        # Tipo da mensagem diferente do canal do tópico.
        (TOPICO.replace("/telemetria", "/evento"), mensagem(), Motivo.TOPICO_DIVERGENTE),
        # Tópico de outro dispositivo.
        (TOPICO.replace("solo-talhao07-02", "outro"), mensagem(), Motivo.DISPOSITIVO_DIVERGENTE),
        # Dispositivo publicando fora do seu local ou domínio (simplificação do RF-SEG-04).
        (TOPICO.replace("fazenda-boa-vista", "fazenda-vizinha"), mensagem(), Motivo.TOPICO_DIVERGENTE),
        (TOPICO.replace("agricultura", "clima"), mensagem(), Motivo.TOPICO_DIVERGENTE),
    ],
)
def test_topico_precisa_corresponder_a_mensagem_e_ao_dispositivo(pipeline, topico, carga, motivo):
    assert processar_publicacao(pipeline, topico, json.dumps(carga).encode()).rejeicao.motivo is motivo


def test_assinaturas_com_e_sem_grupo(pipeline):
    simples = ConsumidorMqtt(pipeline, "mqtt://broker:1883", cliente_id="a")
    assert simples.topicos() == ["+/+/+/+/telemetria", "+/+/+/+/evento", "+/+/+/+/estado"]
    compartilhado = ConsumidorMqtt(pipeline, "mqtt://usuario:senha@broker", cliente_id="b", grupo="nucleo")
    assert compartilhado.topicos()[0] == "$share/nucleo/+/+/+/+/telemetria"


def test_com_grupo_desfaz_as_assinaturas_antigas_da_sessao(pipeline):
    # A sessão persistente guarda as assinaturas sem grupo; mantê-las faria cada mensagem chegar duas vezes.
    class Cliente:
        def __init__(self) -> None:
            self.chamadas = []

        def unsubscribe(self, topicos):
            self.chamadas.append(("desfaz", topicos))

        def subscribe(self, topicos):
            self.chamadas.append(("assina", [topico for topico, _qos in topicos]))

    conectado = SimpleNamespace(is_failure=False)
    compartilhado, cliente = ConsumidorMqtt(pipeline, "mqtt://broker", cliente_id="f", grupo="nucleo"), Cliente()
    compartilhado._ao_conectar(cliente, None, None, conectado, None)
    assert cliente.chamadas == [
        ("desfaz", ["+/+/+/+/telemetria", "+/+/+/+/evento", "+/+/+/+/estado"]),
        ("assina", compartilhado.topicos()),
    ]

    simples, cliente = ConsumidorMqtt(pipeline, "mqtt://broker", cliente_id="g"), Cliente()
    simples._ao_conectar(cliente, None, None, conectado, None)
    assert cliente.chamadas == [("assina", simples.topicos())]


def test_replica_de_sessao_limpa_sai_do_grupo_antes_de_parar(pipeline, repositorio):
    # ADR-0022: uma réplica parada não pode continuar no grupo segurando mensagens; e o que já estava a caminho
    # quando ela pediu para sair ainda é processado e confirmado, porque na sessão limpa nada é reentregue.
    replica = ConsumidorMqtt(pipeline, "mqtt://broker", cliente_id="h", grupo="nucleo", sessao_persistente=False)
    assert replica._cliente._clean_session is True
    chamadas = []

    class Cliente(ClienteFalso):
        def unsubscribe(self, topicos):
            chamadas.append(topicos)
            replica._ao_receber(None, None, publicacao(mensagem(), mid=11))  # chegou antes do UNSUBACK
            replica._ao_desinscrever(None, None, 1, [], None)

        def disconnect(self):
            chamadas.append("desconecta")

        def loop_stop(self):
            pass

    replica._cliente = Cliente()
    replica.parar()
    assert chamadas == [replica.topicos(), "desconecta"]
    assert (len(repositorio.mensagens), replica._cliente.confirmadas) == (1, [(11, 1)])
    assert ConsumidorMqtt(pipeline, "mqtt://broker", cliente_id="i")._cliente._clean_session is False


def test_confirma_so_depois_de_processar(pipeline, repositorio):
    # RNF-10: o PUBACK sai depois da gravação.
    consumidor = ConsumidorMqtt(pipeline, "mqtt://broker", cliente_id="c")
    consumidor._cliente = ClienteFalso()
    consumidor._processar(publicacao(mensagem(), mid=7))
    assert len(repositorio.mensagens) == 1
    assert consumidor._cliente.confirmadas == [(7, 1)]

    consumidor._processar(publicacao(mensagem(), mid=8, qos=0))
    assert consumidor._cliente.confirmadas == [(7, 1)]


def test_falha_ao_gravar_nao_confirma(pipeline, repositorio, monkeypatch):
    def falhar(_mensagem):
        raise ConnectionError("banco fora do ar")

    monkeypatch.setattr(repositorio, "persistir", falhar)
    consumidor = ConsumidorMqtt(pipeline, "mqtt://broker", cliente_id="d")
    consumidor._cliente = ClienteFalso()
    consumidor._processar(publicacao(mensagem(), mid=9))
    assert consumidor._cliente.confirmadas == []


def test_ao_parar_nao_aceita_novas_mensagens(pipeline, repositorio):
    consumidor = ConsumidorMqtt(pipeline, "mqtt://broker", cliente_id="e")
    consumidor._parando = True
    consumidor._ao_receber(None, None, publicacao(mensagem()))
    consumidor._executor.shutdown(wait=True)
    assert repositorio.mensagens == []


@pytest.mark.integracao
@pytest.mark.skipif(not URL_TESTE, reason="MQTT_URL_TESTE não definida")
def test_mensagem_publicada_no_broker_e_persistida_em_ate_2_segundos(pipeline, repositorio):
    # Critério do RF-ING-01 (sem TLS e sem autenticação no broker de teste).
    import paho.mqtt.client as mqtt
    from paho.mqtt.enums import CallbackAPIVersion

    consumidor = ConsumidorMqtt(pipeline, URL_TESTE, cliente_id=f"teste-{uuid.uuid4().hex[:8]}")
    consumidor.iniciar()
    try:
        assert consumidor.inscrito.wait(10), "o consumidor não se inscreveu no broker"
        publicador = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"pub-{uuid.uuid4().hex[:8]}")
        endereco = URL_TESTE.removeprefix("mqtt://").split(":")
        publicador.connect(endereco[0], int(endereco[1]) if len(endereco) > 1 else 1883)
        publicador.loop_start()
        carga = mensagem()
        inicio = time.monotonic()
        publicador.publish(TOPICO, json.dumps(carga), qos=1).wait_for_publish(5)
        while not repositorio.mensagens and time.monotonic() - inicio < 2:
            time.sleep(0.02)
        publicador.loop_stop()
        publicador.disconnect()
        assert [aceita.id_mensagem for aceita in repositorio.mensagens] == [carga["id_mensagem"]]
    finally:
        consumidor.parar()
