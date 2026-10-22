"""Entidades e resultados do domínio.

Nenhum nome de cenário aparece aqui (RNF-08): domínios, perfis e locais são dados do catálogo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class TipoOrigem(StrEnum):
    DISPOSITIVO = "dispositivo"
    CHAVE = "chave"
    MQTT = "mqtt"


# Papéis de chave de API que podem enviar mensagens (ADR-0018).
PAPEIS_QUE_INGEREM = frozenset({"administrador", "gestor", "integrador", "no_borda"})


@dataclass(frozen=True)
class Origem:
    """Quem entregou a mensagem, já autenticado pelo adaptador de entrada."""

    tipo: TipoOrigem
    inquilino: str | None
    dispositivo: str | None = None
    papel: str | None = None

    def descricao(self) -> str:
        partes = [self.tipo.value]
        if self.inquilino:
            partes.append(f"inquilino={self.inquilino}")
        if self.dispositivo:
            partes.append(f"dispositivo={self.dispositivo}")
        if self.papel:
            partes.append(f"papel={self.papel}")
        return " ".join(partes)


@dataclass(frozen=True)
class GrandezaDoPerfil:
    grandeza: str
    unidade: str
    minimo: float | None = None
    maximo: float | None = None

    def fora_da_faixa(self, valor: float) -> bool:
        return (self.minimo is not None and valor < self.minimo) or (self.maximo is not None and valor > self.maximo)


@dataclass(frozen=True)
class Perfil:
    """Tipo de dispositivo como dado (Type Object, ADR-0003)."""

    id: str
    nome: str
    grandezas: dict[str, GrandezaDoPerfil]
    intervalo_envio_s: int


@dataclass(frozen=True)
class DispositivoCadastrado:
    inquilino: str
    id: str
    perfil: str
    dominio: str
    site: str
    area: str | None = None
    revogado_em: datetime | None = None


@dataclass(frozen=True)
class Medida:
    grandeza: str
    valor: float | bool | str
    unidade: str | None
    suspeita: bool = False


@dataclass(frozen=True)
class MensagemAceita:
    """Mensagem validada e enriquecida, pronta para persistir."""

    id_mensagem: str
    inquilino: str
    dispositivo: str
    tipo: str
    timestamp: datetime
    origem_timestamp: str
    recebido_em: datetime
    dominio: str
    perfil: str
    site: str | None
    area: str | None
    via: str | None
    # Diferença entre chegada e medição dentro do limite: só dado atual dispara regra (ADR-0013).
    atual: bool
    medidas: tuple[Medida, ...] = ()
    evento: dict[str, Any] | None = None
    estado: dict[str, Any] | None = None
    # Mensagem canônica com o timestamp efetivo, para encaminhar ou sincronizar sem perda.
    carga: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ErroDeCampo:
    caminho: str
    mensagem: str


class Situacao(StrEnum):
    ACEITA = "aceita"
    DUPLICADA = "duplicada"
    REJEITADA = "rejeitada"


class Etapa(StrEnum):
    VALIDACAO = "validacao"
    AUTORIZACAO = "autorizacao"
    ENRIQUECIMENTO = "enriquecimento"


class Motivo(StrEnum):
    JSON_INVALIDO = "json_invalido"
    FORA_DO_CONTRATO = "fora_do_contrato"
    VERSAO_NAO_SUPORTADA = "versao_nao_suportada"
    ORIGEM_NAO_AUTORIZADA = "origem_nao_autorizada"
    DISPOSITIVO_DIVERGENTE = "dispositivo_divergente"
    DISPOSITIVO_DESCONHECIDO = "dispositivo_desconhecido"
    PERFIL_DESCONHECIDO = "perfil_desconhecido"
    CREDENCIAL_REVOGADA = "credencial_revogada"
    TIPO_NAO_ACEITO = "tipo_nao_aceito"
    GRANDEZA_FORA_DO_PERFIL = "grandeza_fora_do_perfil"
    UNIDADE_INCOMPATIVEL = "unidade_incompativel"


@dataclass(frozen=True)
class Rejeicao:
    etapa: Etapa
    motivo: Motivo
    erros: tuple[ErroDeCampo, ...] = ()


@dataclass(frozen=True)
class ResultadoIngestao:
    situacao: Situacao
    id_mensagem: str | None = None
    rejeicao: Rejeicao | None = None
    mensagem: MensagemAceita | None = None


@dataclass(frozen=True)
class ResultadoLote:
    resultados: tuple[ResultadoIngestao, ...] = ()
    # Preenchido quando o envelope do lote está fora do contrato; nesse caso nada é processado.
    erros_envelope: tuple[ErroDeCampo, ...] = ()

    def contar(self, situacao: Situacao) -> int:
        return sum(1 for resultado in self.resultados if resultado.situacao is situacao)


@dataclass(frozen=True)
class MensagemRejeitada:
    """Registro da DLQ (Dead Letter Channel): nada se perde em silêncio."""

    recebido_em: datetime
    inquilino: str | None
    etapa: Etapa
    motivo: Motivo
    erros: tuple[ErroDeCampo, ...]
    carga: Any
    origem: str
