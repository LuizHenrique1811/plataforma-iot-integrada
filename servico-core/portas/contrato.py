from typing import Any, Protocol

from dominio.modelos import ErroDeCampo


class ValidadorDeContrato(Protocol):
    """Valida mensagens contra o contrato da versão declarada (RF-ING-06)."""

    def versoes(self) -> frozenset[str]:
        """Versões da mensagem canônica que a plataforma aceita."""
        ...

    def validar(self, carga: dict[str, Any]) -> list[ErroDeCampo]:
        """Erros da mensagem; lista vazia quando ela está no contrato."""
        ...

    def validar_lote(self, carga: Any) -> list[ErroDeCampo]:
        """Erros do envelope do lote (os itens são validados um a um depois)."""
        ...
