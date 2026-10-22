"""Pipeline de ingestão com adaptadores em memória (ADR-0008)."""

from dataclasses import replace
from datetime import UTC, datetime

from apoio import AGORA, ORIGEM_BORDA, ORIGEM_SOLO, mensagem
from dominio.modelos import Etapa, Motivo, Origem, Situacao, TipoOrigem


def test_aceita_telemetria_e_enriquece_com_o_cadastro(pipeline, repositorio):
    # RF-PRO-01: a mensagem armazenada tem inquilino, domínio, local e área do cadastro.
    resultado = pipeline.processar(mensagem(), ORIGEM_SOLO)

    assert resultado.situacao is Situacao.ACEITA
    aceita = repositorio.mensagens[0]
    assert (aceita.inquilino, aceita.dominio, aceita.site, aceita.area) == (
        "coop-cerrado",
        "agricultura",
        "fazenda-boa-vista",
        "talhao-07",
    )
    assert aceita.atual is True
    assert aceita.origem_timestamp == "dispositivo"


def test_reenvio_com_o_mesmo_id_e_armazenado_uma_unica_vez(pipeline, repositorio):
    # RF-ING-08
    carga = mensagem()
    primeiro = pipeline.processar(carga, ORIGEM_BORDA)
    segundo = pipeline.processar(carga, ORIGEM_BORDA)

    assert primeiro.situacao is Situacao.ACEITA
    assert segundo.situacao is Situacao.DUPLICADA
    assert len(repositorio.mensagens) == 1


def test_reenvios_simultaneos_resultam_em_uma_duplicada(pipeline, repositorio, monkeypatch):
    # A checagem rápida pode não ver o reenvio concorrente; a gravação atômica resolve.
    monkeypatch.setattr(repositorio, "ja_recebida", lambda _id: False)
    carga = mensagem()

    assert pipeline.processar(carga, ORIGEM_BORDA).situacao is Situacao.ACEITA
    assert pipeline.processar(carga, ORIGEM_BORDA).situacao is Situacao.DUPLICADA
    assert len(repositorio.mensagens) == 1


def test_mensagem_fora_do_contrato_vai_para_a_dlq_com_os_erros(pipeline, rejeitadas):
    # RF-ING-06
    carga = mensagem(id_mensagem="123", medidas=[])
    resultado = pipeline.processar(carga, ORIGEM_SOLO)

    assert resultado.situacao is Situacao.REJEITADA
    assert resultado.rejeicao.etapa is Etapa.VALIDACAO
    assert resultado.rejeicao.motivo is Motivo.FORA_DO_CONTRATO
    assert {erro.caminho for erro in resultado.rejeicao.erros} == {"/id_mensagem", "/medidas"}
    assert len(rejeitadas.itens) == 1
    assert rejeitadas.itens[0].carga == carga
    assert rejeitadas.itens[0].origem == "dispositivo inquilino=coop-cerrado dispositivo=solo-talhao07-02"


def test_versao_nao_suportada(pipeline):
    resultado = pipeline.processar(mensagem(versao="2.0"), ORIGEM_SOLO)
    assert resultado.rejeicao.motivo is Motivo.VERSAO_NAO_SUPORTADA
    assert resultado.rejeicao.erros[0].caminho == "/versao"


def test_carga_que_nao_e_objeto(pipeline):
    resultado = pipeline.processar([1, 2, 3], ORIGEM_SOLO)
    assert resultado.rejeicao.motivo is Motivo.FORA_DO_CONTRATO
    assert resultado.id_mensagem is None


def test_carga_ilegivel_tambem_vai_para_a_dlq(pipeline, rejeitadas):
    resultado = pipeline.registrar_carga_ilegivel("{quebrado", ORIGEM_SOLO, "Expecting property name")
    assert resultado.rejeicao.motivo is Motivo.JSON_INVALIDO
    assert rejeitadas.itens[0].carga == "{quebrado"


def test_dispositivo_divergente_da_credencial(pipeline):
    resultado = pipeline.processar(mensagem(dispositivo="outro-sensor"), ORIGEM_SOLO)
    assert resultado.rejeicao.etapa is Etapa.AUTORIZACAO
    assert resultado.rejeicao.motivo is Motivo.DISPOSITIVO_DIVERGENTE


def test_papel_que_nao_envia_mensagens(pipeline):
    leitor = Origem(TipoOrigem.CHAVE, "coop-cerrado", papel="leitor")
    assert pipeline.processar(mensagem(), leitor).rejeicao.motivo is Motivo.ORIGEM_NAO_AUTORIZADA


def test_credencial_sem_inquilino(pipeline):
    administrador = Origem(TipoOrigem.CHAVE, None, papel="administrador")
    assert pipeline.processar(mensagem(), administrador).rejeicao.motivo is Motivo.ORIGEM_NAO_AUTORIZADA


