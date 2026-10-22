"""Adaptadores PostgreSQL + TimescaleDB contra um banco real (docker compose de testes ou CI)."""

import os
import uuid
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from adaptadores.credenciais import hash_segredo
from apoio import AGORA, ORIGEM_BORDA, ORIGEM_SOLO, RelogioFixo, mensagem
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
    pipeline_pg.processar(
        mensagem(timestamp="2026-10-19T05:12:00Z", medidas=[{"grandeza": "umidade_solo", "valor": 31.0}]),
        ORIGEM_BORDA,
    )
    pipeline_pg.processar(
        mensagem(timestamp="2026-10-18T05:12:00Z", medidas=[{"grandeza": "umidade_solo", "valor": 5.0}]),
        ORIGEM_BORDA,
    )
    estado = consultar(
        pool,
        "SELECT valor, medido_em FROM ultimo_estado WHERE inquilino_id = 'coop-cerrado'"
        " AND dispositivo_id = 'solo-talhao07-02' AND grandeza = 'umidade_solo'",
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
