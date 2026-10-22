"""Um teste automatizado por tipo de ação do motor de regras (critério do RF-PRO-03)."""

import json
import logging
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from adaptadores.acoes import ClienteWebhookHttp, NotificadorEmLog, PublicadorEmLog
from adaptadores.agendador import TarefaPeriodica
from apoio import ORIGEM_SOLO, mensagem, regra
from dominio.modelos import DispositivoCadastrado
from dominio.regras import Acao, EstadoAlarme, Severidade, TipoAcao


def disparar(regras_env, *acoes):
    regras_env.regras.inserir_regra("coop-cerrado", regra(acoes=list(acoes)))
    carga = mensagem(timestamp=None, medidas=[{"grandeza": "umidade_solo", "valor": 12.5}])
    regras_env.pipeline.processar(carga, ORIGEM_SOLO)


def test_acao_alarme(regras_env):
    disparar(regras_env, Acao(TipoAcao.ALARME, Severidade.CRITICO, mensagem="Solo seco no talhão 07"))
    [alarme] = regras_env.alarmes.alarmes.values()
    assert (alarme.estado, alarme.severidade, alarme.mensagem, alarme.origem) == (
        EstadoAlarme.ATIVO,
        Severidade.CRITICO,
        "Solo seco no talhão 07",
        "central",
    )


def test_acao_notificar(regras_env):
    disparar(regras_env, Acao(TipoAcao.NOTIFICAR, mensagem="Irrigar o talhão 07", canal="sms"))
    [(inquilino, canal, texto, contexto)] = regras_env.saidas.notificador.notificacoes
    assert (inquilino, canal, texto) == ("coop-cerrado", "sms", "Irrigar o talhão 07")
    assert contexto["valor"] == 12.5


def test_acao_comando_vai_para_o_dispositivo_de_destino(regras_env, catalogo, validador):
    # UC-01: o sensor de solo dispara e o comando vai para a válvula de irrigação.
    catalogo.adicionar_dispositivo(
        DispositivoCadastrado("coop-cerrado", "valvula-talhao07", "sensor-solo", "agricultura", "fazenda-boa-vista")
    )
    comando = {"nome": "abrir", "parametros": {"minutos": 30}}
    disparar(regras_env, Acao(TipoAcao.COMANDO, comando=comando, dispositivo="valvula-talhao07"))
    [(topico, carga)] = regras_env.saidas.publicador.publicadas
    assert topico == "coop-cerrado/fazenda-boa-vista/agricultura/valvula-talhao07/comando"
    assert (carga["tipo"], carga["dispositivo"], carga["comando"]) == ("comando", "valvula-talhao07", comando)
    assert validador.validar(carga) == []  # o comando segue o contrato canônico


def test_acao_comando_sem_destino_cadastrado_nao_publica(regras_env):
    disparar(regras_env, Acao(TipoAcao.COMANDO, comando={"nome": "abrir"}, dispositivo="nao-existe"))
    assert regras_env.saidas.publicador.publicadas == []


def test_acao_webhook(regras_env):
    disparar(regras_env, Acao(TipoAcao.WEBHOOK, url="https://rotas.exemplo/coleta"))
    [(url, carga)] = regras_env.saidas.webhook.chamadas
    assert url == "https://rotas.exemplo/coleta"
    assert (carga["regra"], carga["dispositivo"], carga["grandeza"]) == (
        "umidade-baixa",
        "solo-talhao07-02",
        "umidade_solo",
    )


def test_acao_publicar_em_topico(regras_env):
    disparar(regras_env, Acao(TipoAcao.PUBLICAR, topico="coop-cerrado/eventos/umidade"))
    [(topico, carga)] = regras_env.saidas.publicador.publicadas
    assert topico == "coop-cerrado/eventos/umidade"
    assert carga["area"] == "talhao-07"


