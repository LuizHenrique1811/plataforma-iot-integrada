from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from dominio.sincronizacao import ItemDaFila


class FilaDeSincronizacao(Protocol):
    """Fila persistente de mensagens da borda para a central (store-and-forward)."""

    def enfileirar(self, carga: dict[str, Any], prioridade: int) -> None:
        """Ignora um id_mensagem que já está na fila."""
        ...

    def proximas(self, limite: int) -> list[ItemDaFila]:
        """Próximas mensagens por prioridade e ordem de chegada, sem removê-las."""
        ...

    def remover(self, sequencias: list[int]) -> None: ...

    def pendentes(self) -> int: ...


class ClienteDaCentral(Protocol):
    def enviar_lote(self, mensagens: list[dict[str, Any]]) -> list[str]:
        """Envia o lote e devolve a situação de cada mensagem, na ordem (aceita, duplicada ou rejeitada).

        Levanta CentralIndisponivel quando não há confirmação: link fora, tempo esgotado ou erro da central.
        """
        ...
