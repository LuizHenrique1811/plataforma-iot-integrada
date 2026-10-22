from typing import Protocol

from dominio.modelos import Origem


class Autenticador(Protocol):
    """Resolve credenciais em origens autenticadas (ADR-0018)."""

    def por_token_dispositivo(self, token: str) -> Origem | None:
        """Origem do dispositivo dono do token, ou None se o token não existe ou foi revogado."""
        ...

    def por_chave(self, chave: str) -> Origem | None:
        """Origem da chave de API, com inquilino e papel, ou None se inválida ou revogada."""
        ...
