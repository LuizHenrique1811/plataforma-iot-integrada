"""Saídas das ações de regras: notificação no log (ADR-0012), webhook por HTTP e publicação sem broker."""

from __future__ import annotations

import json
import logging
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

log = logging.getLogger("servico_core.acoes")


class NotificadorEmLog:
    """No MVP, todo canal (SMS, e-mail, mensagem) é registrado no log; o provedor real é evolução (ADR-0012)."""

    def notificar(self, inquilino: str, canal: str, texto: str, contexto: dict[str, Any]) -> None:
        log.warning(
            "notificação [%s]: %s",
            canal,
            texto,
            extra={"inquilino": inquilino, "dispositivo": contexto.get("dispositivo")},
        )


class ClienteWebhookHttp:
    """POST com o disparo em JSON. Fora da thread de ingestão, para um destino lento não atrasar as mensagens.

    Novas tentativas com espera crescente são o RF-APP-03 (Importante) e ficam para depois.
    """

    def __init__(self, *, tempo_limite_s: float = 5.0, assincrono: bool = True) -> None:
        self._tempo_limite_s = tempo_limite_s
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="webhook") if assincrono else None

    def enviar(self, url: str, carga: dict[str, Any]) -> None:
        if self._executor is None:
            self._post(url, carga)
        else:
            self._executor.submit(self._post, url, carga)

    def encerrar(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True)

    def _post(self, url: str, carga: dict[str, Any]) -> None:
        requisicao = urllib.request.Request(
            url,
            data=json.dumps(carga).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "plataforma-iot-integrada"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(requisicao, timeout=self._tempo_limite_s) as resposta:  # noqa: S310
                log.info("webhook %s respondeu %s", url, resposta.status)
        except Exception:
            log.exception("webhook %s falhou", url)


class PublicadorEmLog:
    """Usado quando não há broker configurado (desenvolvimento): registra o que seria publicado."""

    def publicar(self, topico: str, carga: dict[str, Any]) -> None:
        log.warning("sem broker MQTT; publicação descartada em %s", topico)
