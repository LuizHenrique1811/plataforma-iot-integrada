"""Consumidor MQTT da ingestão (RF-ING-01).

Assina os tópicos canônicos {inquilino}/{site}/{dominio}/{dispositivo}/{canal} (asyncapi.yaml) com
sessão persistente e confirma cada mensagem (PUBACK) só depois de gravá-la (RNF-10). Enquanto o
serviço está fora, o broker guarda as mensagens da sessão; o que chegar repetido é descartado pela
deduplicação.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from adaptadores.observabilidade import observar
from dominio.modelos import Origem, ResultadoIngestao, TipoOrigem
from dominio.pipeline import PipelineDeIngestao

CANAIS = ("telemetria", "evento", "estado")

log = logging.getLogger("servico_core.mqtt")


def interpretar_topico(topico: str) -> Origem | None:
    partes = topico.split("/")
    if len(partes) != 5 or partes[4] not in CANAIS or not all(partes):
        return None
    inquilino, site, dominio, dispositivo, canal = partes
    return Origem(TipoOrigem.MQTT, inquilino, dispositivo=dispositivo, site=site, dominio=dominio, canal=canal)


def processar_publicacao(pipeline: PipelineDeIngestao, topico: str, payload: bytes) -> ResultadoIngestao | None:
    origem = interpretar_topico(topico)
    if origem is None:
        log.warning("tópico fora da convenção ignorado: %s", topico, extra={"entrada": "mqtt"})
        return None
    try:
        carga = json.loads(payload)
    except ValueError as erro:
        return pipeline.registrar_carga_ilegivel(payload.decode("utf-8", errors="replace"), origem, str(erro))
    return pipeline.processar(carga, origem)


class ConsumidorMqtt:
    def __init__(
        self,
        pipeline: PipelineDeIngestao,
        url: str,
        *,
        cliente_id: str,
        grupo: str | None = None,
        trabalhadores: int = 8,
    ) -> None:
        endereco = urlparse(url)
        self._host = endereco.hostname or "localhost"
        self._porta = endereco.port or 1883
        self._pipeline = pipeline
        self._grupo = grupo
        self._parando = False
        self._executor = ThreadPoolExecutor(max_workers=trabalhadores, thread_name_prefix="mqtt")
        self.inscrito = threading.Event()
        self._cliente = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id=cliente_id,
            clean_session=False,
            protocol=mqtt.MQTTv311,
            manual_ack=True,
        )
        if endereco.username:
            self._cliente.username_pw_set(endereco.username, endereco.password)
        self._cliente.reconnect_delay_set(1, 30)
        self._cliente.on_connect = self._ao_conectar
        self._cliente.on_subscribe = self._ao_inscrever
        self._cliente.on_message = self._ao_receber

    def topicos(self) -> list[str]:
        # Com grupo, várias réplicas dividem as mensagens por assinatura compartilhada (RNF-09).
        prefixo = f"$share/{self._grupo}/" if self._grupo else ""
        return [f"{prefixo}+/+/+/+/{canal}" for canal in CANAIS]

    def iniciar(self) -> None:
        self._cliente.connect_async(self._host, self._porta, keepalive=30)
        self._cliente.loop_start()
        log.info("consumidor MQTT iniciado em %s:%s", self._host, self._porta, extra={"entrada": "mqtt"})

    def parar(self) -> None:
        # Para de aceitar, termina o que está em andamento (e confirma) e só então desconecta.
        self._parando = True
        self._executor.shutdown(wait=True)
        self._cliente.disconnect()
        self._cliente.loop_stop()

    def _ao_conectar(self, cliente, _dados, _flags, codigo, _propriedades) -> None:
        if codigo.is_failure:
            log.error("conexão MQTT recusada: %s", codigo, extra={"entrada": "mqtt"})
            return
        cliente.subscribe([(topico, 1) for topico in self.topicos()])

    def _ao_inscrever(self, _cliente, _dados, _mid, _codigos, _propriedades) -> None:
        self.inscrito.set()

    def _ao_receber(self, _cliente, _dados, mensagem: mqtt.MQTTMessage) -> None:
        if self._parando:
            return  # sem confirmação: o broker reentrega na próxima sessão
        self._executor.submit(self._processar, mensagem)

    def _processar(self, mensagem: mqtt.MQTTMessage) -> None:
        inicio = time.perf_counter()
        try:
            resultado = processar_publicacao(self._pipeline, mensagem.topic, mensagem.payload)
        except Exception:
            # Sem confirmação: a mensagem continua com o broker e volta na próxima sessão (RNF-10).
            log.exception("falha ao processar mensagem MQTT", extra={"entrada": "mqtt"})
            return
        if resultado is not None:
            observar(resultado, "mqtt", time.perf_counter() - inicio)
        if mensagem.qos > 0:
            self._cliente.ack(mensagem.mid, mensagem.qos)
