"""Cliente HTTP da borda para a central: POST /api/v1/ingestao/lote com a chave do nó de borda (RF-SEG-05)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from dominio.sincronizacao import CentralIndisponivel


class ClienteDaCentralHttp:
    def __init__(self, url: str, chave: str, borda: str, *, tempo_limite_s: float = 30.0) -> None:
        self._url = url.rstrip("/") + "/api/v1/ingestao/lote"
        self._chave = chave
        self._borda = borda
        self._tempo_limite_s = tempo_limite_s

    def enviar_lote(self, mensagens: list[dict[str, Any]]) -> list[str]:
        corpo = json.dumps({"versao": "1.0", "via": self._borda, "mensagens": mensagens}).encode("utf-8")
        requisicao = urllib.request.Request(
            self._url,
            data=corpo,
            headers={"Content-Type": "application/json", "X-Chave-API": self._chave},
            method="POST",
        )
        try:
            with urllib.request.urlopen(requisicao, timeout=self._tempo_limite_s) as resposta:  # noqa: S310
                dados = json.loads(resposta.read())
        except urllib.error.HTTPError as erro:
            # 4xx/5xx: a central não confirmou; o lote fica na fila (credencial errada também cai aqui).
            raise CentralIndisponivel(f"a central respondeu {erro.code}") from erro
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as erro:
            raise CentralIndisponivel(f"sem resposta da central: {erro}") from erro
        resultados = sorted(dados.get("resultados", []), key=lambda item: item["indice"])
        return [item["situacao"] for item in resultados]
