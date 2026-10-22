"""Validação pelos arquivos de contratos/json-schema (contrato primeiro)."""

import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator
from jsonschema.protocols import Validator

from dominio.modelos import ErroDeCampo

_PADRAO_ARQUIVO = re.compile(r"^mensagem-canonica-(\d+\.\d+)\.json$")


class ValidadorJsonSchema:
    def __init__(self, contratos_dir: Path) -> None:
        pasta = contratos_dir / "json-schema"
        self._por_versao: dict[str, Draft7Validator] = {}
        for caminho in sorted(pasta.glob("mensagem-canonica-*.json")):
            correspondencia = _PADRAO_ARQUIVO.match(caminho.name)
            if correspondencia:
                self._por_versao[correspondencia.group(1)] = _compilar(caminho)
        if not self._por_versao:
            raise FileNotFoundError(f"nenhum schema de mensagem canônica em {pasta}")
        self._lote = _compilar(pasta / "lote-1.0.json")

    def versoes(self) -> frozenset[str]:
        return frozenset(self._por_versao)

    def validar(self, carga: dict[str, Any]) -> list[ErroDeCampo]:
        return erros_de_validacao(self._por_versao[carga["versao"]], carga)

    def validar_lote(self, carga: Any) -> list[ErroDeCampo]:
        return erros_de_validacao(self._lote, carga)


def _compilar(caminho: Path) -> Draft7Validator:
    with caminho.open(encoding="utf-8") as arquivo:
        schema = json.load(arquivo)
    return Draft7Validator(schema, format_checker=Draft7Validator.FORMAT_CHECKER)


def erros_de_validacao(validador: Validator, carga: Any) -> list[ErroDeCampo]:
    erros = sorted(validador.iter_errors(carga), key=lambda erro: [str(parte) for parte in erro.absolute_path])
    return [ErroDeCampo(_ponteiro(erro.absolute_path), erro.message) for erro in erros]


def _ponteiro(caminho) -> str:
    """Caminho do erro como JSON Pointer (ex.: /medidas/0/valor)."""
    return "".join(f"/{parte}" for parte in caminho)
