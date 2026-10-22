"""Estação de qualidade do ar com firmware legado (UC-03): publica o JSON do fabricante, não o canônico.

Quem traduz é o adaptador plugável adaptadores-plugaveis/ar-urbano. De vez em quando a estação reenvia a
última leitura, como fazem firmwares sem confirmação; o adaptador gera o mesmo id_mensagem e o núcleo
descarta a repetida.

Uso: python estacao_legada.py
"""

import json
import logging
import os
import random
import time
import uuid
from urllib.parse import urlparse

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("estacao-legada")


def main() -> None:
    endereco = urlparse(os.environ.get("MQTT_URL", "mqtt://host.docker.internal:1883"))
    estacao = os.environ.get("ESTACAO", "AR-CENTRO-03")
    intervalo = float(os.environ.get("INTERVALO_S", "5"))
    cliente = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"estacao-{uuid.uuid4().hex[:6]}")
    cliente.connect(endereco.hostname or "localhost", endereco.port or 1883)
    cliente.loop_start()
    pm25, ruido, temperatura_f = 15.0, 60.0, 77.0
    ultima = None
    while True:
        if ultima is not None and random.random() < 0.2:
            carga = ultima  # reenvio da mesma leitura
        else:
            pm25 = max(2.0, pm25 + random.uniform(-2, 2.5))
            ruido = min(95.0, max(40.0, ruido + random.uniform(-3, 3)))
            temperatura_f = temperatura_f + random.uniform(-0.5, 0.5)
            carga = {
                "station": estacao,
                "ts": int(time.time()),
                "readings": {"pm2_5": round(pm25, 1), "noise_db": round(ruido), "temp_f": round(temperatura_f, 1)},
            }
        cliente.publish(f"legado/estacoes/{estacao}", json.dumps(carga), qos=1)
        log.info("legado/estacoes/%s %s%s", estacao, carga["readings"], " (reenvio)" if carga is ultima else "")
        ultima = carga
        time.sleep(intervalo)


if __name__ == "__main__":
    main()
