"""Adaptadores PostgreSQL + TimescaleDB contra um banco real (docker compose de testes ou CI)."""

import os
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from adaptadores.credenciais import hash_segredo
from apoio import AGORA, ORIGEM_BORDA, ORIGEM_SOLO, RelogioFixo, mensagem
from dominio.erros import JaExiste
from dominio.modelos import Situacao, TipoOrigem
from dominio.pipeline import PipelineDeIngestao

URL = os.environ.get("BANCO_URL_TESTE")
pytestmark = [
    pytest.mark.integracao,
    pytest.mark.skipif(not URL, reason="BANCO_URL_TESTE não definida"),
]

if URL:
    from adaptadores.postgres.conexao import aplicar_migracoes, criar_pool
    from adaptadores.postgres.repositorios import (
        AutenticadorPostgres,
        CatalogoPostgres,
        FilaDeRejeitadasPostgres,
        RepositorioDeIngestaoPostgres,
    )


@pytest.fixture(scope="module")
def pool():
    pool = criar_pool(URL)
    aplicar_migracoes(pool)
    with pool.connection() as conexao, conexao.transaction():
        conexao.execute(
            """
            INSERT INTO inquilinos (id, nome) VALUES ('coop-cerrado', 'Cooperativa do Cerrado') ON CONFLICT DO NOTHING;
            INSERT INTO dominios (inquilino_id, id, nome) VALUES ('coop-cerrado', 'agricultura', 'Agricultura')
                ON CONFLICT DO NOTHING;
            INSERT INTO perfis (inquilino_id, id, nome, grandezas, intervalo_envio_s) VALUES (
                'coop-cerrado', 'sensor-solo', 'Sensor de solo',
                '[{"grandeza": "umidade_solo", "unidade": "%", "minimo": 0, "maximo": 100},
                  {"grandeza": "temperatura_solo", "unidade": "Cel"}]', 900) ON CONFLICT DO NOTHING;
            INSERT INTO sites (inquilino_id, id, nome) VALUES ('coop-cerrado', 'fazenda-boa-vista', 'Fazenda Boa Vista')
                ON CONFLICT DO NOTHING;
            INSERT INTO areas (inquilino_id, site_id, id, nome) VALUES
                ('coop-cerrado', 'fazenda-boa-vista', 'talhao-07', 'Talhão 07') ON CONFLICT DO NOTHING;
            """
        )
        conexao.execute(
            "INSERT INTO dispositivos (inquilino_id, id, perfil_id, dominio_id, site_id, area_id, token_hash)"
            " VALUES ('coop-cerrado', 'solo-talhao07-02', 'sensor-solo', 'agricultura', 'fazenda-boa-vista',"
            " 'talhao-07', %s) ON CONFLICT DO NOTHING",
            (hash_segredo("token-solo"),),
        )
        # Dispositivo só do teste de último estado, para não depender do que outros testes gravaram.
        conexao.execute(
            "INSERT INTO dispositivos (inquilino_id, id, perfil_id, dominio_id, site_id)"
            " VALUES ('coop-cerrado', 'estado-01', 'sensor-solo', 'agricultura', 'fazenda-boa-vista')"
            " ON CONFLICT DO NOTHING"
        )
        conexao.execute(
            "INSERT INTO chaves_api (id, inquilino_id, papel, hash) VALUES ('borda-1', 'coop-cerrado', 'no_borda', %s)"
            " ON CONFLICT DO NOTHING",
            (hash_segredo("chave-borda"),),
        )
    yield pool
    pool.close()


@pytest.fixture
def pipeline_pg(pool, validador):
    return PipelineDeIngestao(
        validador,
        CatalogoPostgres(pool),
        RepositorioDeIngestaoPostgres(pool),
        FilaDeRejeitadasPostgres(pool),
        RelogioFixo(AGORA),
    )


def consultar(pool, sql, *parametros):
    with pool.connection() as conexao:
        return conexao.execute(sql, parametros).fetchall()


def test_migracoes_sao_idempotentes(pool):
    assert aplicar_migracoes(pool) == []


def test_catalogo_le_dispositivo_e_perfil(pool):
    catalogo = CatalogoPostgres(pool)
    dispositivo = catalogo.obter_dispositivo("coop-cerrado", "solo-talhao07-02")
    assert (dispositivo.perfil, dispositivo.area) == ("sensor-solo", "talhao-07")
    perfil = catalogo.obter_perfil("coop-cerrado", "sensor-solo")
    assert perfil.grandezas["umidade_solo"].maximo == 100
    assert catalogo.obter_dispositivo("coop-cerrado", "nao-existe") is None
    assert catalogo.obter_perfil("coop-cerrado", "nao-existe") is None


