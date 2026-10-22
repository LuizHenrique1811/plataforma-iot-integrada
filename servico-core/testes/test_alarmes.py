"""Ciclo de vida dos alarmes (RF-PRO-05) e cadastro de regras com validação e papéis (RF-PRO-02, RF-SEG-02)."""

from datetime import timedelta

import pytest

from adaptadores.memoria import AlarmesEmMemoria, CatalogoEmMemoria, RegrasEmMemoria, RepositorioEmMemoria
from apoio import AGORA, RelogioFixo, regra
from dominio.alarmes import ServicoDeAlarmes
from dominio.erros import AcessoNegado, Conflito, DadosInvalidos, JaExiste, NaoEncontrado
from dominio.modelos import Origem, TipoOrigem
from dominio.paginacao import ParametrosDePagina
from dominio.regras import Acao, Alarme, EstadoAlarme, ServicoDeRegras, Severidade, TipoAcao

OPERADOR = Origem(TipoOrigem.CHAVE, "coop-cerrado", papel="operador")
GESTOR = Origem(TipoOrigem.CHAVE, "coop-cerrado", papel="gestor")
LEITOR = Origem(TipoOrigem.CHAVE, "coop-cerrado", papel="leitor")
PAGINA = ParametrosDePagina()


def novo_alarme(identificador="a1", inquilino="coop-cerrado", severidade=Severidade.CRITICO, minutos=0) -> Alarme:
    return Alarme(
        identificador, inquilino, "r1", "silo-02", severidade, EstadoAlarme.ATIVO, AGORA - timedelta(minutes=minutos)
    )


@pytest.fixture
def relogio():
    return RelogioFixo(AGORA)


@pytest.fixture
def alarmes():
    return AlarmesEmMemoria()


@pytest.fixture
def servico(alarmes, relogio):
    return ServicoDeAlarmes(alarmes, relogio)


def test_ativo_reconhecido_resolvido(servico, alarmes, relogio):
    alarmes.inserir_alarme(novo_alarme())
    relogio.avancar(minutes=2)
    reconhecido = servico.reconhecer(OPERADOR, "a1")
    assert (reconhecido.estado, reconhecido.reconhecido_em) == (EstadoAlarme.RECONHECIDO, AGORA + timedelta(minutes=2))
    relogio.avancar(minutes=30)
    resolvido = servico.resolver(OPERADOR, "a1")
    assert (resolvido.estado, resolvido.resolvido_em) == (EstadoAlarme.RESOLVIDO, AGORA + timedelta(minutes=32))
    assert alarmes.obter_alarme("coop-cerrado", "a1").estado is EstadoAlarme.RESOLVIDO


def test_transicoes_invalidas(servico, alarmes):
    alarmes.inserir_alarme(novo_alarme())
    servico.resolver(OPERADOR, "a1")  # ativo -> resolvido direto é permitido
    with pytest.raises(Conflito):
        servico.reconhecer(OPERADOR, "a1")
    with pytest.raises(Conflito):
        servico.resolver(OPERADOR, "a1")


def test_reconhecer_duas_vezes(servico, alarmes):
    alarmes.inserir_alarme(novo_alarme())
    servico.reconhecer(OPERADOR, "a1")
    with pytest.raises(Conflito):
        servico.reconhecer(OPERADOR, "a1")


def test_leitor_nao_opera_alarmes(servico, alarmes):
    alarmes.inserir_alarme(novo_alarme())
    with pytest.raises(AcessoNegado):
        servico.reconhecer(LEITOR, "a1")
    assert servico.listar(LEITOR, None, None, PAGINA).total == 1


def test_alarme_de_outro_inquilino_ou_inexistente(servico, alarmes):
    alarmes.inserir_alarme(novo_alarme(inquilino="semma"))
    with pytest.raises(NaoEncontrado):
        servico.reconhecer(OPERADOR, "a1")
    with pytest.raises(NaoEncontrado):
        servico.resolver(OPERADOR, "nao-existe")


def test_listagem_com_filtros_e_mais_recentes_primeiro(servico, alarmes):
    # Gravados direto, sem a regra de um aberto por regra e dispositivo, para montar a listagem.
    alarmes.atualizar_alarme(novo_alarme("antigo", minutos=60))
    alarmes.atualizar_alarme(novo_alarme("recente", severidade=Severidade.AVISO))
    alarmes.atualizar_alarme(novo_alarme("info", severidade=Severidade.INFO, minutos=30))
    servico.resolver(OPERADOR, "antigo")
    assert [a.id for a in servico.listar(OPERADOR, None, None, PAGINA).itens] == ["recente", "info", "antigo"]
    assert [a.id for a in servico.listar(OPERADOR, "ativo", None, PAGINA).itens] == ["recente", "info"]
    assert [a.id for a in servico.listar(OPERADOR, None, "aviso", PAGINA).itens] == ["recente"]


def test_um_alarme_aberto_por_regra_e_dispositivo(alarmes):
    assert alarmes.inserir_alarme(novo_alarme("a1")) is True
    assert alarmes.inserir_alarme(novo_alarme("a2")) is False
    assert alarmes.resolver_abertos("coop-cerrado", "r1", "silo-02", AGORA, "central") == 1
    assert alarmes.inserir_alarme(novo_alarme("a3")) is True


class TestCadastroDeRegras:
    @pytest.fixture
    def servico_de_regras(self, relogio):
        mudancas = []
        repositorio = RegrasEmMemoria(CatalogoEmMemoria(), RepositorioEmMemoria())
        servico = ServicoDeRegras(repositorio, relogio, ao_mudar=mudancas.append)
        servico.mudancas = mudancas
        return servico

    def test_cria_e_lista(self, servico_de_regras):
        criada = servico_de_regras.criar(GESTOR, regra())
        assert criada.criado_em == AGORA
        assert servico_de_regras.mudancas == ["coop-cerrado"]
        assert [r.id for r in servico_de_regras.listar(LEITOR, PAGINA).itens] == ["umidade-baixa"]
        with pytest.raises(JaExiste):
            servico_de_regras.criar(GESTOR, regra())

    def test_operador_nao_altera_regras(self, servico_de_regras):
        # Critério do RF-SEG-02.
        with pytest.raises(AcessoNegado):
            servico_de_regras.criar(OPERADOR, regra())

    @pytest.mark.parametrize(
        ("invalida", "caminhos"),
        [
            (regra(operador=None, valor=None), {"/condicao/operador", "/condicao/valor"}),
            (regra(tipo="janela"), {"/condicao/duracao_s"}),
            (regra(tipo="ausencia", operador=None, valor=None), {"/condicao/duracao_s"}),
            (regra(acoes=[Acao(TipoAcao.WEBHOOK)]), {"/acoes/0/url"}),
            (regra(acoes=[Acao(TipoAcao.COMANDO)]), {"/acoes/0/comando"}),
            (regra(acoes=[Acao(TipoAcao.PUBLICAR, topico="semma/eventos")]), {"/acoes/0/topico"}),
            (regra(acoes=[Acao(TipoAcao.PUBLICAR, topico="coop-cerrado/#")]), {"/acoes/0/topico"}),
        ],
    )
    def test_regras_inconsistentes(self, servico_de_regras, invalida, caminhos):
        with pytest.raises(DadosInvalidos) as erro:
            servico_de_regras.criar(GESTOR, invalida)
        assert {campo.caminho for campo in erro.value.erros} == caminhos
