"""Contrato primeiro: contratos válidos e API implementada dentro do contrato (RF-APP-01, RNF-13)."""

import json
import subprocess
import sys

import yaml
from fastapi.routing import APIRoute

from adaptadores.memoria import AutenticadorEmMemoria
from adaptadores.rest.aplicacao import criar_app
from apoio import CONTRATOS


def rotas_da_api(rotas):
    """Rotas da aplicação, inclusive as dos roteadores incluídos.

    Nas versões recentes do FastAPI, include_router guarda o roteador aninhado em vez de copiar as rotas;
    sem percorrer a árvore, o teste não veria nada e passaria vazio. Os roteadores daqui não usam prefixo.
    """
    for rota in rotas:
        if isinstance(rota, APIRoute):
            yield rota
        elif hasattr(rota, "original_router"):
            yield from rotas_da_api(rota.original_router.routes)


def test_percorre_as_rotas_incluidas(pipeline):
    app = criar_app(pipeline=pipeline, autenticador=AutenticadorEmMemoria(), contratos_dir=CONTRATOS, papel="central")
    assert "/api/v1/ingestao" in {rota.path for rota in rotas_da_api(app.routes)}


def test_contratos_sao_validos():
    execucao = subprocess.run(
        [sys.executable, str(CONTRATOS / "validar.py")], capture_output=True, text=True, check=False
    )
    assert execucao.returncode == 0, execucao.stdout + execucao.stderr


def test_api_implementada_e_contrato_coincidem():
    # RF-APP-01: toda rota implementada está no contrato, e toda operação do contrato está implementada.
    from configuracao import Configuracao
    from principal import criar_aplicacao

    especificacao = yaml.safe_load((CONTRATOS / "openapi.yaml").read_text(encoding="utf-8"))
    app = criar_aplicacao(Configuracao(contratos_dir=CONTRATOS))
    implementadas = {
        (metodo.lower(), rota.path)
        for rota in rotas_da_api(app.routes)
        if rota.include_in_schema
        for metodo in rota.methods
    }
    no_contrato = {
        (metodo, caminho)
        for caminho, operacoes in especificacao["paths"].items()
        for metodo in operacoes
        if metodo in ("get", "post", "put", "patch", "delete")
    }
    assert implementadas - no_contrato == set()
    assert no_contrato - implementadas == set()


def test_rotas_minimas_sem_catalogo_tambem_estao_no_contrato(pipeline):
    especificacao = yaml.safe_load((CONTRATOS / "openapi.yaml").read_text(encoding="utf-8"))
    app = criar_app(pipeline=pipeline, autenticador=AutenticadorEmMemoria(), contratos_dir=CONTRATOS, papel="central")
    fora_do_contrato = [
        f"{metodo} {rota.path}"
        for rota in rotas_da_api(app.routes)
        if rota.include_in_schema
        for metodo in rota.methods
        if metodo.lower() not in especificacao["paths"].get(rota.path, {})
    ]
    assert fora_do_contrato == []


def test_exemplos_validos_passam_no_validador_do_servico(validador):
    for caminho in sorted((CONTRATOS / "exemplos" / "mensagem" / "validos").glob("*.json")):
        assert validador.validar(json.loads(caminho.read_text(encoding="utf-8"))) == [], caminho.name
