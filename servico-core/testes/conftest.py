import pytest

from adaptadores.contrato_jsonschema import ValidadorJsonSchema
from adaptadores.memoria import FilaDeRejeitadasEmMemoria, RepositorioEmMemoria
from apoio import AGORA, CONTRATOS, RelogioFixo, catalogo_de_exemplo
from dominio.pipeline import PipelineDeIngestao


@pytest.fixture(scope="session")
def validador():
    return ValidadorJsonSchema(CONTRATOS)


@pytest.fixture
def relogio():
    return RelogioFixo(AGORA)


@pytest.fixture
def catalogo():
    return catalogo_de_exemplo()


@pytest.fixture
def repositorio():
    return RepositorioEmMemoria()


@pytest.fixture
def rejeitadas():
    return FilaDeRejeitadasEmMemoria()


@pytest.fixture
def pipeline(validador, catalogo, repositorio, rejeitadas, relogio):
    return PipelineDeIngestao(validador, catalogo, repositorio, rejeitadas, relogio)


@pytest.fixture
def regras_env(validador, catalogo, repositorio, rejeitadas, relogio):
    """Motor de regras ligado ao pipeline, com saídas em memória para inspecionar as ações."""
    from types import SimpleNamespace

    from adaptadores.memoria import (
        AlarmesEmMemoria,
        ClienteWebhookEmMemoria,
        NotificadorEmMemoria,
        PublicadorEmMemoria,
        RegrasEmMemoria,
    )
    from dominio.acoes import executores_padrao
    from dominio.motor import MotorDeRegras

    regras = RegrasEmMemoria(catalogo, repositorio)
    alarmes = AlarmesEmMemoria()
    saidas = SimpleNamespace(
        publicador=PublicadorEmMemoria(), notificador=NotificadorEmMemoria(), webhook=ClienteWebhookEmMemoria()
    )
    motor = MotorDeRegras(
        regras,
        alarmes,
        executores_padrao(
            alarmes=alarmes,
            catalogo=catalogo,
            notificador=saidas.notificador,
            publicador=saidas.publicador,
            webhook=saidas.webhook,
            relogio=relogio,
            origem="central",
        ),
        ambito="central",
        validade_do_cache_s=0,
    )
    pipeline = PipelineDeIngestao(validador, catalogo, repositorio, rejeitadas, relogio, observadores=(motor,))
    return SimpleNamespace(regras=regras, alarmes=alarmes, motor=motor, pipeline=pipeline, saidas=saidas)
