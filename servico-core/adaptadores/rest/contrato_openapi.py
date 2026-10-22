"""Valida corpos de requisição pelos schemas de contratos/openapi.yaml (contrato primeiro, RF-APP-01)."""

from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from adaptadores.contrato_jsonschema import erros_de_validacao
from dominio.erros import DadosInvalidos

_URI = "urn:plataforma-iot:openapi"


class ValidadorDeCorpos:
    def __init__(self, contratos_dir: Path) -> None:
        documento = yaml.safe_load((contratos_dir / "openapi.yaml").read_text(encoding="utf-8"))
        self._schemas = documento["components"]["schemas"]
        recurso = Resource.from_contents(documento, default_specification=DRAFT202012)
        self._registro = Registry().with_resource(_URI, recurso)
        self._validadores: dict[str, Draft202012Validator] = {}

    def validar(self, schema: str, corpo: Any) -> dict[str, Any]:
        """Devolve o corpo se ele segue components/schemas/<schema>; senão levanta DadosInvalidos."""
        validador = self._validadores.get(schema)
        if validador is None:
            if schema not in self._schemas:
                raise KeyError(f"schema {schema!r} não existe no openapi.yaml")
            validador = Draft202012Validator(
                {"$ref": f"{_URI}#/components/schemas/{schema}"},
                registry=self._registro,
                format_checker=Draft202012Validator.FORMAT_CHECKER,
            )
            self._validadores[schema] = validador
        erros = erros_de_validacao(validador, corpo)
        if erros:
            raise DadosInvalidos(f"O corpo não segue o schema {schema} do contrato.", erros)
        return corpo
