"""Teste de desconexão de 72 h (critério de aceite 9.3; RF-EDG-01, RF-EDG-02, RNF-04, RNF-07, RF-ING-08).

As 72 h não são esperadas em tempo real: as leituras chegam à borda com timestamps retroativos, como
chegariam de sensores durante um corte de 72 h. O que se prova:

1. Com o link fora, a borda aceita e guarda tudo na fila cifrada; nada chega à central.
2. A borda é reiniciada no meio do corte (queda de energia) e a fila continua lá (RNF-07).
3. Reenvios de sensores durante o corte são descartados na borda (RF-ING-08).
4. A regra local dispara sem link e o alarme chega depois, com o horário em que ocorreu (RF-EDG-03, RF-PRO-05).
5. Ao reconectar, a resposta do primeiro lote se perde depois de a central gravar; a borda reenvia.
6. A central termina com cada medição exatamente uma vez, na hora da medição (RF-EDG-02).

Banco da central: PostgreSQL se BANCO_URL_TESTE estiver definida (docker compose de testes e CI);
senão, adaptadores em memória.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from configuracao import Configuracao, localizar_contratos
from dominio.modelos import Origem, Situacao, TipoOrigem
from dominio.sincronizacao import CentralIndisponivel
from principal import montar_servico

HORAS = 72
INTERVALO = timedelta(minutes=10)
SENSORES = ("solo-01", "solo-02", "solo-03")
BORDA = "borda-fazenda-boa-vista"
CONTRATOS = localizar_contratos()


class LinkSimulado:
    """O link via satélite entre a borda e a central: pode cair e pode perder a resposta de um lote."""

    def __init__(self, central: TestClient, chave: str) -> None:
        self._central = central
        self._chave = chave
        self.conectado = False
        self.perder_proxima_resposta = False
        self.lotes_entregues = 0

    def enviar_lote(self, mensagens):
        if not self.conectado:
            raise CentralIndisponivel("link via satélite fora do ar")
        resposta = self._central.post(
            "/api/v1/ingestao/lote",
            json={"versao": "1.0", "via": BORDA, "mensagens": mensagens},
            headers={"X-Chave-API": self._chave},
        )
        if resposta.status_code != 200:
            raise CentralIndisponivel(f"a central respondeu {resposta.status_code}")
        self.lotes_entregues += 1
        if self.perder_proxima_resposta:
            self.perder_proxima_resposta = False
            raise CentralIndisponivel("resposta perdida depois de a central gravar")
        return [item["situacao"] for item in sorted(resposta.json()["resultados"], key=lambda item: item["indice"])]


def montar_catalogo(cliente: TestClient, admin: dict, inquilino: str) -> None:
    assert (
        cliente.post("/api/v1/inquilinos", json={"id": inquilino, "nome": "Cooperativa"}, headers=admin).status_code
        == 201
    )
    itens = [
        ("/api/v1/catalogo/dominios", {"id": "agricultura", "nome": "Agricultura"}),
        ("/api/v1/catalogo/perfis", {"id": "sensor-solo", "nome": "Sensor de solo", "intervalo_envio_s": 600,
                                     "grandezas": [{"grandeza": "umidade_solo", "unidade": "%", "minimo": 0,
                                                    "maximo": 100}]}),
        ("/api/v1/sites", {"id": "fazenda-boa-vista", "nome": "Fazenda Boa Vista"}),
        ("/api/v1/sites/fazenda-boa-vista/areas", {"id": "talhao-07", "nome": "Talhão 07"}),
    ] + [
        ("/api/v1/dispositivos", {"id": nome, "perfil": "sensor-solo", "dominio": "agricultura",
                                  "site": "fazenda-boa-vista", "area": "talhao-07"})
        for nome in (*SENSORES, "valvula-talhao07")
    ]  # fmt: skip
    for caminho, corpo in itens:
        resposta = cliente.post(caminho, json=corpo, headers=admin)
        assert resposta.status_code == 201, resposta.text


def leituras(inquilino: str, fim: datetime):
    """72 h de leituras de cada sensor; a última do solo-01 é atual e está abaixo do limite da regra local."""
    instantes = [fim - timedelta(hours=HORAS) + INTERVALO * (k + 1) for k in range(HORAS * 6)]
    origens = {
        sensor: Origem(
            TipoOrigem.MQTT, inquilino, dispositivo=sensor, site="fazenda-boa-vista", dominio="agricultura",
            canal="telemetria",
        )
        for sensor in SENSORES
    }  # fmt: skip
    # Em ordem de tempo, os três sensores a cada instante, como chegariam à borda.
    for indice, instante in enumerate(instantes):
        for sensor, origem in origens.items():
            seco = sensor == "solo-01" and indice == len(instantes) - 1
            valor = 15.0 if seco else 30.0 + (indice % 20)
            carga = {
                "versao": "1.0",
                "id_mensagem": str(uuid.uuid4()),
                "dispositivo": sensor,
                "tipo": "telemetria",
                "timestamp": instante.isoformat().replace("+00:00", "Z"),
                "medidas": [{"grandeza": "umidade_solo", "valor": valor, "unidade": "%"}],
            }
            yield sensor, origem, carga


def test_desconexao_de_72_horas_sem_perda_nem_duplicacao(tmp_path):
    inquilino = f"coop-{uuid.uuid4().hex[:8]}"
    admin_central = {"X-Chave-API": "admin-central", "X-Inquilino": inquilino}
    admin_borda = {"X-Chave-API": "admin-borda", "X-Inquilino": inquilino}
    chave_da_fila = tmp_path / "pendrive" / "chave-fila"
    chave_da_fila.parent.mkdir()
    chave_da_fila.write_text("chave da fila da fazenda", encoding="utf-8")
    config_central = Configuracao(
        banco_url=os.environ.get("BANCO_URL_TESTE"), contratos_dir=CONTRATOS, chave_admin="admin-central"
    )
    config_borda = Configuracao(
        papel="borda",
        banco_url=f"sqlite:///{tmp_path / 'disco-da-borda' / 'borda.db'}",
        borda_id=BORDA,
        chave_fila_arquivo=str(chave_da_fila),
        chave_admin="admin-borda",
        contratos_dir=CONTRATOS,
        sincronizacao_s=3600,  # sincronização chamada à mão no teste
    )

    with TestClient(montar_servico(config_central).app) as central:
        montar_catalogo(central, admin_central, inquilino)
        chave_borda = central.post("/api/v1/chaves", json={"papel": "no_borda"}, headers=admin_central).json()["chave"]
        link = LinkSimulado(central, chave_borda)

        fim = datetime.now(UTC).replace(microsecond=0)
        todas = list(leituras(inquilino, fim))
        metade = len(todas) // 2
        esperadas = {sensor: [] for sensor in SENSORES}
        for sensor, _, carga in todas:
            esperadas[sensor].append(carga["timestamp"])

        # 1. Link cortado: a primeira metade das 72 h chega à borda.
        borda = montar_servico(config_borda, cliente_da_central=link)
        with TestClient(borda.app) as cliente_borda:
            montar_catalogo(cliente_borda, admin_borda, inquilino)
            regra = {
                "id": "irrigacao-talhao07", "nome": "Irrigar o talhão 07 com solo seco", "ambito": "borda",
                "condicao": {"tipo": "limite", "grandeza": "umidade_solo", "operador": "<", "valor": 20},
                "acoes": [{"tipo": "alarme", "severidade": "critico", "mensagem": "Solo seco no talhão 07"},
                          {"tipo": "comando", "dispositivo": "valvula-talhao07", "comando": {"nome": "abrir"}}],
            }  # fmt: skip
            assert cliente_borda.post("/api/v1/regras", json=regra, headers=admin_borda).status_code == 201
            for _, origem, carga in todas[:metade]:
                assert borda.pipeline.processar(carga, origem).situacao is Situacao.ACEITA
            # 3. Sensores reenviam durante o corte: a borda descarta.
            for _, origem, carga in todas[:20]:
                assert borda.pipeline.processar(carga, origem).situacao is Situacao.DUPLICADA
            assert borda.sincronizador.sincronizar().erro == "link via satélite fora do ar"
            pendentes_antes_da_queda = borda.fila.pendentes()
        assert pendentes_antes_da_queda == metade

        # 2. Queda de energia no meio do corte: a borda volta com a mesma fila, lida do disco cifrado.
        borda = montar_servico(config_borda, cliente_da_central=link)
        with TestClient(borda.app):
            assert borda.fila.pendentes() == metade
            for _, origem, carga in todas[metade:]:
                assert borda.pipeline.processar(carga, origem).situacao is Situacao.ACEITA
            # 4. A última leitura do solo-01 disparou a regra local: telemetria + alarme + comando na fila.
            assert borda.fila.pendentes() == len(todas) + 2
            for sensor in SENSORES:
                assert (
                    central.get(f"/api/v1/dispositivos/{sensor}/telemetria", headers=admin_central).json()["total"] == 0
                )

            # 5. O link volta, mas a confirmação do primeiro lote se perde depois de a central gravar.
            link.conectado = True
            link.perder_proxima_resposta = True
            primeira = borda.sincronizador.sincronizar()
            assert (primeira.enviadas, primeira.pendentes) == (0, len(todas) + 2)
            segunda = borda.sincronizador.sincronizar()
            assert (segunda.enviadas, segunda.recusadas, segunda.pendentes) == (len(todas) + 2, 0, 0)
            assert link.lotes_entregues == 1 + -(-(len(todas) + 2) // config_borda.tamanho_do_lote)

        # 6. Na central: cada medição exatamente uma vez, na ordem e na hora da medição.
        for sensor in SENSORES:
            pagina = central.get(f"/api/v1/dispositivos/{sensor}/telemetria?tamanho=500", headers=admin_central).json()
            assert pagina["total"] == HORAS * 6, sensor
            horarios = [item["timestamp"] for item in pagina["itens"]]
            assert horarios == esperadas[sensor]
            assert len({item["id_mensagem"] for item in pagina["itens"]}) == HORAS * 6
            assert {item["via"] for item in pagina["itens"]} == {BORDA}
        [alarme] = central.get("/api/v1/alarmes", headers=admin_central).json()["itens"]
        assert (alarme["origem"], alarme["regra"], alarme["severidade"]) == ("borda", "irrigacao-talhao07", "critico")
        assert alarme["ocorrido_em"] == fim.isoformat().replace("+00:00", "Z")
        assert central.get("/api/v1/rejeitadas", headers=admin_central).json()["total"] == 0
        estado = central.get("/api/v1/dispositivos/solo-01/estado", headers=admin_central).json()
        assert estado["situacao"] == "online"
        assert estado["grandezas"][0]["valor"] == 15.0

    print(
        f"\n72 h de leituras: {len(todas)} mensagens de {len(SENSORES)} sensores, borda reiniciada no meio do corte,"
        f" 20 reenvios descartados na borda, 1 lote reenviado após resposta perdida;"
        f" central com {HORAS * 6} medições por sensor, sem perda nem duplicata."
    )


class _RespostaAceita:
    status_code = 200

    def json(self):
        return {"resultados": [{"indice": 0, "situacao": "aceita"}]}


class _CentralQueGrava:
    def post(self, *_args, **_kwargs):
        return _RespostaAceita()


@pytest.mark.parametrize("perder", [False, True])
def test_link_simulado(perder):
    link = LinkSimulado(_CentralQueGrava(), "chave")
    with pytest.raises(CentralIndisponivel):
        link.enviar_lote([{}])
    link.conectado = True
    link.perder_proxima_resposta = perder
    if perder:
        with pytest.raises(CentralIndisponivel):
            link.enviar_lote([{}])
    assert link.enviar_lote([{}]) == ["aceita"]
