from typing import Any, Protocol


class Notificador(Protocol):
    """Canais de notificação: e-mail, aplicativo de mensagens, SMS (ADR-0012)."""

    def notificar(self, inquilino: str, canal: str, texto: str, contexto: dict[str, Any]) -> None: ...


class Publicador(Protocol):
    """Publicação MQTT de comandos e de eventos de regras."""

    def publicar(self, topico: str, carga: dict[str, Any]) -> None: ...


class ClienteWebhook(Protocol):
    """POST de saída para sistemas externos."""

    def enviar(self, url: str, carga: dict[str, Any]) -> None: ...
