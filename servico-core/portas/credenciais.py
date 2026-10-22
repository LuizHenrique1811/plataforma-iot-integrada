from typing import Protocol


class GeradorDeCredenciais(Protocol):
    """Emite tokens de dispositivo e chaves de API; o domínio só guarda o hash (ADR-0018)."""

    def novo_segredo(self) -> str: ...

    def novo_id(self) -> str: ...

    def hash(self, segredo: str) -> str: ...
