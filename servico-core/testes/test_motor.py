"""Motor de regras: limite, janela e ausência, disparo na transição e dado atrasado sem alarme (RF-PRO-02)."""

from dataclasses import replace
from datetime import timedelta

from apoio import AGORA, ORIGEM_BORDA, ORIGEM_SOLO, mensagem, regra
from dominio.modelos import DispositivoCadastrado, Situacao
from dominio.regras import Acao, EstadoAlarme, Severidade, TipoAcao


def umidade(valor, **campos):
    return mensagem(timestamp=None, medidas=[{"grandeza": "umidade_solo", "valor": valor}], **campos)


def temperatura(valor):
    return mensagem(timestamp=None, medidas=[{"grandeza": "temperatura_solo", "valor": valor}])


def alarmes_de(env, estado=None):
    return [a for a in env.alarmes.alarmes.values() if estado is None or a.estado is estado]


def test_limite_dispara_uma_vez_e_gera_alarme(regras_env, relogio):
    regras_env.regras.inserir_regra("coop-cerrado", regra())
    regras_env.pipeline.processar(umidade(17.9), ORIGEM_SOLO)
    relogio.avancar(seconds=60)
    regras_env.pipeline.processar(umidade(15.0), ORIGEM_SOLO)

    [alarme] = alarmes_de(regras_env)
    assert (alarme.estado, alarme.severidade, alarme.dispositivo) == (
        EstadoAlarme.ATIVO,
        Severidade.CRITICO,
        "solo-talhao07-02",
    )
    assert alarme.ocorrido_em == AGORA
    assert "umidade_solo = 17.9" in alarme.mensagem


def test_alarme_resolvido_quando_a_condicao_deixa_de_valer(regras_env, relogio):
    # UC-04: "após a coleta, o nível cai e o alarme é resolvido".
    regras_env.regras.inserir_regra("coop-cerrado", regra())
    regras_env.pipeline.processar(umidade(17.9), ORIGEM_SOLO)
    relogio.avancar(minutes=1)
    regras_env.pipeline.processar(umidade(35.0), ORIGEM_SOLO)
    [resolvido] = alarmes_de(regras_env)
    assert (resolvido.estado, resolvido.resolvido_em) == (EstadoAlarme.RESOLVIDO, AGORA + timedelta(minutes=1))

    relogio.avancar(minutes=1)
    regras_env.pipeline.processar(umidade(12.0), ORIGEM_SOLO)
    assert len(alarmes_de(regras_env, EstadoAlarme.ATIVO)) == 1


def test_janela_exige_a_condicao_continua_pelo_periodo(regras_env, relogio):
    # UC-02: "temperatura > 30 °C por 30 minutos" (aqui, 2 minutos).
    regras_env.regras.inserir_regra(
        "coop-cerrado", regra("silo-quente", "janela", "temperatura_solo", ">", 30, duracao_s=120)
    )
    regras_env.pipeline.processar(temperatura(31), ORIGEM_SOLO)
    relogio.avancar(seconds=60)
    regras_env.pipeline.processar(temperatura(32), ORIGEM_SOLO)
    assert alarmes_de(regras_env) == []
    relogio.avancar(seconds=70)
    regras_env.pipeline.processar(temperatura(33), ORIGEM_SOLO)
    assert len(alarmes_de(regras_env)) == 1


def test_janela_interrompida_recomeca_a_contagem(regras_env, relogio):
    regras_env.regras.inserir_regra(
        "coop-cerrado", regra("silo-quente", "janela", "temperatura_solo", ">", 30, duracao_s=120)
    )
    # t=0: 31 | t=60: 25 (interrompe) | t=70: 31 (recomeça) | t=130: 32 | t=190: 34
    for avanco, valor in ((0, 31), (60, 25), (10, 31), (60, 32)):
        relogio.avancar(seconds=avanco)
        regras_env.pipeline.processar(temperatura(valor), ORIGEM_SOLO)
    assert alarmes_de(regras_env) == []  # sem a interrupção, já teria disparado em t=130
    relogio.avancar(seconds=60)
    regras_env.pipeline.processar(temperatura(34), ORIGEM_SOLO)
    assert len(alarmes_de(regras_env)) == 1


def test_ausencia_de_dados(regras_env, relogio, catalogo):
    regras_env.regras.inserir_regra(
        "coop-cerrado", regra("sem-dados", "ausencia", operador=None, valor=None, duracao_s=600)
    )
    # Dispositivo cadastrado há pouco e sem leitura ainda não dispara.
    catalogo.adicionar_dispositivo(
        DispositivoCadastrado(
            "coop-cerrado", "solo-novo", "sensor-solo", "agricultura", "fazenda-boa-vista", criado_em=AGORA
        )
    )
    catalogo.adicionar_dispositivo(
        DispositivoCadastrado(
            "coop-cerrado", "solo-revogado", "sensor-solo", "agricultura", "fazenda-boa-vista", revogado_em=AGORA
        )
    )
    regras_env.pipeline.processar(umidade(30), ORIGEM_SOLO)

    assert regras_env.motor.verificar_ausencias(AGORA + timedelta(minutes=5)) == []
    disparos = regras_env.motor.verificar_ausencias(AGORA + timedelta(minutes=11))
    assert sorted(disparo.dispositivo for disparo in disparos) == ["solo-novo", "solo-talhao07-02"]
    assert regras_env.motor.verificar_ausencias(AGORA + timedelta(minutes=12)) == []

    # A leitura volta: o alarme é resolvido e a regra rearma.
    relogio.avancar(minutes=13)
    regras_env.pipeline.processar(umidade(30), ORIGEM_SOLO)
    estados = {alarme.dispositivo: alarme.estado for alarme in alarmes_de(regras_env)}
    assert estados == {"solo-novo": EstadoAlarme.ATIVO, "solo-talhao07-02": EstadoAlarme.RESOLVIDO}


