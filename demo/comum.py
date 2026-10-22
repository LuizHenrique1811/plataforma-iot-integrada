"""Apoio dos scripts de demonstração: só biblioteca padrão (urllib), como qualquer integrador poderia fazer."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_DE_TOKENS = RAIZ / "demo" / ".env.demo"
CENTRAL = os.environ.get("CENTRAL_URL", "http://host.docker.internal:8000")
BORDA = os.environ.get("BORDA_URL", "http://host.docker.internal:8001")


def ler_env(caminho: Path) -> dict[str, str]:
    if not caminho.exists():
        return {}
    valores = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            chave, valor = linha.split("=", 1)
            valores[chave.strip()] = valor.strip()
    return valores


def gravar_env(caminho: Path, novos: dict[str, str]) -> None:
    """Atualiza ou acrescenta variáveis, preservando o resto do arquivo."""
    linhas = caminho.read_text(encoding="utf-8").splitlines() if caminho.exists() else []
    pendentes = dict(novos)
    for indice, linha in enumerate(linhas):
        chave = linha.split("=", 1)[0].strip()
        if chave in pendentes:
            linhas[indice] = f"{chave}={pendentes.pop(chave)}"
    linhas += [f"{chave}={valor}" for chave, valor in pendentes.items()]
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")


class Api:
    def __init__(self, nome: str, base: str, chave: str, inquilino: str | None = None) -> None:
        self.nome = nome
        self._base = base.rstrip("/")
        self._cabecalhos = {"Content-Type": "application/json", "X-Chave-API": chave}
        if inquilino:
            self._cabecalhos["X-Inquilino"] = inquilino

    def chamar(self, metodo: str, caminho: str, corpo: Any = None) -> tuple[int, Any]:
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        requisicao = urllib.request.Request(self._base + caminho, data=dados, headers=self._cabecalhos, method=metodo)
        try:
            with urllib.request.urlopen(requisicao, timeout=15) as resposta:
                return resposta.status, json.loads(resposta.read() or b"null")
        except urllib.error.HTTPError as erro:
            conteudo = erro.read()
            try:
                return erro.code, json.loads(conteudo or b"null")
            except ValueError:
                return erro.code, conteudo.decode("utf-8", errors="replace")
        except urllib.error.URLError as erro:
            sys.exit(f"{self.nome} fora do ar em {self._base}: {erro.reason}. Suba os serviços (infra/README.md).")

    def garantir(self, caminho: str, corpo: dict[str, Any], descricao: str) -> tuple[int, Any]:
        """Cria o recurso; se ele já existe (409), segue em frente. Assim o script pode rodar de novo."""
        status, resposta = self.chamar("POST", caminho, corpo)
        if status == 201:
            print(f"  [{self.nome}] criado: {descricao}")
        elif status == 409:
            print(f"  [{self.nome}] já existia: {descricao}")
        else:
            sys.exit(f"  [{self.nome}] falhou ao criar {descricao}: HTTP {status} {resposta}")
        return status, resposta