def test_cliente_webhook_faz_post_com_o_disparo():
    recebidos = []

    class Receptor(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - nome exigido pelo http.server
            tamanho = int(self.headers["Content-Length"])
            recebidos.append((self.path, self.headers["Content-Type"], json.loads(self.rfile.read(tamanho))))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_):
            pass

    servidor = HTTPServer(("127.0.0.1", 0), Receptor)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        cliente = ClienteWebhookHttp(assincrono=False)
        cliente.enviar(f"http://127.0.0.1:{servidor.server_port}/alarmes", {"regra": "r1"})
        cliente.enviar("http://127.0.0.1:1/fora-do-ar", {"regra": "r1"})  # falha registrada, sem exceção
    finally:
        servidor.shutdown()
    assert recebidos == [("/alarmes", "application/json", {"regra": "r1"})]


def test_cliente_webhook_assincrono_nao_bloqueia():
    cliente = ClienteWebhookHttp(tempo_limite_s=0.5)
    inicio = time.monotonic()
    cliente.enviar("http://10.255.255.1/lento", {"regra": "r1"})
    assert time.monotonic() - inicio < 0.2
    cliente.encerrar()


def test_notificacao_e_publicacao_sem_broker_vao_para_o_log(caplog):
    with caplog.at_level(logging.WARNING):
        NotificadorEmLog().notificar("coop-cerrado", "sms", "Silo 2 acima de 30 °C", {"dispositivo": "silo-02"})
        PublicadorEmLog().publicar("coop-cerrado/x", {})
    assert "notificação [sms]: Silo 2 acima de 30 °C" in caplog.text
    assert "publicação descartada" in caplog.text


def test_tarefa_periodica_continua_depois_de_uma_falha():
    chamadas = []
    evento = threading.Event()

    def trabalho():
        chamadas.append(1)
        if len(chamadas) == 1:
            raise RuntimeError("falha passageira")
        evento.set()

    tarefa = TarefaPeriodica("teste", 0.01, trabalho)
    tarefa.iniciar()
    assert evento.wait(2)
    tarefa.parar()
    assert len(chamadas) >= 2


@pytest.mark.integracao
@pytest.mark.skipif(not os.environ.get("MQTT_URL_TESTE"), reason="MQTT_URL_TESTE não definida")
def test_publicador_mqtt_entrega_no_broker():
    import paho.mqtt.client as mqtt
    from paho.mqtt.enums import CallbackAPIVersion

    from adaptadores.mqtt import PublicadorMqtt

    url = os.environ["MQTT_URL_TESTE"]
    host, porta = url.removeprefix("mqtt://").split(":")
    topico = f"coop-cerrado/teste/{uuid.uuid4().hex[:8]}"
    recebidas, inscrito = [], threading.Event()
    assinante = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"sub-{uuid.uuid4().hex[:8]}")
    assinante.on_subscribe = lambda *_: inscrito.set()
    assinante.on_message = lambda _c, _d, msg: recebidas.append(json.loads(msg.payload))
    assinante.connect(host, int(porta))
    assinante.loop_start()
    assinante.subscribe(topico, qos=1)
    assert inscrito.wait(5)

    publicador = PublicadorMqtt(url, cliente_id=f"pub-{uuid.uuid4().hex[:8]}")
    publicador.iniciar()
    try:
        publicador.publicar(topico, {"regra": "r1"})
        prazo = time.monotonic() + 5
        while not recebidas and time.monotonic() < prazo:
            time.sleep(0.02)
    finally:
        publicador.parar()
        assinante.loop_stop()
        assinante.disconnect()
    assert recebidas == [{"regra": "r1"}]


@pytest.mark.parametrize(("intervalo", "verifica"), [(30.0, True), (0, False)])
def test_so_uma_replica_verifica_ausencias(intervalo, verifica):
    # ADR-0022: com várias réplicas, as extras desligam a verificação para não notificar em dobro.
    from fastapi.testclient import TestClient

    from configuracao import Configuracao, localizar_contratos
    from principal import montar_servico

    servico = montar_servico(Configuracao(contratos_dir=localizar_contratos(), verificacao_ausencia_s=intervalo))
    with TestClient(servico.app):
        tarefas = {thread.name for thread in threading.enumerate()}
    assert ("verificacao-ausencia" in tarefas) is verifica
