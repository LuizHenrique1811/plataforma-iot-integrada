"""Valida os contratos da plataforma (contrato primeiro, RNF-13).

- Cada JSON Schema é um schema draft-07 válido.
- Os exemplos em exemplos/<schema>/validos passam, e os de exemplos/<schema>/invalidos falham.
- O openapi.yaml é uma especificação OpenAPI 3.1 válida, inclusive as referências externas.

O asyncapi.yaml é validado pela CLI oficial do AsyncAPI, que roda em Node (ver README).

Uso: python contratos/validar.py
     python contratos/validar.py --mensagens < amostras.jsonl   (uma mensagem canônica por linha)
Dependências: jsonschema[format-nongpl], pyyaml, openapi-spec-validator.
"""

import json
import sys
from pathlib import Path

from jsonschema import Draft7Validator
from openapi_spec_validator import validate as validar_openapi
from openapi_spec_validator.readers import read_from_filename

RAIZ = Path(__file__).resolve().parent

# Pasta de exemplos -> schema que os valida.
EXEMPLOS = {
    "mensagem": "mensagem-canonica-1.0.json",
    "lote": "lote-1.0.json",
}


def carregar_json(caminho: Path):
    with caminho.open(encoding="utf-8") as arquivo:
        return json.load(arquivo)


def validar_schemas() -> list[str]:
    falhas = []
    for caminho in sorted((RAIZ / "json-schema").glob("*.json")):
        try:
            Draft7Validator.check_schema(carregar_json(caminho))
        except Exception as erro:  # noqa: BLE001 - qualquer falha invalida o contrato
            falhas.append(f"{caminho.name}: schema inválido: {erro}")
    return falhas


def validar_exemplos() -> list[str]:
    falhas = []
    for pasta, arquivo_schema in EXEMPLOS.items():
        schema = carregar_json(RAIZ / "json-schema" / arquivo_schema)
        validador = Draft7Validator(schema, format_checker=Draft7Validator.FORMAT_CHECKER)
        for caminho in sorted((RAIZ / "exemplos" / pasta / "validos").glob("*.json")):
            erros = list(validador.iter_errors(carregar_json(caminho)))
            if erros:
                falhas.append(f"{pasta}/validos/{caminho.name} deveria passar: {erros[0].message}")
        for caminho in sorted((RAIZ / "exemplos" / pasta / "invalidos").glob("*.json")):
            if validador.is_valid(carregar_json(caminho)):
                falhas.append(f"{pasta}/invalidos/{caminho.name} deveria falhar e passou")
    return falhas


def validar_openapi_yaml() -> list[str]:
    try:
        especificacao, base_uri = read_from_filename(str(RAIZ / "openapi.yaml"))
        validar_openapi(especificacao, base_uri=base_uri)
    except Exception as erro:  # noqa: BLE001
        return [f"openapi.yaml inválido: {erro}"]
    return []


def validar_mensagens(linhas) -> list[str]:
    """Valida mensagens canônicas, uma por linha (ex.: amostras dos simuladores das três linguagens)."""
    validador = Draft7Validator(
        carregar_json(RAIZ / "json-schema" / "mensagem-canonica-1.0.json"),
        format_checker=Draft7Validator.FORMAT_CHECKER,
    )
    falhas, total = [], 0
    for numero, linha in enumerate(linhas, start=1):
        if not linha.strip():
            continue
        total += 1
        erros = list(validador.iter_errors(json.loads(linha)))
        if erros:
            falhas.append(f"mensagem da linha {numero}: {erros[0].message}")
    if total == 0:
        falhas.append("nenhuma mensagem recebida")
    else:
        print(f"{total} mensagens validadas contra a mensagem canônica 1.0.")
    return falhas


def main() -> int:
    if "--mensagens" in sys.argv:
        falhas = validar_mensagens(sys.stdin)
        for falha in falhas:
            print(f"FALHA  {falha}")
        return 1 if falhas else 0
    falhas = validar_schemas() + validar_exemplos() + validar_openapi_yaml()
    for falha in falhas:
        print(f"FALHA  {falha}")
    if falhas:
        return 1
    print("Contratos válidos: JSON Schema, exemplos e OpenAPI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
