"""Sincronização da borda com a central em lotes (RF-EDG-02).

A mensagem só sai da fila depois que a central confirma o lote. Se o link cai no meio, ou se a resposta
se perde depois de a central ter gravado, o lote é reenviado inteiro; a deduplicação por id_mensagem na
central garante que cada mensagem seja armazenada uma única vez (ADR-0011).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from portas.sincronizacao import ClienteDaCentral, FilaDeSincronizacao

# Eventos e alarmes saem antes da telemetria rotineira (RF-EDG-05).
PRIORIDADE_EVENTO = 0
PRIORIDADE_TELEMETRIA = 1

log = logging.getLogger("servico_core.sincronizacao")


class CentralIndisponivel(Exception):
    pass


@dataclass(frozen=True)
class ItemDaFila:
    seq: int
    carga: dict[str, Any]


@dataclass(frozen=True)
class ResultadoDaSincronizacao:
    enviadas: int
    recusadas: int
    pendentes: int
    erro: str | None = None


def prioridade_de(carga: dict[str, Any]) -> int:
    return PRIORIDADE_EVENTO if carga.get("tipo") == "evento" else PRIORIDADE_TELEMETRIA


class SincronizadorDeBorda:
    def __init__(self, fila: FilaDeSincronizacao, central: ClienteDaCentral, *, tamanho_do_lote: int = 500) -> None:
        self._fila = fila
        self._central = central
        self._tamanho_do_lote = tamanho_do_lote

    def sincronizar(self) -> ResultadoDaSincronizacao:
        enviadas = recusadas = 0
        while True:
            lote = self._fila.proximas(self._tamanho_do_lote)
            if not lote:
                return ResultadoDaSincronizacao(enviadas, recusadas, 0)
            try:
                situacoes = self._central.enviar_lote([item.carga for item in lote])
                if len(situacoes) != len(lote):
                    raise CentralIndisponivel(f"a central confirmou {len(situacoes)} de {len(lote)} mensagens")
            except CentralIndisponivel as erro:
                pendentes = self._fila.pendentes()
                log.warning("sincronização interrompida: %s (%s pendentes)", erro, pendentes)
                return ResultadoDaSincronizacao(enviadas, recusadas, pendentes, str(erro))
            # Recusadas pela central ficam na DLQ de lá, com o motivo; a borda não as reenvia para sempre.
            recusadas += situacoes.count("rejeitada")
            self._fila.remover([item.seq for item in lote])
            enviadas += len(lote)
            log.info("lote sincronizado: %s mensagens", len(lote))
