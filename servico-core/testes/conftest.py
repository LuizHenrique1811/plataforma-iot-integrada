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