def test_mensagem_persistida_uma_unica_vez(pool, pipeline_pg):
    # RF-ING-08 com o banco real.
    carga = mensagem(
        medidas=[
            {"grandeza": "umidade_solo", "valor": 23.5, "unidade": "%"},
            {"grandeza": "temperatura_solo", "valor": 21.8, "unidade": "Cel"},
        ]
    )
    assert pipeline_pg.processar(carga, ORIGEM_SOLO).situacao is Situacao.ACEITA
    assert pipeline_pg.processar(carga, ORIGEM_SOLO).situacao is Situacao.DUPLICADA

    linhas = consultar(
        pool,
        "SELECT grandeza, valor, area_id, medido_em FROM medicoes WHERE id_mensagem = %s ORDER BY grandeza",
        uuid.UUID(carga["id_mensagem"]),
    )
    assert [(linha[0], linha[1], linha[2]) for linha in linhas] == [
        ("temperatura_solo", 21.8, "talhao-07"),
        ("umidade_solo", 23.5, "talhao-07"),
    ]
    assert linhas[0][3] == datetime(2026, 10, 19, 5, 10, tzinfo=UTC)


def test_corrida_entre_reenvios_grava_uma_vez(pool, pipeline_pg):
    resultado = pipeline_pg.processar(mensagem(), ORIGEM_SOLO)
    repositorio = RepositorioDeIngestaoPostgres(pool)
    assert repositorio.persistir(resultado.mensagem) is False


def test_ultimo_estado_nao_regride_com_dado_atrasado(pool, pipeline_pg):
    # ADR-0017: o upsert só troca o valor quando a medição é mais nova.
    for timestamp, valor in (("2026-10-19T05:12:00Z", 31.0), ("2026-10-18T05:12:00Z", 5.0)):
        pipeline_pg.processar(
            mensagem(
                dispositivo="estado-01", timestamp=timestamp, medidas=[{"grandeza": "umidade_solo", "valor": valor}]
            ),
            ORIGEM_BORDA,
        )
    estado = consultar(
        pool,
        "SELECT valor, medido_em FROM ultimo_estado WHERE inquilino_id = 'coop-cerrado'"
        " AND dispositivo_id = 'estado-01' AND grandeza = 'umidade_solo'",
    )
    assert estado == [(31.0, datetime(2026, 10, 19, 5, 12, tzinfo=UTC))]


def test_valor_booleano_e_texto(pool, pipeline_pg):
    carga = mensagem(
        medidas=[{"grandeza": "umidade_solo", "valor": True}, {"grandeza": "temperatura_solo", "valor": "n/d"}]
    )
    pipeline_pg.processar(carga, ORIGEM_SOLO)
    linhas = consultar(
        pool,
        "SELECT valor, valor_texto FROM medicoes WHERE id_mensagem = %s ORDER BY grandeza",
        uuid.UUID(carga["id_mensagem"]),
    )
    assert linhas == [(None, "n/d"), (1.0, "true")]


def test_evento_e_estado_persistidos(pool, pipeline_pg):
    evento = mensagem(
        tipo="evento",
        medidas=None,
        evento={"nome": "irrigacao_ligada", "severidade": "info", "detalhes": {"umidade": 17.9}},
    )
    estado = mensagem(tipo="estado", medidas=None, estado={"bomba": "ligada"})
    pipeline_pg.processar(evento, ORIGEM_BORDA)
    pipeline_pg.processar(estado, ORIGEM_BORDA)
    linhas = consultar(
        pool,
        "SELECT tipo, nome, dados FROM eventos WHERE id_mensagem IN (%s, %s) ORDER BY tipo",
        uuid.UUID(evento["id_mensagem"]),
        uuid.UUID(estado["id_mensagem"]),
    )
    assert linhas == [("estado", None, {"bomba": "ligada"}), ("evento", "irrigacao_ligada", {"umidade": 17.9})]


def test_rejeitadas_vao_para_a_tabela_da_dlq(pool, pipeline_pg):
    carga = mensagem(id_mensagem="nao-uuid")
    pipeline_pg.processar(carga, ORIGEM_SOLO)
    pipeline_pg.registrar_carga_ilegivel("{quebrado", ORIGEM_SOLO, "JSON inválido")
    linhas = consultar(
        pool,
        "SELECT motivo, carga, carga_texto, erros FROM rejeitadas"
        " WHERE carga->>'id_mensagem' = 'nao-uuid' OR carga_texto = '{quebrado' ORDER BY id",
    )
    assert [linha[0] for linha in linhas[-2:]] == ["fora_do_contrato", "json_invalido"]
    assert linhas[-2][1]["id_mensagem"] == "nao-uuid"
    assert linhas[-2][3][0]["caminho"] == "/id_mensagem"
    assert linhas[-1][2] == "{quebrado"


