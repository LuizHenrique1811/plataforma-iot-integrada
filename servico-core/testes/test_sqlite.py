"""Repositórios SQL sobre o SQLite da borda (ADR-0020) e fila cifrada com SQLCipher (RF-SEG-05, ADR-0014)."""

import sqlite3
import uuid
from datetime import timedelta

import pytest

from adaptadores.contrato_jsonschema import ValidadorJsonSchema
from adaptadores.credenciais import GeradorDeCredenciaisSeguro
from adaptadores.postgres.regras import AlarmesPostgres, RegrasPostgres
from adaptadores.postgres.repositorios import (
    AutenticadorPostgres,
    CatalogoPostgres,
    ConsultasPostgres,
    FilaDeRejeitadasPostgres,
)
from adaptadores.sqlite.conexao import (
    PASTA_MIGRACOES,
    PoolSqlite,
    abrir,
    aplicar_migracoes,
    caminho_da_url,
    chave_do_arquivo,
    traduzir,
)
from adaptadores.sqlite.fila import FilaSqlite, RepositorioDeIngestaoDaBorda
from apoio import AGORA, CONTRATOS, PERFIL_SOLO, RelogioFixo, mensagem, regra
from dominio.catalogo import Area, Dominio, Inquilino, ServicoDeCatalogo, Site
from dominio.modelos import DispositivoCadastrado, Origem, Situacao, TipoOrigem
from dominio.paginacao import Ordenacao, ParametrosDePagina
from dominio.pipeline import PipelineDeIngestao
from dominio.regras import Alarme, EstadoAlarme, EstadoDaRegra, Severidade

ADMIN = Origem(TipoOrigem.CHAVE, "coop-cerrado", papel="administrador")
ORIGEM_MQTT = Origem(
    TipoOrigem.MQTT, "coop-cerrado", dispositivo="solo-01", site="fazenda", dominio="agricultura", canal="telemetria"
)
PAGINA = ParametrosDePagina(tamanho=500)


@pytest.fixture
def arquivo_de_chave(tmp_path):
    caminho = tmp_path / "segredos" / "chave-fila"
    caminho.parent.mkdir()
    caminho.write_text("chave de teste da fila\n", encoding="utf-8")
    return str(caminho)


@pytest.fixture
def pool(tmp_path, arquivo_de_chave):
    pool = abrir(f"sqlite:///{tmp_path / 'dados' / 'borda.db'}", arquivo_de_chave)
    aplicar_migracoes(pool)
    yield pool
    pool.close()


@pytest.fixture
def token(pool):
    """Catálogo da borda montado pelo próprio serviço de catálogo, sobre SQLite."""
    servico = ServicoDeCatalogo(CatalogoPostgres(pool), GeradorDeCredenciaisSeguro(), RelogioFixo(AGORA))
    servico.criar_inquilino(Origem(TipoOrigem.CHAVE, None, papel="administrador"), Inquilino("coop-cerrado", "Coop"))
    servico.criar_dominio(ADMIN, Dominio("agricultura", "Agricultura"))
    servico.criar_perfil(ADMIN, PERFIL_SOLO)
    servico.criar_site(ADMIN, Site("fazenda", "Fazenda", {"type": "Point", "coordinates": [-49.1, -16.4]}))
    servico.criar_area(ADMIN, Area("talhao-07", "fazenda", "Talhão 07"))
    _, segredo = servico.cadastrar_dispositivo(
        ADMIN, DispositivoCadastrado("", "solo-01", "sensor-solo", "agricultura", "fazenda", "talhao-07")
    )
    return segredo


@pytest.fixture
def pipeline(pool, token):
    return PipelineDeIngestao(
        ValidadorJsonSchema(CONTRATOS),
        CatalogoPostgres(pool),
        RepositorioDeIngestaoDaBorda(pool, "borda-fazenda"),
        FilaDeRejeitadasPostgres(pool),
        RelogioFixo(AGORA),
    )


def leitura(valor=23.5, **campos):
    return mensagem(dispositivo="solo-01", medidas=[{"grandeza": "umidade_solo", "valor": valor}], **campos)


def test_traducao_do_sql_postgres_para_sqlite():
    sql = "UPDATE t SET a = GREATEST(a, %s), b = now() WHERE definicao->'condicao'->>'tipo' = %s"
    assert traduzir(sql) == (
        "UPDATE t SET a = MAX(a, ?), b = strftime('%Y-%m-%dT%H:%M:%f+00:00','now')"
        " WHERE json_extract(definicao, '$.condicao.tipo') = ?"
    )


