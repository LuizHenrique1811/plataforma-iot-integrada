"""Consultas de histórico, último estado, situação e DLQ (RF-DAD-01, RF-DAD-02, RF-DIS-06, ADR-0010)."""

from datetime import timedelta

import pytest

from adaptadores.memoria import ConsultasEmMemoria
from apoio import AGORA, ORIGEM_BORDA, ORIGEM_SOLO, mensagem
from dominio.consultas import Contato, ServicoDeConsultas, SituacaoDispositivo, calcular_situacao
from dominio.erros import AcessoNegado, DadosInvalidos, NaoEncontrado
from dominio.modelos import Origem, TipoOrigem
from dominio.paginacao import ParametrosDePagina

LEITOR = Origem(TipoOrigem.CHAVE, "coop-cerrado", papel="leitor")
PAGINA = ParametrosDePagina()


@pytest.fixture
def consultas(repositorio, rejeitadas, catalogo, relogio):
    return ServicoDeConsultas(ConsultasEmMemoria(repositorio, rejeitadas), catalogo, relogio)


class TestSituacao:
    def test_sensor_de_hora_em_hora_nao_fica_offline_apos_5_minutos(self):
        # Critério do RF-DIS-06.
        contato = Contato(AGORA - timedelta(minutes=5))
        assert calcular_situacao(AGORA, contato, 3600, None) is SituacaoDispositivo.ONLINE

    def test_offline_depois_de_duas_vezes_o_intervalo(self):
        contato = Contato(AGORA - timedelta(hours=3))
        assert calcular_situacao(AGORA, contato, 3600, None) is SituacaoDispositivo.OFFLINE

    def test_nunca_visto_e_offline(self):
        assert calcular_situacao(AGORA, None, 60, None) is SituacaoDispositivo.OFFLINE

    def test_atras_de_borda_sem_sincronizar_e_desconhecido(self):
        # ADR-0010: a central não sabe se o sensor parou ou se o link caiu.
        contato = Contato(AGORA - timedelta(hours=3), via="borda-fazenda")
        assert calcular_situacao(AGORA, contato, 900, AGORA - timedelta(hours=3)) is SituacaoDispositivo.DESCONHECIDO
        assert calcular_situacao(AGORA, contato, 900, None) is SituacaoDispositivo.DESCONHECIDO

    def test_atras_de_borda_que_sincroniza_e_offline(self):
        contato = Contato(AGORA - timedelta(hours=3), via="borda-fazenda")
        assert calcular_situacao(AGORA, contato, 900, AGORA - timedelta(minutes=1)) is SituacaoDispositivo.OFFLINE


def test_historico_em_ordem_de_medicao_com_filtros(pipeline, consultas):
    # RF-DAD-01, com o dado atrasado já no lugar certo (RF-ING-04).
    for horario, valor in (("05:10", 23.5), ("03:10", 30.0), ("04:10", 27.0)):
        pipeline.processar(
            mensagem(
                timestamp=f"2026-10-19T{horario}:00Z",
                medidas=[
                    {"grandeza": "umidade_solo", "valor": valor},
                    {"grandeza": "temperatura_solo", "valor": 20},
                ],
            ),
            ORIGEM_BORDA,
        )
    pagina = consultas.telemetria(LEITOR, "solo-talhao07-02", "umidade_solo", None, None, PAGINA)
    assert [medicao.valor for medicao in pagina.itens] == [30.0, 27.0, 23.5]
    assert pagina.total == 3

    recentes = consultas.telemetria(
        LEITOR,
        "solo-talhao07-02",
        None,
        AGORA - timedelta(hours=1, minutes=30),
        AGORA,
        ParametrosDePagina(ordenar="-timestamp"),
    )
    assert [(medicao.grandeza, medicao.valor) for medicao in recentes.itens] == [
        ("umidade_solo", 23.5),
        ("temperatura_solo", 20.0),
        ("umidade_solo", 27.0),
        ("temperatura_solo", 20.0),
    ]
    assert recentes.total == 4


def test_intervalo_vazio_e_dispositivo_inexistente(consultas):
    with pytest.raises(DadosInvalidos):
        consultas.telemetria(LEITOR, "solo-talhao07-02", None, AGORA, AGORA, PAGINA)
    with pytest.raises(NaoEncontrado):
        consultas.telemetria(LEITOR, "nao-existe", None, None, None, PAGINA)
    with pytest.raises(NaoEncontrado):
        consultas.estado(LEITOR, "nao-existe")


def test_estado_com_ultimo_valor_e_situacao(pipeline, consultas):
    # RF-DAD-02 e RF-DIS-06
    pipeline.processar(mensagem(timestamp="2026-10-19T05:10:00Z"), ORIGEM_SOLO)
    pipeline.processar(
        mensagem(timestamp="2026-10-19T02:00:00Z", medidas=[{"grandeza": "umidade_solo", "valor": 1.0}]), ORIGEM_SOLO
    )
    estado = consultas.estado(LEITOR, "solo-talhao07-02")
    assert estado.situacao is SituacaoDispositivo.ONLINE
    assert estado.ultimo_contato == AGORA - timedelta(minutes=5)
    assert [(medicao.grandeza, medicao.valor) for medicao in estado.grandezas] == [("umidade_solo", 23.5)]


def test_estado_desconhecido_quando_a_borda_some(pipeline, consultas, relogio):
    pipeline.processar(mensagem(via="borda-fazenda-boa-vista"), ORIGEM_BORDA)
    relogio.avancar(hours=5)
    assert consultas.estado(LEITOR, "solo-talhao07-02").situacao is SituacaoDispositivo.DESCONHECIDO


def test_estado_de_dispositivo_sem_dados(consultas):
    estado = consultas.estado(LEITOR, "solo-talhao07-02")
    assert (estado.situacao, estado.ultimo_contato, estado.grandezas) == (SituacaoDispositivo.OFFLINE, None, ())


def test_dlq_consultada_por_inquilino(pipeline, consultas):
    pipeline.processar(mensagem(id_mensagem="ruim"), ORIGEM_SOLO)
    pipeline.processar(mensagem(id_mensagem="ruim"), Origem(TipoOrigem.CHAVE, "semma", papel="integrador"))
    pagina = consultas.rejeitadas(LEITOR, PAGINA)
    assert pagina.total == 1
    assert pagina.itens[0].motivo == "fora_do_contrato"
    assert pagina.itens[0].erros[0]["caminho"] == "/id_mensagem"


def test_dispositivo_nao_consulta(consultas):
    with pytest.raises(AcessoNegado):
        consultas.estado(ORIGEM_SOLO, "solo-talhao07-02")
