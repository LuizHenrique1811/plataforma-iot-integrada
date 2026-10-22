"""Dados e utilitários compartilhados pelos testes."""

import uuid
from datetime import UTC, datetime, timedelta

from adaptadores.memoria import CatalogoEmMemoria
from configuracao import localizar_contratos
from dominio.modelos import DispositivoCadastrado, GrandezaDoPerfil, Origem, Perfil, TipoOrigem

CONTRATOS = localizar_contratos()
AGORA = datetime(2026, 10, 19, 5, 15, tzinfo=UTC)

ORIGEM_SOLO = Origem(TipoOrigem.DISPOSITIVO, "coop-cerrado", dispositivo="solo-talhao07-02")
ORIGEM_BORDA = Origem(TipoOrigem.CHAVE, "coop-cerrado", papel="no_borda")

PERFIL_SOLO = Perfil(
    "sensor-solo",
    "Sensor de solo",
    {
        "umidade_solo": GrandezaDoPerfil("umidade_solo", "%", 0, 100),
        "temperatura_solo": GrandezaDoPerfil("temperatura_solo", "Cel", -10, 60),
    },
    900,
)
PERFIL_AR = Perfil("estacao-ar", "Estação de qualidade do ar", {"pm25": GrandezaDoPerfil("pm25", "ug/m3", 0, 1000)}, 60)


class RelogioFixo:
    def __init__(self, instante: datetime) -> None:
        self.instante = instante

    def agora(self) -> datetime:
        return self.instante

    def avancar(self, **intervalo) -> None:
        self.instante += timedelta(**intervalo)


def catalogo_de_exemplo() -> CatalogoEmMemoria:
    catalogo = CatalogoEmMemoria()
    catalogo.adicionar_perfil("coop-cerrado", PERFIL_SOLO)
    catalogo.adicionar_dispositivo(
        DispositivoCadastrado(
            "coop-cerrado", "solo-talhao07-02", "sensor-solo", "agricultura", "fazenda-boa-vista", "talhao-07"
        )
    )
    catalogo.adicionar_perfil("semma", PERFIL_AR)
    catalogo.adicionar_dispositivo(DispositivoCadastrado("semma", "ar-centro-03", "estacao-ar", "ambiente", "centro"))
    return catalogo


def mensagem(**campos) -> dict:
    """Mensagem canônica válida; um campo com valor None é removido."""
    base = {
        "versao": "1.0",
        "id_mensagem": str(uuid.uuid4()),
        "dispositivo": "solo-talhao07-02",
        "tipo": "telemetria",
        "timestamp": "2026-10-19T05:10:00Z",
        "medidas": [{"grandeza": "umidade_solo", "valor": 23.5, "unidade": "%"}],
    }
    base.update(campos)
    return {chave: valor for chave, valor in base.items() if valor is not None}


def regra(
    id_: str = "umidade-baixa",
    tipo: str = "limite",
    grandeza: str = "umidade_solo",
    operador: str | None = "<",
    valor: float | None = 20,
    duracao_s: int | None = None,
    acoes=None,
    ambito: str = "central",
    ativa: bool = True,
    **filtros,
):
    """Regra de teste; por padrão, umidade do solo abaixo de 20% gera alarme crítico."""
    from dominio.regras import Acao, Condicao, Regra, Severidade, TipoAcao, TipoCondicao

    return Regra(
        id_,
        f"Regra {id_}",
        Condicao(TipoCondicao(tipo), grandeza, operador, valor, duracao_s, **filtros),
        tuple(acoes or [Acao(TipoAcao.ALARME, Severidade.CRITICO)]),
        ambito=ambito,
        ativa=ativa,
    )