def test_dado_atrasado_nao_gera_alarme(regras_env):
    # RF-ING-04: medição de 48 h atrás entra no histórico, mas não dispara regra.
    regras_env.regras.inserir_regra("coop-cerrado", regra())
    atrasada = mensagem(timestamp="2026-10-17T05:10:00Z", medidas=[{"grandeza": "umidade_solo", "valor": 5.0}])
    assert regras_env.pipeline.processar(atrasada, ORIGEM_BORDA).situacao is Situacao.ACEITA
    assert alarmes_de(regras_env) == []


def test_filtros_da_condicao(regras_env):
    for nova in (
        regra("outra-area", area="talhao-08"),
        regra("outro-dispositivo", dispositivo="solo-99"),
        regra("outro-dominio", dominio="clima"),
        regra("inativa", ativa=False),
        regra("da-borda", ambito="borda"),
    ):
        regras_env.regras.inserir_regra("coop-cerrado", nova)
    regras_env.regras.inserir_regra("semma", regra("de-outro-inquilino"))
    regras_env.regras.inserir_regra("coop-cerrado", regra("desta-area", area="talhao-07", site="fazenda-boa-vista"))

    regras_env.pipeline.processar(umidade(10), ORIGEM_SOLO)
    assert [alarme.regra for alarme in alarmes_de(regras_env)] == ["desta-area"]


def test_valor_nao_numerico_e_grandeza_ausente_nao_disparam(regras_env):
    regras_env.regras.inserir_regra("coop-cerrado", regra())
    regras_env.pipeline.processar(umidade("seco"), ORIGEM_SOLO)
    regras_env.pipeline.processar(temperatura(10), ORIGEM_SOLO)
    assert alarmes_de(regras_env) == []


def test_falha_em_uma_acao_nao_impede_as_outras(regras_env):
    class Quebrado:
        def enviar(self, url, carga):
            raise ConnectionError("destino fora do ar")

    regras_env.motor._executores[TipoAcao.WEBHOOK]._cliente = Quebrado()
    acoes = [Acao(TipoAcao.WEBHOOK, url="http://fora-do-ar"), Acao(TipoAcao.ALARME)]
    regras_env.regras.inserir_regra("coop-cerrado", regra(acoes=acoes))
    regras_env.pipeline.processar(umidade(10), ORIGEM_SOLO)
    [alarme] = alarmes_de(regras_env)
    assert alarme.severidade is Severidade.AVISO


def test_falha_no_motor_nao_desfaz_a_ingestao(regras_env, repositorio, monkeypatch):
    def quebrar(_inquilino, _ambito):
        raise RuntimeError("banco de regras indisponível")

    monkeypatch.setattr(regras_env.regras, "regras_ativas", quebrar)
    assert regras_env.pipeline.processar(umidade(10), ORIGEM_SOLO).situacao is Situacao.ACEITA
    assert len(repositorio.mensagens) == 1


def test_alarme_gerado_na_borda_chega_com_o_horario_da_ocorrencia(regras_env):
    # RF-PRO-05: alarme da borda durante a desconexão aparece com o horário em que ocorreu.
    evento = mensagem(
        tipo="evento",
        medidas=None,
        timestamp="2026-10-18T22:00:00Z",
        via="borda-fazenda-boa-vista",
        evento={
            "nome": "alarme",
            "severidade": "critico",
            "detalhes": {"regra": "irrigacao-talhao07", "mensagem": "Umidade baixa no talhão 07"},
        },
    )
    regras_env.pipeline.processar(evento, ORIGEM_BORDA)
    [alarme] = alarmes_de(regras_env)
    assert (alarme.origem, alarme.regra, alarme.severidade) == ("borda", "irrigacao-talhao07", Severidade.CRITICO)
    assert alarme.ocorrido_em.isoformat() == "2026-10-18T22:00:00+00:00"
    assert alarme.id_mensagem == evento["id_mensagem"]


def test_evento_comum_nao_gera_alarme(regras_env):
    evento = mensagem(tipo="evento", medidas=None, evento={"nome": "porta_aberta"})
    regras_env.pipeline.processar(evento, ORIGEM_SOLO)
    assert alarmes_de(regras_env) == []


def test_cache_de_regras_e_esquecido_quando_uma_regra_muda(regras_env, relogio):
    from dominio.modelos import Origem, TipoOrigem
    from dominio.regras import ServicoDeRegras

    regras_env.motor._validade_do_cache_s = 3600
    servico = ServicoDeRegras(regras_env.regras, relogio, ao_mudar=regras_env.motor.esquecer_cache)
    regras_env.pipeline.processar(umidade(30), ORIGEM_SOLO)
    servico.criar(Origem(TipoOrigem.CHAVE, "coop-cerrado", papel="gestor"), regra())
    relogio.avancar(seconds=30)
    regras_env.pipeline.processar(umidade(10), ORIGEM_SOLO)
    assert len(alarmes_de(regras_env)) == 1
    assert replace(alarmes_de(regras_env)[0], mensagem=None).regra == "umidade-baixa"