def test_autenticador_por_token_e_por_chave(pool):
    autenticador = AutenticadorPostgres(pool, chave_admin="admin")
    origem = autenticador.por_token_dispositivo("token-solo")
    assert (origem.tipo, origem.inquilino, origem.dispositivo) == (
        TipoOrigem.DISPOSITIVO,
        "coop-cerrado",
        "solo-talhao07-02",
    )
    assert autenticador.por_token_dispositivo("errado") is None
    assert autenticador.por_chave("chave-borda").papel == "no_borda"
    assert autenticador.por_chave("admin").papel == "administrador"
    assert autenticador.por_chave("errada") is None


def test_dispositivo_revogado_perde_o_token(pool):
    with pool.connection() as conexao:
        conexao.execute(
            "INSERT INTO dispositivos (inquilino_id, id, perfil_id, dominio_id, site_id, token_hash, revogado_em)"
            " VALUES ('coop-cerrado', 'revogado-01', 'sensor-solo', 'agricultura', 'fazenda-boa-vista', %s, now())"
            " ON CONFLICT DO NOTHING",
            (hash_segredo("token-revogado"),),
        )
    assert AutenticadorPostgres(pool).por_token_dispositivo("token-revogado") is None
    dispositivo = CatalogoPostgres(pool).obter_dispositivo("coop-cerrado", "revogado-01")
    assert dispositivo.revogado_em is not None
    assert replace(dispositivo, revogado_em=None).id == "revogado-01"


def test_contato_da_borda_e_situacao_desconhecida(pool, pipeline_pg):
    # ADR-0010 com o banco real: dispositivo atrás de borda sem sincronizar fica "desconhecido".
    from adaptadores.postgres.repositorios import ConsultasPostgres
    from dominio.consultas import ServicoDeConsultas, SituacaoDispositivo
    from dominio.modelos import Origem

    pipeline_pg.processar(mensagem(timestamp="2026-10-19T05:14:00Z", via="borda-fazenda-boa-vista"), ORIGEM_BORDA)
    consultas = ConsultasPostgres(pool)
    assert consultas.contato_da_borda("coop-cerrado", "borda-fazenda-boa-vista") == AGORA
    relogio = RelogioFixo(datetime(2026, 10, 19, 12, 0, tzinfo=UTC))
    servico = ServicoDeConsultas(consultas, CatalogoPostgres(pool), relogio)
    leitor = Origem(TipoOrigem.CHAVE, "coop-cerrado", papel="leitor")
    assert servico.estado(leitor, "solo-talhao07-02").situacao is SituacaoDispositivo.DESCONHECIDO


