"""Simulador rural em Python (UC-01 e UC-02): sensores de solo e de silo publicando por MQTT na borda.

Integração de nível 1 (seção 4.2): só uma biblioteca genérica de MQTT (paho-mqtt) e o contrato canônico.
O solo seca aos poucos; quando a regra local da borda manda abrir a válvula de irrigação, o simulador
recebe o comando e a umidade volta a subir, fechando o ciclo do UC-01.

Uso: python simulador.py           (publica a cada INTERVALO_S segundos)
     python simulador.py --amostra (imprime uma mensagem de cada sensor e sai)
"""

import json
import logging
import math
import os
import random
import sys
import time
import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("simulador-rural")

INQUILINO = os.environ.get("INQUILINO", "coop-cerrado")
SITE = os.environ.get("SITE", "fazenda-boa-vista")
VALVULA = os.environ.get("VALVULA", "valvula-talhao07")
SENSORES = [
    {"dispositivo": "solo-talhao07-02", "dominio": "agricultura", "grandeza": "umidade_solo", "unidade": "%"},
    {"dispositivo": "silo-02", "dominio": "armazenagem", "grandeza": "temperatura_graos", "unidade": "Cel"},
]


def mensagem(sensor: dict, valor: float) -> dict:
    return {
        "versao": "1.0",
        "id_mensagem": str(uuid.uuid4()),
        "dispositivo": sensor["dispositivo"],
        "tipo": "telemetria",
        "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "medidas": [{"grandeza": sensor["grandeza"], "valor": round(valor, 2), "unidade": sensor["unidade"]}],
    }


def topico(sensor: dict) -> str:
    return f"{INQUILINO}/{SITE}/{sensor['dominio']}/{sensor['dispositivo']}/telemetria"


class Fazenda:
    """Estado simulado: umidade do solo e temperatura dos grãos."""

    def __init__(self, umidade: float, temperatura: float) -> None:
        self.umidade = umidade
        self.temperatura = temperatura
        self.temperatura_media = temperatura
        self.passos = 0
        self.ciclos_irrigando = 0

    def avancar(self) -> None:
        if self.ciclos_irrigando > 0:
            self.umidade = min(45.0, self.umidade + 3.0)
            self.ciclos_irrigando -= 1
        else:
            self.umidade = max(5.0, self.umidade - random.uniform(0.4, 1.2))
        # O silo esquenta e esfria em ciclos de uns 6 minutos (a 5 s por envio), passando de 30 °C por um tempo.
        self.passos += 1
        self.temperatura = self.temperatura_media + 2.5 * math.sin(self.passos / 12) + random.uniform(-0.2, 0.2)

    def valores(self) -> list[float]:
        return [self.umidade, self.temperatura]


def main() -> None:
    fazenda = Fazenda(
        float(os.environ.get("UMIDADE_INICIAL", "26")), float(os.environ.get("TEMPERATURA_MEDIA", "29.5"))
    )
    if "--amostra" in sys.argv:
        for sensor, valor in zip(SENSORES, fazenda.valores(), strict=True):
            print(json.dumps(mensagem(sensor, valor)))
        return

    import paho.mqtt.client as mqtt
    from paho.mqtt.enums import CallbackAPIVersion

    endereco = urlparse(os.environ.get("MQTT_URL", "mqtt://host.docker.internal:1884"))
    intervalo = float(os.environ.get("INTERVALO_S", "5"))
    topico_do_comando = f"{INQUILINO}/{SITE}/agricultura/{VALVULA}/comando"
    cliente = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"simulador-rural-{uuid.uuid4().hex[:6]}")

    def ao_conectar(cliente, _dados, _flags, codigo, _propriedades):
        log.info("conectado ao broker (%s); ouvindo %s", codigo, topico_do_comando)
        cliente.subscribe(topico_do_comando, qos=1)

    def ao_receber_comando(_cliente, _dados, recebida):
        comando = json.loads(recebida.payload).get("comando", {})
        log.info("válvula recebeu o comando %s", comando)
        if comando.get("nome") == "abrir":
            fazenda.ciclos_irrigando = 6

    cliente.on_connect = ao_conectar
    cliente.on_message = ao_receber_comando
    cliente.connect(endereco.hostname or "localhost", endereco.port or 1883)
    cliente.loop_start()
    while True:
        fazenda.avancar()
        for sensor, valor in zip(SENSORES, fazenda.valores(), strict=True):
            carga = mensagem(sensor, valor)
            cliente.publish(topico(sensor), json.dumps(carga), qos=1)
            log.info("%s %s = %.2f %s", sensor["dispositivo"], sensor["grandeza"], valor, sensor["unidade"])
        time.sleep(intervalo)


if __name__ == "__main__":
    main()
