"""Tokens de dispositivo e chaves de API: só o hash é guardado (ADR-0018)."""

import hashlib
import secrets


def gerar_segredo() -> str:
    return secrets.token_urlsafe(32)


def hash_segredo(segredo: str) -> str:
    # Segredos aleatórios de 256 bits dispensam um hash lento como bcrypt.
    return hashlib.sha256(segredo.encode("utf-8")).hexdigest()