def test_fluxo_completo_pela_api_com_o_banco(pool):
    # Raiz de composição com PostgreSQL: cadastro, ingestão, consultas e revogação.
    from fastapi.testclient import TestClient

    from apoio import CONTRATOS
    from configuracao import Configuracao
    from principal import criar_aplicacao

    inquilino = f"inq-{uuid.uuid4().hex[:8]}"
    admin = {"X-Chave-API": "admin-pg", "X-Inquilino": inquilino}
    config = Configuracao(banco_url=URL, contratos_dir=CONTRATOS, chave_admin="admin-pg")
    with TestClient(criar_aplicacao(config)) as cliente:
        assert (
            cliente.post("/api/v1/inquilinos", json={"id": inquilino, "nome": "Teste"}, headers=admin).status_code
            == 201
        )
        gestor = {
            "X-Chave-API": cliente.post("/api/v1/chaves", json={"papel": "gestor"}, headers=admin).json()["chave"]
        }
        for caminho, corpo in (
            ("/api/v1/catalogo/dominios", {"id": "ambiente", "nome": "Meio ambiente"}),
            (
                "/api/v1/catalogo/perfis",
                {
                    "id": "estacao-ar",
                    "nome": "Estação",
                    "intervalo_envio_s": 60,
                    "grandezas": [{"grandeza": "pm25", "unidade": "ug/m3", "maximo": 500}],
                },
            ),
            (
                "/api/v1/sites",
                {"id": "centro", "nome": "Centro", "geo": {"type": "Point", "coordinates": [-49.0, -16.0]}},
            ),
            ("/api/v1/sites/centro/areas", {"id": "praca", "nome": "Praça"}),
        ):
            resposta = cliente.post(caminho, json=corpo, headers=gestor)
            assert resposta.status_code == 201, resposta.text
        assert (
            cliente.post("/api/v1/catalogo/dominios", json={"id": "ambiente", "nome": "X"}, headers=gestor).status_code
            == 409
        )
        resposta = cliente.post(
            "/api/v1/dispositivos",
            json={
                "id": "ar-01",
                "perfil": "estacao-ar",
                "dominio": "ambiente",
                "site": "centro",
                "area": "praca",
                "fabricante": "Acme",
                "firmware": "1.2.0",
            },
            headers=gestor,
        )
        assert resposta.status_code == 201, resposta.text
        token = {"Authorization": f"Bearer {resposta.json()['token']}"}

        carga = mensagem(dispositivo="ar-01", timestamp=None, medidas=[{"grandeza": "pm25", "valor": 600}])
        assert cliente.post("/api/v1/ingestao", json=carga, headers=token).status_code == 202
        telemetria = cliente.get("/api/v1/dispositivos/ar-01/telemetria", headers=gestor).json()
        assert telemetria["total"] == 1
        assert telemetria["itens"][0]["suspeita"] is True
        estado = cliente.get("/api/v1/dispositivos/ar-01/estado", headers=gestor).json()
        assert estado["situacao"] == "online"
        detalhe = cliente.get("/api/v1/dispositivos/ar-01", headers=gestor).json()
        assert (detalhe["fabricante"], detalhe["firmware"], detalhe["area"]) == ("Acme", "1.2.0", "praca")
        sites = cliente.get("/api/v1/sites?ordenar=-nome", headers=gestor).json()
        assert sites["itens"][0]["geo"]["type"] == "Point"
        assert cliente.get("/api/v1/dispositivos?area=praca&tamanho=1", headers=gestor).json()["total"] == 1
        assert (
            cliente.get("/api/v1/catalogo/perfis", headers=gestor).json()["itens"][0]["grandezas"][0]["maximo"] == 500
        )

        cliente.post("/api/v1/ingestao", json=mensagem(dispositivo="ar-01", id_mensagem="ruim"), headers=token)
        rejeitadas = cliente.get("/api/v1/rejeitadas", headers=gestor).json()
        assert rejeitadas["itens"][0]["carga"]["id_mensagem"] == "ruim"

        assert cliente.delete("/api/v1/dispositivos/ar-01/credencial", headers=gestor).status_code == 204
        assert cliente.post("/api/v1/ingestao", json=mensagem(dispositivo="ar-01"), headers=token).status_code == 401
        assert cliente.get("/api/v1/dispositivos/ar-01", headers=gestor).json()["revogado_em"] is not None