def test_dispositivo_nao_cadastrado(pipeline):
    resultado = pipeline.processar(mensagem(dispositivo="nao-existe"), ORIGEM_BORDA)
    assert resultado.rejeicao.etapa is Etapa.ENRIQUECIMENTO
    assert resultado.rejeicao.motivo is Motivo.DISPOSITIVO_DESCONHECIDO


def test_um_inquilino_nao_envia_dados_por_dispositivo_de_outro(pipeline):
    # RF-SEG-03: o dispositivo de coop-cerrado não existe para o inquilino semma.
    integrador_semma = Origem(TipoOrigem.CHAVE, "semma", papel="integrador")
    assert pipeline.processar(mensagem(), integrador_semma).rejeicao.motivo is Motivo.DISPOSITIVO_DESCONHECIDO


def test_perfil_ausente(pipeline, catalogo):
    catalogo.perfis.clear()
    assert pipeline.processar(mensagem(), ORIGEM_SOLO).rejeicao.motivo is Motivo.PERFIL_DESCONHECIDO


def test_grandeza_fora_do_perfil(pipeline):
    carga = mensagem(medidas=[{"grandeza": "pm25", "valor": 10}])
    resultado = pipeline.processar(carga, ORIGEM_SOLO)
    assert resultado.rejeicao.motivo is Motivo.GRANDEZA_FORA_DO_PERFIL
    assert resultado.rejeicao.erros[0].caminho == "/medidas/0/grandeza"


def test_unidade_convertida_para_a_do_perfil(pipeline, repositorio):
    # RF-PRO-01: normalizar unidades.
    carga = mensagem(medidas=[{"grandeza": "temperatura_solo", "valor": 71.6, "unidade": "[degF]"}])
    pipeline.processar(carga, ORIGEM_SOLO)
    medida = repositorio.mensagens[0].medidas[0]
    assert medida.unidade == "Cel"
    assert round(medida.valor, 6) == 22.0


def test_unidade_sem_conversao(pipeline):
    carga = mensagem(medidas=[{"grandeza": "umidade_solo", "valor": 20, "unidade": "Cel"}])
    assert pipeline.processar(carga, ORIGEM_SOLO).rejeicao.motivo is Motivo.UNIDADE_INCOMPATIVEL


def test_medida_sem_unidade_usa_a_do_perfil(pipeline, repositorio):
    pipeline.processar(mensagem(medidas=[{"grandeza": "umidade_solo", "valor": 30}]), ORIGEM_SOLO)
    assert repositorio.mensagens[0].medidas[0].unidade == "%"


def test_medida_fora_da_faixa_e_marcada_como_suspeita(pipeline, repositorio):
    # RF-CEN-02: fora da faixa é suspeita, não recusada.
    resultado = pipeline.processar(mensagem(medidas=[{"grandeza": "umidade_solo", "valor": 130}]), ORIGEM_SOLO)
    assert resultado.situacao is Situacao.ACEITA
    assert repositorio.mensagens[0].medidas[0].suspeita is True


def test_valor_nao_numerico_e_guardado_sem_conversao(pipeline, repositorio):
    carga = mensagem(medidas=[{"grandeza": "umidade_solo", "valor": "seco"}])
    assert pipeline.processar(carga, ORIGEM_SOLO).situacao is Situacao.ACEITA
    assert repositorio.mensagens[0].medidas[0].valor == "seco"


def test_sem_timestamp_a_recepcao_carimba_a_hora(pipeline, repositorio):
    # ADR-0009
    pipeline.processar(mensagem(timestamp=None), ORIGEM_SOLO)
    aceita = repositorio.mensagens[0]
    assert aceita.timestamp == AGORA
    assert aceita.origem_timestamp == "recepcao"
    assert aceita.carga["timestamp"] == "2026-10-19T05:15:00Z"


def test_timestamp_no_futuro_e_substituido_pela_recepcao(pipeline, repositorio):
    pipeline.processar(mensagem(timestamp="2027-01-01T00:00:00Z"), ORIGEM_SOLO)
    assert repositorio.mensagens[0].timestamp == AGORA


def test_timestamp_de_relogio_zerado_e_substituido_pela_recepcao(pipeline, repositorio):
    pipeline.processar(mensagem(timestamp="1970-01-01T00:00:10Z"), ORIGEM_SOLO)
    assert repositorio.mensagens[0].origem_timestamp == "recepcao"


def test_carimbo_feito_pela_borda_e_preservado_na_central(pipeline, repositorio):
    pipeline.processar(mensagem(origem_timestamp="recepcao"), ORIGEM_BORDA)
    assert repositorio.mensagens[0].origem_timestamp == "recepcao"


def test_dado_atrasado_entra_no_historico_sem_ser_atual(pipeline, repositorio):
    # RF-ING-04: medição de 48 h atrás entra na posição certa e não conta como atual.
    resultado = pipeline.processar(mensagem(timestamp="2026-10-17T05:10:00Z"), ORIGEM_BORDA)
    assert resultado.situacao is Situacao.ACEITA
    aceita = repositorio.mensagens[0]
    assert aceita.timestamp == datetime(2026, 10, 17, 5, 10, tzinfo=UTC)
    assert aceita.atual is False


