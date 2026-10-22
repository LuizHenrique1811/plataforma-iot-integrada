from datetime import datetime
from typing import Protocol


class Relogio(Protocol):
    """Hora atual em UTC. É uma porta para que os testes controlem o tempo (ADR-0009)."""

    def agora(self) -> datetime: ...