def test_url_e_chave(arquivo_de_chave):
    assert caminho_da_url("sqlite:////dados/borda.db") == "/dados/borda.db"
    assert caminho_da_url("sqlite:///borda.db") == "borda.db"
    with pytest.raises(ValueError):
        caminho_da_url("postgresql://x")
    assert len(chave_do_arquivo(arquivo_de_chave)) == 64
    with pytest.raises(ValueError):
        PoolSqlite(":memory:", "não-hexadecimal")


def test_disco_retirado_nao_revela_os_dados(tmp_path, arquivo_de_chave, pool, pipeline):
    # Critério do RF-SEG-05: o arquivo da fila não abre sem a chave, que fica fora do volume de dados.
    pipeline.processar(leitura(valor=12.345), ORIGEM_MQTT)
    arquivo = tmp_path / "dados" / "borda.db"
    pool.close()
    assert b"solo-01" not in arquivo.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(arquivo).execute("SELECT * FROM fila_sincronizacao").fetchall()
    errado = tmp_path / "outra-chave"
    errado.write_text("chave errada", encoding="utf-8")
    with pytest.raises(Exception, match="not a database"):
        abrir(f"sqlite:///{arquivo}", str(errado))
    reaberto = abrir(f"sqlite:///{arquivo}", arquivo_de_chave)
    assert FilaSqlite(reaberto).pendentes() == 1
    reaberto.close()


def test_sem_chave_a_fila_fica_em_claro(tmp_path):
    pool = abrir(f"sqlite:///{tmp_path / 'aberta.db'}")
    assert pool.cifrado is False
    assert aplicar_migracoes(pool) == [arquivo.name for arquivo in sorted(PASTA_MIGRACOES.glob("*.sql"))]
    assert aplicar_migracoes(pool) == []
    pool.close()


def test_ingestao_grava_e_enfileira_na_mesma_transacao(pool, pipeline):
    carga = leitura(valor=130)
    assert pipeline.processar(carga, ORIGEM_MQTT).situacao is Situacao.ACEITA
    assert pipeline.processar(carga, ORIGEM_MQTT).situacao is Situacao.DUPLICADA

    fila = FilaSqlite(pool)
    [item] = fila.proximas(10)
    assert item.carga["id_mensagem"] == carga["id_mensagem"]
    assert item.carga["via"] == "borda-fazenda"  # rastreabilidade do caminho (campo via)
    assert item.carga["origem_timestamp"] == "dispositivo"

    consultas = ConsultasPostgres(pool)
    medicoes = consultas.medicoes("coop-cerrado", "solo-01", None, None, None, PAGINA, Ordenacao("timestamp"))
    [medicao] = medicoes.itens
    assert (medicao.valor, medicao.suspeita, medicao.via) == (130.0, True, None)
    assert medicao.timestamp == AGORA - timedelta(minutes=5)
    assert consultas.ultimo_estado("coop-cerrado", "solo-01")[0].valor == 130.0
    assert consultas.ultimo_contato("coop-cerrado", "solo-01").medido_em == AGORA - timedelta(minutes=5)


def test_falha_ao_enfileirar_desfaz_a_gravacao(pool, pipeline, monkeypatch):
    def falhar(_cursor, _mensagem):
        raise RuntimeError("disco cheio")

    repositorio = pipeline._repositorio
    monkeypatch.setattr(repositorio, "_depois_de_gravar", falhar)
    with pytest.raises(RuntimeError):
        pipeline.processar(leitura(), ORIGEM_MQTT)
    with pool.connection() as conexao:
        assert conexao.execute("SELECT count(*) FROM mensagens_recebidas").fetchone()[0] == 0
        assert conexao.execute("SELECT count(*) FROM medicoes").fetchone()[0] == 0


def test_contato_da_borda_usa_o_maior_horario(pool, pipeline):
    # O segundo envio passa pelo ON CONFLICT com GREATEST, traduzido para MAX no SQLite.
    pipeline.processar(leitura(via="gateway-norte"), ORIGEM_MQTT)
    pipeline._relogio.avancar(minutes=1)
    pipeline.processar(leitura(via="gateway-norte"), ORIGEM_MQTT)
    assert ConsultasPostgres(pool).contato_da_borda("coop-cerrado", "gateway-norte") == AGORA + timedelta(minutes=1)


