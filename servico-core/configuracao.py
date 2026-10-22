"""Configuração por variáveis de ambiente (Twelve-Factor). Nenhum segredo tem valor padrão."""

from __future__ import annotations

import os
import socket
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
    # mqtt://[usuario:senha@]host:porta; vazio desliga o consumidor MQTT.
    mqtt_url: str | None = None
    mqtt_cliente: str = "servico-core"
    # Nome do grupo de assinatura compartilhada, para dividir a carga entre réplicas; vazio desliga.
    mqtt_grupo: str | None = None
    mqtt_trabalhadores: int = 8
    # Intervalo da verificação de regras de ausência de dados.
    verificacao_ausencia_s: float = 30.0
    # Nó de borda (ADR-0006): identificador, central, chave do nó na central e arquivo da chave da fila.
    borda_id: str | None = None
    central_url: str | None = None
    chave_central: str | None = None
    chave_fila_arquivo: str | None = None
    sincronizacao_s: float = 5.0
    tamanho_do_lote: int = 500

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
            mqtt_url=ambiente.get("MQTT_URL") or None,
            mqtt_cliente=ambiente.get("MQTT_CLIENTE") or f"servico-core-{papel}-{socket.gethostname()}",
            mqtt_grupo=ambiente.get("MQTT_GRUPO") or None,
            mqtt_trabalhadores=int(ambiente.get("MQTT_TRABALHADORES", "8")),
            verificacao_ausencia_s=float(ambiente.get("VERIFICACAO_AUSENCIA_S", "30")),
            borda_id=ambiente.get("BORDA_ID") or None,
            central_url=ambiente.get("CENTRAL_URL") or None,
            chave_central=ambiente.get("CHAVE_CENTRAL") or None,
            chave_fila_arquivo=ambiente.get("CHAVE_FILA_ARQUIVO") or None,
            sincronizacao_s=float(ambiente.get("SINCRONIZACAO_S", "5")),
            tamanho_do_lote=int(ambiente.get("TAMANHO_DO_LOTE", "500")),
        )


def localizar_contratos() -> Path:
    """contratos/ ao lado do código (imagem Docker) ou na raiz do repositório."""
    aqui = Path(__file__).resolve().parent
    for candidato in (aqui / "contratos", aqui.parent / "contratos"):
        if (candidato / "json-schema").is_dir():
            return candidato
    raise FileNotFoundError("pasta contratos/ não encontrada; defina CONTRATOS_DIR")