def test_regras_estado_e_alarmes_no_banco(pool):
    from adaptadores.postgres.regras import AlarmesPostgres, RegrasPostgres
    from apoio import regra
    from dominio.paginacao import Ordenacao, ParametrosDePagina
    from dominio.regras import Alarme, EstadoAlarme, EstadoDaRegra, Severidade

    regras = RegrasPostgres(pool)
    sufixo = uuid.uuid4().hex[:6]
    regras.inserir_regra("coop-cerrado", replace(regra(f"r-{sufixo}"), criado_em=AGORA))
    regras.inserir_regra(
        "coop-cerrado",
        replace(regra(f"a-{sufixo}", "ausencia", operador=None, valor=None, duracao_s=600, site="fazenda-boa-vista")),
    )
    regras.inserir_regra("coop-cerrado", regra(f"b-{sufixo}", ambito="borda"))
    with pytest.raises(JaExiste):
        regras.inserir_regra("coop-cerrado", regra(f"r-{sufixo}"))

    ativas = {r.id for r in regras.regras_ativas("coop-cerrado", "central")}
    assert {f"r-{sufixo}", f"a-{sufixo}"} <= ativas and f"b-{sufixo}" not in ativas
    assert f"a-{sufixo}" in {r.id for _, r in regras.regras_de_ausencia("central")}
    pagina = regras.listar_regras("coop-cerrado", ParametrosDePagina(tamanho=500), Ordenacao("id"))
    assert next(r for r in pagina.itens if r.id == f"r-{sufixo}").criado_em == AGORA

    assert regras.obter_estado("coop-cerrado", f"r-{sufixo}", "solo-talhao07-02") is None
    regras.salvar_estado("coop-cerrado", f"r-{sufixo}", "solo-talhao07-02", EstadoDaRegra(True, AGORA, False))
    regras.salvar_estado("coop-cerrado", f"r-{sufixo}", "solo-talhao07-02", EstadoDaRegra(True, AGORA, True))
    assert regras.obter_estado("coop-cerrado", f"r-{sufixo}", "solo-talhao07-02") == EstadoDaRegra(True, AGORA, True)

    leituras = dict(regras.ultimas_leituras("coop-cerrado", {"site": "fazenda-boa-vista"}, "umidade_solo"))
    assert "solo-talhao07-02" in leituras and "revogado-01" not in leituras

    alarmes = AlarmesPostgres(pool)

    def alarme(origem="central"):
        return Alarme(str(uuid.uuid4()), "coop-cerrado", f"r-{sufixo}", "solo-talhao07-02", Severidade.CRITICO,
                      EstadoAlarme.ATIVO, AGORA, "Solo seco", origem)  # fmt: skip

    primeiro = alarme()
    assert alarmes.inserir_alarme(primeiro) is True
    assert alarmes.inserir_alarme(alarme()) is False  # índice único parcial: um aberto por regra e dispositivo
    assert alarmes.inserir_alarme(alarme("borda")) is True
    assert alarmes.obter_alarme("coop-cerrado", primeiro.id).mensagem == "Solo seco"
    assert alarmes.obter_alarme("coop-cerrado", "nao-e-uuid") is None
    alarmes.atualizar_alarme(replace(primeiro, estado=EstadoAlarme.RECONHECIDO, reconhecido_em=AGORA))
    assert alarmes.obter_alarme("coop-cerrado", primeiro.id).estado is EstadoAlarme.RECONHECIDO
    assert alarmes.resolver_abertos("coop-cerrado", f"r-{sufixo}", "solo-talhao07-02", AGORA) == 1
    abertos = alarmes.listar_alarmes(
        "coop-cerrado",
        {"estado": "ativo", "severidade": "critico"},
        ParametrosDePagina(tamanho=500),
        Ordenacao("ocorrido_em", True),
    )
    assert [a.origem for a in abertos.itens if a.regra == f"r-{sufixo}"] == ["borda"]


def test_regra_dispara_alarme_pela_api_com_o_banco(pool):
    from fastapi.testclient import TestClient

    from apoio import CONTRATOS
    from configuracao import Configuracao
    from principal import criar_aplicacao

    inquilino = f"inq-{uuid.uuid4().hex[:8]}"
    admin = {"X-Chave-API": "admin-pg", "X-Inquilino": inquilino}
    agora = datetime.now(UTC)
    with TestClient(
        criar_aplicacao(Configuracao(banco_url=URL, contratos_dir=CONTRATOS, chave_admin="admin-pg"))
    ) as cliente:
        cliente.post("/api/v1/inquilinos", json={"id": inquilino, "nome": "Teste"}, headers=admin)
        for caminho, corpo in (
            ("/api/v1/catalogo/dominios", {"id": "armazenagem", "nome": "Armazenagem"}),
            (
                "/api/v1/catalogo/perfis",
                {
                    "id": "silo",
                    "nome": "Silo",
                    "intervalo_envio_s": 900,
                    "grandezas": [{"grandeza": "temperatura_graos", "unidade": "Cel"}],
                },
            ),
            ("/api/v1/sites", {"id": "fazenda", "nome": "Fazenda"}),
            (
                "/api/v1/regras",
                {
                    "id": "quente",
                    "nome": "Quente",
                    "acoes": [{"tipo": "alarme", "severidade": "critico"}],
                    "condicao": {"tipo": "limite", "grandeza": "temperatura_graos", "operador": ">", "valor": 30},
                },
            ),
        ):
            assert cliente.post(caminho, json=corpo, headers=admin).status_code == 201
        resposta = cliente.post(
            "/api/v1/dispositivos",
            json={"id": "silo-02", "perfil": "silo", "dominio": "armazenagem", "site": "fazenda"},
            headers=admin,
        )
        token = {"Authorization": f"Bearer {resposta.json()['token']}"}
        for segundos, valor in ((60, 35), (30, 36), (10, 20)):
            carga = mensagem(dispositivo="silo-02", timestamp=(agora - timedelta(seconds=segundos)).isoformat(),
                             medidas=[{"grandeza": "temperatura_graos", "valor": valor}])  # fmt: skip
            assert cliente.post("/api/v1/ingestao", json=carga, headers=token).status_code == 202
        [alarme] = cliente.get("/api/v1/alarmes", headers=admin).json()["itens"]
        assert (alarme["regra"], alarme["estado"]) == ("quente", "resolvido")
        assert cliente.get("/api/v1/regras", headers=admin).json()["itens"][0]["condicao"]["valor"] == 30