def test_dado_atrasado_nao_sobrescreve_o_ultimo_estado(pipeline, repositorio):
    # ADR-0017
    pipeline.processar(mensagem(medidas=[{"grandeza": "umidade_solo", "valor": 23.5}]), ORIGEM_BORDA)
    atrasada = mensagem(timestamp="2026-10-19T03:10:00Z", medidas=[{"grandeza": "umidade_solo", "valor": 10.0}])
    pipeline.processar(atrasada, ORIGEM_BORDA)

    medida, _ = repositorio.ultimo_estado[("coop-cerrado", "solo-talhao07-02", "umidade_solo")]
    assert medida.valor == 23.5
    assert len(repositorio.mensagens) == 2


def test_local_da_mensagem_prevalece_sobre_o_cadastro(pipeline, repositorio):
    pipeline.processar(mensagem(local={"site": "fazenda-boa-vista", "area": "talhao-08"}), ORIGEM_SOLO)
    assert repositorio.mensagens[0].area == "talhao-08"


def test_evento_gerado_na_borda_e_aceito_com_o_horario_da_ocorrencia(pipeline, repositorio):
    # RF-PRO-05: alarme ou evento gerado na borda chega com o horário em que ocorreu.
    carga = mensagem(
        tipo="evento",
        medidas=None,
        timestamp="2026-10-19T02:00:00Z",
        via="borda-fazenda-boa-vista",
        evento={"nome": "irrigacao_ligada", "severidade": "info"},
    )
    assert pipeline.processar(carga, ORIGEM_BORDA).situacao is Situacao.ACEITA
    aceita = repositorio.mensagens[0]
    assert aceita.evento["nome"] == "irrigacao_ligada"
    assert aceita.timestamp == datetime(2026, 10, 19, 2, 0, tzinfo=UTC)
    assert aceita.via == "borda-fazenda-boa-vista"


def test_comando_nao_e_aceito_na_ingestao(pipeline):
    carga = mensagem(tipo="comando", medidas=None, comando={"nome": "abrir"})
    assert pipeline.processar(carga, ORIGEM_BORDA).rejeicao.motivo is Motivo.TIPO_NAO_ACEITO


def test_medicao_posterior_a_revogacao_e_recusada(pipeline, catalogo):
    # ADR-0015: mitigação na central para dados vindos da borda após a revogação.
    chave = ("coop-cerrado", "solo-talhao07-02")
    catalogo.dispositivos[chave] = replace(
        catalogo.dispositivos[chave], revogado_em=datetime(2026, 10, 19, 5, 0, tzinfo=UTC)
    )
    depois = pipeline.processar(mensagem(timestamp="2026-10-19T05:10:00Z"), ORIGEM_BORDA)
    antes = pipeline.processar(mensagem(timestamp="2026-10-19T04:50:00Z"), ORIGEM_BORDA)

    assert depois.rejeicao.motivo is Motivo.CREDENCIAL_REVOGADA
    assert antes.situacao is Situacao.ACEITA


def test_lote_tem_resultado_por_mensagem(pipeline):
    # RF-ING-03
    mensagens = [mensagem(), mensagem(id_mensagem="ruim"), mensagem()]
    mensagens.append(dict(mensagens[0]))  # reenvio dentro do mesmo lote
    lote = pipeline.processar_lote({"versao": "1.0", "mensagens": mensagens}, ORIGEM_BORDA)

    assert [resultado.situacao for resultado in lote.resultados] == [
        Situacao.ACEITA,
        Situacao.REJEITADA,
        Situacao.ACEITA,
        Situacao.DUPLICADA,
    ]
    assert (lote.contar(Situacao.ACEITA), lote.contar(Situacao.REJEITADA)) == (2, 1)


def test_envelope_de_lote_invalido_nao_processa_nada(pipeline, repositorio):
    lote = pipeline.processar_lote({"versao": "1.0", "mensagens": []}, ORIGEM_BORDA)
    assert lote.erros_envelope
    assert lote.resultados == ()
    assert repositorio.mensagens == []


def test_perfil_e_consultado_uma_vez(pipeline, catalogo, monkeypatch):
    # ADR-0022: perfis não mudam depois de criados, então o pipeline não os consulta a cada mensagem.
    consultas = []
    original = catalogo.obter_perfil

    def contar(inquilino, perfil):
        consultas.append(perfil)
        return original(inquilino, perfil)

    monkeypatch.setattr(catalogo, "obter_perfil", contar)
    for _ in range(3):
        assert pipeline.processar(mensagem(timestamp=None), ORIGEM_SOLO).situacao is Situacao.ACEITA
    assert consultas == ["sensor-solo"]
