"""A tradução gera mensagens que seguem o contrato canônico (contrato primeiro, RF-INT-03)."""

import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from traducao import FormatoLegadoInvalido, traduzir  # noqa: E402

SCHEMA = json.loads(
    (RAIZ.parents[1] / "contratos" / "json-schema" / "mensagem-canonica-1.0.json").read_text(encoding="utf-8")
)
VALIDADOR = Draft7Validator(SCHEMA, format_checker=Draft7Validator.FORMAT_CHECKER)
LEGADO = {"station": "AR-CENTRO-03", "ts": 1761109200, "readings": {"pm2_5": 18.2, "noise_db": 64, "temp_f": 77.0}}


def test_traduz_para_a_mensagem_canonica():
    carga = traduzir(LEGADO)
    assert list(VALIDADOR.iter_errors(carga)) == []
    assert carga["dispositivo"] == "ar-centro-03"
    assert carga["timestamp"] == "2025-10-22T05:00:00Z"
    assert carga["medidas"] == [
        {"grandeza": "pm25", "valor": 18.2, "unidade": "ug/m3"},
        {"grandeza": "ruido", "valor": 64.0, "unidade": "dB"},
        {"grandeza": "temperatura_ar", "valor": 77.0, "unidade": "[degF]"},
    ]


def test_mesma_leitura_reenviada_gera_o_mesmo_id():
    # A estação reenvia a mesma leitura; a deduplicação do núcleo descarta pelo id_mensagem.
    assert traduzir(LEGADO)["id_mensagem"] == traduzir(dict(LEGADO))["id_mensagem"]
    assert traduzir({**LEGADO, "ts": LEGADO["ts"] + 60})["id_mensagem"] != traduzir(LEGADO)["id_mensagem"]


def test_campos_desconhecidos_sao_ignorados():
    carga = traduzir({**LEGADO, "readings": {"pm2_5": 10, "co2_ppm": 400}, "firmware": "x"})
    assert [medida["grandeza"] for medida in carga["medidas"]] == ["pm25"]


@pytest.mark.parametrize(
    "invalido",
    [
        {},
        {"station": "AR-1", "ts": "ontem", "readings": {"pm2_5": 1}},
        {"station": "AR-1", "ts": 1, "readings": {"co2_ppm": 400}},
        {"station": "", "ts": 1, "readings": {"pm2_5": 1}},
        {"station": "AR-1", "ts": 1, "readings": {"pm2_5": "alto"}},
        ["não", "é", "objeto"],
    ],
)
def test_formato_legado_invalido(invalido):
    with pytest.raises(FormatoLegadoInvalido):
        traduzir(invalido)
