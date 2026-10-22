"""Sincronização da borda em lotes, com remoção só após a confirmação da central (RF-EDG-02)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from adaptadores.central import ClienteDaCentralHttp
from adaptadores.sqlite.conexao import abrir, aplicar_migracoes
from adaptadores.sqlite.fila import FilaSqlite
from apoio import mensagem
from dominio.sincronizacao import CentralIndisponivel, SincronizadorDeBorda, prioridade_de


class CentralFalsa:
    """Grava por id_mensagem, como a central (Idempotent Receiver), e simula falhas do link."""

    def __init__(self) -> None:
        self.gravadas: dict[str, dict] = {}
        self.lotes: list[int] = []
        self.conectada = True
        self.perder_proxima_resposta = False
        self.recusar: set[str] = set()

    def enviar_lote(self, mensagens):
        if not self.conectada:
            raise CentralIndisponivel("link desligado")
        self.lotes.append(len(mensagens))
        situacoes = []
        for carga in mensagens:
            if carga["id_mensagem"] in self.recusar:
                situacoes.append("rejeitada")
            elif carga["id_mensagem"] in self.gravadas:
                situacoes.append("duplicada")
            else:
                self.gravadas[carga["id_mensagem"]] = carga
                situacoes.append("aceita")
        if self.perder_proxima_resposta:
            self.perder_proxima_resposta = False
            raise CentralIndisponivel("resposta perdida depois de a central gravar")
        return situacoes


@pytest.fixture
def fila(tmp_path):
    pool = abrir(f"sqlite:///{tmp_path / 'borda.db'}")
    aplicar_migracoes(pool)
    yield FilaSqlite(pool)
    pool.close()


def encher(fila, quantidade):
    cargas = [mensagem() for _ in range(quantidade)]
    for carga in cargas:
        fila.enfileirar(carga, prioridade_de(carga))
    return cargas


def test_lotes_saem_e_a_fila_esvazia(fila):
    central = CentralFalsa()
    encher(fila, 1200)
    resultado = SincronizadorDeBorda(fila, central, tamanho_do_lote=500).sincronizar()
    assert (resultado.enviadas, resultado.pendentes, resultado.erro) == (1200, 0, None)
    assert central.lotes == [500, 500, 200]
    assert len(central.gravadas) == 1200


def test_sem_link_nada_sai_da_fila(fila):
    central = CentralFalsa()
    central.conectada = False
    encher(fila, 10)
    resultado = SincronizadorDeBorda(fila, central).sincronizar()
    assert (resultado.enviadas, resultado.pendentes) == (0, 10)
    assert "link desligado" in resultado.erro


def test_resposta_perdida_reenvia_e_a_central_nao_duplica(fila):
    # A central gravou, mas a confirmação não chegou: a borda reenvia o lote inteiro.
    central = CentralFalsa()
    central.perder_proxima_resposta = True
    encher(fila, 50)
    sincronizador = SincronizadorDeBorda(fila, central, tamanho_do_lote=20)
    primeiro = sincronizador.sincronizar()
    assert (primeiro.enviadas, primeiro.pendentes) == (0, 50)
    segundo = sincronizador.sincronizar()
    assert (segundo.enviadas, segundo.pendentes) == (50, 0)
    assert len(central.gravadas) == 50
    assert central.lotes == [20, 20, 20, 10]


def test_link_cai_no_meio_e_o_restante_fica_na_fila(fila):
    class CaiNoSegundoLote(CentralFalsa):
        def enviar_lote(self, mensagens):
            if self.lotes:
                self.conectada = False
            return super().enviar_lote(mensagens)

    central = CaiNoSegundoLote()
    encher(fila, 30)
    resultado = SincronizadorDeBorda(fila, central, tamanho_do_lote=10).sincronizar()
    assert (resultado.enviadas, resultado.pendentes) == (10, 20)


def test_confirmacao_incompleta_nao_remove(fila):
    class Incompleta(CentralFalsa):
        def enviar_lote(self, mensagens):
            return super().enviar_lote(mensagens)[:-1]

    encher(fila, 5)
    resultado = SincronizadorDeBorda(fila, Incompleta()).sincronizar()
    assert resultado.pendentes == 5
    assert "4 de 5" in resultado.erro


def test_recusadas_pela_central_saem_da_fila(fila):
    # Ficam na DLQ da central, com o motivo; a borda não as reenvia para sempre.
    central = CentralFalsa()
    cargas = encher(fila, 3)
    central.recusar = {cargas[1]["id_mensagem"]}
    resultado = SincronizadorDeBorda(fila, central).sincronizar()
    assert (resultado.enviadas, resultado.recusadas, resultado.pendentes) == (3, 1, 0)


def test_eventos_saem_antes_da_telemetria(fila):
    central = CentralFalsa()
    encher(fila, 3)
    evento = mensagem(tipo="evento", medidas=None, evento={"nome": "alarme"})
    fila.enfileirar(evento, prioridade_de(evento))
    SincronizadorDeBorda(fila, central, tamanho_do_lote=1).sincronizar()
    assert next(iter(central.gravadas.values()))["tipo"] == "evento"


class TestClienteHttp:
    @pytest.fixture
    def central_http(self):
        estado = {"status": 200, "recebidos": []}

        class Central(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                estado["recebidos"].append((self.path, self.headers["X-Chave-API"], corpo))
                resultados = [{"indice": i, "situacao": "aceita"} for i in range(len(corpo["mensagens"]))]
                resposta = json.dumps({"resultados": list(reversed(resultados))}).encode()
                self.send_response(estado["status"])
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(resposta)

            def log_message(self, *_):
                pass

        servidor = HTTPServer(("127.0.0.1", 0), Central)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        estado["url"] = f"http://127.0.0.1:{servidor.server_port}"
        yield estado
        servidor.shutdown()

    def test_envia_o_lote_com_a_chave_e_le_o_resultado_por_indice(self, central_http):
        cliente = ClienteDaCentralHttp(central_http["url"] + "/", "chave-borda", "borda-fazenda")
        assert cliente.enviar_lote([mensagem(), mensagem()]) == ["aceita", "aceita"]
        caminho, chave, corpo = central_http["recebidos"][0]
        assert (caminho, chave, corpo["via"], corpo["versao"]) == (
            "/api/v1/ingestao/lote",
            "chave-borda",
            "borda-fazenda",
            "1.0",
        )

    def test_erro_da_central_vira_indisponivel(self, central_http):
        central_http["status"] = 503
        with pytest.raises(CentralIndisponivel, match="503"):
            ClienteDaCentralHttp(central_http["url"], "chave", "borda").enviar_lote([mensagem()])

    def test_sem_conexao_vira_indisponivel(self):
        with pytest.raises(CentralIndisponivel, match="sem resposta"):
            ClienteDaCentralHttp("http://127.0.0.1:1", "chave", "borda", tempo_limite_s=1).enviar_lote([mensagem()])
