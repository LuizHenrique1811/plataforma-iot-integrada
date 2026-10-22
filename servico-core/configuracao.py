"""Configuração por variáveis de ambiente (Twelve-Factor). Nenhum segredo tem valor padrão."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

PAPEIS = ("central", "borda")


@dataclass(frozen=True)
class Configuracao:
    papel: str = "central"
    # postgresql://... na central; vazio usa adaptadores em memória (só desenvolvimento).
    banco_url: str | None = None
    contratos_dir: Path = Path("/app/contratos")
    # Chave do administrador da plataforma, para criar os primeiros inquilinos e chaves.
    chave_admin: str | None = None
    limite_dado_atual_s: int = 300
    log_nivel: str = "INFO"

    @classmethod
    def do_ambiente(cls, ambiente: Mapping[str, str] = os.environ) -> Configuracao:
        papel = ambiente.get("PAPEL", "central")
        if papel not in PAPEIS:
            raise ValueError(f"PAPEL deve ser um de {PAPEIS}, recebido {papel!r}")
        return cls(
            papel=papel,
            banco_url=ambiente.get("BANCO_URL") or None,
            contratos_dir=Path(ambiente["CONTRATOS_DIR"]) if ambiente.get("CONTRATOS_DIR") else localizar_contratos(),
            chave_admin=ambiente.get("CHAVE_ADMIN") or None,
            limite_dado_atual_s=int(ambiente.get("LIMITE_DADO_ATUAL_S", "300")),
            log_nivel=ambiente.get("LOG_NIVEL", "INFO"),
        )


def localizar_contratos() -> Path:
    """contratos/ ao lado do código (imagem Docker) ou na raiz do repositório."""
    aqui = Path(__file__).resolve().parent
    for candidato in (aqui / "contratos", aqui.parent / "contratos"):
        if (candidato / "json-schema").is_dir():
            return candidato
    raise FileNotFoundError("pasta contratos/ não encontrada; defina CONTRATOS_DIR")
