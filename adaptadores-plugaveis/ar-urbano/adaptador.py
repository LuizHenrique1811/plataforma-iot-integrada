"""Adaptador plugável de nível 2 (seção 4.2, RF-INT-03, UC-03).

Contêiner próprio, sem nenhum código do núcleo: assina o tópico legado das estações, traduz para a
mensagem canônica e publica no tópico canônico. Entra e sai do ar sem recompilar nem reiniciar o núcleo.
"""

import json
import logging
import os
from urllib.parse import urlparse

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from traducao import FormatoLegadoInvalido, traduzir

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ar-urbano")


def main() -> None:
    endereco = urlparse(os.environ.get("MQTT_URL", "mqtt://host.docker.internal:1883"))
    inquilino = os.environ.get("INQUILINO", "semma")
    site = os.environ.get("SITE", "centro")
    dominio = os.environ.get("DOMINIO", "ambiente")
    topico_legado = os.environ.get("TOPICO_LEGADO", "legado/estacoes/+")

    cliente = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=os.environ.get("MQTT_CLIENTE", "adaptador-ar-urbano"))

    def ao_conectar(cliente, _dados, _flags, codigo, _propriedades):
        log.info("conectado (%s); assinando %s", codigo, topico_legado)
        cliente.subscribe(topico_legado, qos=1)

    def ao_receber(cliente, _dados, mensagem):
        try:
            carga = traduzir(json.loads(mensagem.payload))
        except (ValueError, FormatoLegadoInvalido) as erro:
            # Não é responsabilidade do adaptador guardar o lixo do fabricante: registra e segue.
            log.warning("ignorada em %s: %s", mensagem.topic, erro)
            return
        destino = f"{inquilino}/{site}/{dominio}/{carga['dispositivo']}/telemetria"
        cliente.publish(destino, json.dumps(carga), qos=1)
        log.info("%s -> %s (%s)", mensagem.topic, destino, carga["id_mensagem"])

    cliente.on_connect = ao_conectar
    cliente.on_message = ao_receber
    cliente.reconnect_delay_set(1, 30)
    cliente.connect_async(endereco.hostname or "localhost", endereco.port or 1883, keepalive=30)
    cliente.loop_forever(retry_first_connection=True)


if __name__ == "__main__":
    main()