def test_fila_ordena_eventos_antes_da_telemetria(pool):
    fila = FilaSqlite(pool)
    telemetria = leitura()
    evento = mensagem(dispositivo="solo-01", tipo="evento", medidas=None, evento={"nome": "alarme"})
    fila.enfileirar(telemetria, 1)
    fila.enfileirar(evento, 0)
    fila.enfileirar(evento, 0)  # repetido é ignorado
    itens = fila.proximas(10)
    assert [item.carga["tipo"] for item in itens] == ["evento", "telemetria"]
    fila.remover([itens[0].seq])
    fila.remover([])
    assert fila.pendentes() == 1


def test_catalogo_autenticacao_e_dlq_na_borda(pool, token, pipeline):
    autenticador = AutenticadorPostgres(pool, chave_admin="admin")
    assert autenticador.por_token_dispositivo(token).dispositivo == "solo-01"
    catalogo = CatalogoPostgres(pool)
    assert catalogo.listar_sites("coop-cerrado", PAGINA, Ordenacao("id")).itens[0].geo["type"] == "Point"
    assert catalogo.listar_dispositivos("coop-cerrado", {"area": "talhao-07"}, PAGINA, Ordenacao("id")).total == 1
    assert catalogo.revogar_credencial("coop-cerrado", "solo-01", AGORA) is True
    assert autenticador.por_token_dispositivo(token) is None

    pipeline.processar(leitura(id_mensagem="ruim"), ORIGEM_MQTT)
    pipeline.registrar_carga_ilegivel("{quebrado", ORIGEM_MQTT, "JSON inválido")
    rejeitadas = ConsultasPostgres(pool).rejeitadas("coop-cerrado", PAGINA, Ordenacao("recebido_em"))
    cargas = [item.carga for item in rejeitadas.itens]
    assert "{quebrado" in cargas
    assert any(isinstance(carga, dict) and carga["id_mensagem"] == "ruim" for carga in cargas)


def test_regras_estado_e_alarmes_na_borda(pool, token):
    regras = RegrasPostgres(pool)
    regras.inserir_regra("coop-cerrado", regra("irrigacao", ambito="borda"))
    regras.inserir_regra("coop-cerrado", regra("sem-dados", "ausencia", operador=None, valor=None, duracao_s=60))
    assert [r.id for r in regras.regras_ativas("coop-cerrado", "borda")] == ["irrigacao"]
    assert [r.id for _, r in regras.regras_de_ausencia("central")] == ["sem-dados"]
    assert regras.listar_regras("coop-cerrado", PAGINA, Ordenacao("id")).total == 2

    estado = EstadoDaRegra(True, AGORA, True)
    regras.salvar_estado("coop-cerrado", "irrigacao", "solo-01", estado)
    assert regras.obter_estado("coop-cerrado", "irrigacao", "solo-01") == estado
    [(dispositivo, ultima)] = regras.ultimas_leituras("coop-cerrado", {"site": "fazenda"}, "umidade_solo")
    assert dispositivo == "solo-01" and ultima == AGORA  # sem leitura, vale a data de cadastro

    alarmes = AlarmesPostgres(pool)
    alarme = Alarme(
        str(uuid.uuid4()), "coop-cerrado", "irrigacao", "solo-01", Severidade.CRITICO, EstadoAlarme.ATIVO, AGORA
    )
    assert alarmes.inserir_alarme(alarme) is True
    assert alarmes.inserir_alarme(Alarme(str(uuid.uuid4()), *list(vars(alarme).values())[1:])) is False
    assert alarmes.obter_alarme("coop-cerrado", alarme.id).severidade is Severidade.CRITICO
    assert alarmes.resolver_abertos("coop-cerrado", "irrigacao", "solo-01", AGORA, "central") == 1
    listados = alarmes.listar_alarmes("coop-cerrado", {"estado": "resolvido"}, PAGINA, Ordenacao("ocorrido_em"))
    assert listados.itens[0].resolvido_em == AGORA


def test_identificador_repetido_vira_ja_existe_na_borda(pool, token):
    # Mesmo comportamento da central: o repositório traduz a violação de unicidade em JaExiste (409 na API).
    from dominio.erros import JaExiste

    servico = ServicoDeCatalogo(CatalogoPostgres(pool), GeradorDeCredenciaisSeguro(), RelogioFixo(AGORA))
    administrador = Origem(TipoOrigem.CHAVE, None, papel="administrador")
    with pytest.raises(JaExiste):
        servico.criar_inquilino(administrador, Inquilino("coop-cerrado", "De novo"))
    with pytest.raises(JaExiste):
        servico.criar_dominio(ADMIN, Dominio("agricultura", "De novo"))
    regras = RegrasPostgres(pool)
    regras.inserir_regra("coop-cerrado", regra("dupla"))
    with pytest.raises(JaExiste):
        regras.inserir_regra("coop-cerrado", regra("dupla"))
