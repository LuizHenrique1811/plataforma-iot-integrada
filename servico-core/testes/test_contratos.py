"""Contrato primeiro: contratos válidos e API implementada dentro do contrato (RF-APP-01, RNF-13)."""

import json
import subprocess
import sys

import yaml
from fastapi.routing import APIRoute

from adaptadores.memoria import AutenticadorEmMemoria
from adaptadores.rest.aplicacao import criar_app
from apoio import CONTRATOS


def test_contratos_sao_validos():
    execucao = subprocess.run(
        [sys.executable, str(CONTRATOS / "validar.py")], capture_output=True, text=True, check=False
    )
    assert execucao.returncode == 0, execucao.stdout + execucao.stderr


def test_rotas_implementadas_estao_no_contrato(pipeline):
    especificacao = yaml.safe_load((CONTRATOS / "openapi.yaml").read_text(encoding="utf-8"))
    app = criar_app(pipeline=pipeline, autenticador=AutenticadorEmMemoria(), contratos_dir=CONTRATOS, papel="central")
    fora_do_contrato = [
        f"{metodo} {rota.path}"
        for rota in app.routes
        if isinstance(rota, APIRoute) and rota.include_in_schema
        for metodo in rota.methods
        if metodo.lower() not in especificacao["paths"].get(rota.path, {})
    ]
    assert fora_do_contrato == []


def test_exemplos_validos_passam_no_validador_do_servico(validador):
    for caminho in sorted((CONTRATOS / "exemplos" / "mensagem" / "validos").glob("*.json")):
        assert validador.validar(json.loads(caminho.read_text(encoding="utf-8"))) == [], caminho.name
