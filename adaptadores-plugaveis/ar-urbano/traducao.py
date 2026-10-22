"""Tradução do JSON legado das estações de qualidade do ar para a mensagem canônica v1.0 (UC-03, RF-INT-03).

Formato legado (do fabricante, não pode mudar):
    {"station": "AR-CENTRO-03", "ts": 1761109200, "readings": {"pm2_5": 18.2, "noise_db": 64, "temp_f": 77.0}}

O adaptador não converte unidades: informa a unidade de origem (Fahrenheit) e o núcleo converte para a do
perfil (RF-PRO-01). O id_mensagem é derivado da estação e do horário, então a mesma leitura reenviada pela
estação gera o mesmo id e é descartada pela deduplicação (RF-ING-08).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

# Campo legado -> (grandeza do catálogo, unidade UCUM).
CAMPOS = {
    "pm2_5": ("pm25", "ug/m3"),
    "pm10": ("pm10", "ug/m3"),
    "noise_db": ("ruido", "dB"),
    "temp_f": ("temperatura_ar", "[degF]"),
}
_ESPACO_DE_NOMES = uuid.UUID("6f1d3a52-4c1e-4b8a-9e55-2f0c8a1b7d90")


class FormatoLegadoInvalido(ValueError):
    pass


def traduzir(legado: Any) -> dict[str, Any]:
    try:
        estacao = str(legado["station"]).strip()
        instante = datetime.fromtimestamp(int(legado["ts"]), UTC)
        leituras = legado["readings"]
        medidas = [
            {"grandeza": grandeza, "valor": float(leituras[campo]), "unidade": unidade}
            for campo, (grandeza, unidade) in CAMPOS.items()
            if leituras.get(campo) is not None
        ]
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as erro:
        raise FormatoLegadoInvalido(f"mensagem legada inválida: {erro!r}") from erro
    if not estacao or not medidas:
        raise FormatoLegadoInvalido("mensagem legada sem estação ou sem leituras conhecidas")
    dispositivo = estacao.lower()
    return {
        "versao": "1.0",
        "id_mensagem": str(uuid.uuid5(_ESPACO_DE_NOMES, f"{dispositivo}:{int(legado['ts'])}")),
        "dispositivo": dispositivo,
        "tipo": "telemetria",
        "timestamp": instante.isoformat().replace("+00:00", "Z"),
        "medidas": medidas,
    }
