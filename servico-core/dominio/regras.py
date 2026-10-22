"""Regras condição -> ação e alarmes (RF-PRO-02, RF-PRO-03, RF-PRO-05).

Regras são dados do catálogo do inquilino (RNF-08): nenhuma condição de cenário fica no código.
"""

from __future__ import annotations

import operator
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from dominio.erros import DadosInvalidos
from dominio.modelos import ErroDeCampo, MensagemAceita, Origem
from dominio.paginacao import Pagina, ParametrosDePagina
from dominio.permissoes import Permissao, exigir
from portas.regras import RepositorioDeRegras
from portas.relogio import Relogio


class TipoCondicao(StrEnum):
    LIMITE = "limite"
    JANELA = "janela"
    AUSENCIA = "ausencia"


class TipoAcao(StrEnum):
    ALARME = "alarme"
    NOTIFICAR = "notificar"
    COMANDO = "comando"
    WEBHOOK = "webhook"
    PUBLICAR = "publicar"


class Severidade(StrEnum):
    INFO = "info"
    AVISO = "aviso"
    CRITICO = "critico"


class EstadoAlarme(StrEnum):
    ATIVO = "ativo"
    RECONHECIDO = "reconhecido"
    RESOLVIDO = "resolvido"


OPERADORES: dict[str, Callable[[float, float], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}
FILTROS = ("dispositivo", "dominio", "site", "area")


@dataclass(frozen=True)
class Condicao:
    tipo: TipoCondicao
    grandeza: str
    operador: str | None = None
    valor: float | None = None
    duracao_s: int | None = None
    dispositivo: str | None = None
    dominio: str | None = None
    site: str | None = None
    area: str | None = None

    def atende(self, valor: Any) -> bool:
        """Comparação numérica; valores não numéricos nunca atendem a condição."""
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            return False
        return OPERADORES[self.operador](float(valor), self.valor)

    def casa_com(self, mensagem: MensagemAceita) -> bool:
        """Filtros por dispositivo, domínio, local e área; no MVP a área é o identificador (inconsistência 2)."""
        return all(
            getattr(self, campo) is None or getattr(self, campo) == getattr(mensagem, campo) for campo in FILTROS
        )

    def filtros(self) -> dict[str, str]:
        return {campo: getattr(self, campo) for campo in FILTROS if getattr(self, campo) is not None}


@dataclass(frozen=True)
class Acao:
    tipo: TipoAcao
    severidade: Severidade | None = None
    mensagem: str | None = None
    canal: str | None = None
    comando: dict[str, Any] | None = None
    url: str | None = None
    topico: str | None = None
    dispositivo: str | None = None


@dataclass(frozen=True)
class Regra:
    id: str
    nome: str
    condicao: Condicao
    acoes: tuple[Acao, ...]
    ambito: str = "central"
    ativa: bool = True
    criado_em: datetime | None = None


@dataclass(frozen=True)
class Alarme:
    id: str
    inquilino: str
    regra: str
    dispositivo: str
    severidade: Severidade
    estado: EstadoAlarme
    ocorrido_em: datetime
    mensagem: str | None = None
    origem: str = "central"
    reconhecido_em: datetime | None = None
    resolvido_em: datetime | None = None
    id_mensagem: str | None = None


@dataclass(frozen=True)
class EstadoDaRegra:
    """Estado de uma regra para um dispositivo: dispara na transição, não a cada mensagem."""

    condicao_ativa: bool = False
    desde: datetime | None = None
    disparada: bool = False


@dataclass(frozen=True)
class Disparo:
    regra: Regra
    inquilino: str
    dispositivo: str
    grandeza: str
    valor: Any
    ocorrido_em: datetime
    site: str | None = None
    dominio: str | None = None
    area: str | None = None

    def como_json(self) -> dict[str, Any]:
        return {
            "regra": self.regra.id,
            "nome": self.regra.nome,
            "inquilino": self.inquilino,
            "dispositivo": self.dispositivo,
            "grandeza": self.grandeza,
            "valor": self.valor,
            "ocorrido_em": self.ocorrido_em.isoformat().replace("+00:00", "Z"),
            "site": self.site,
            "dominio": self.dominio,
            "area": self.area,
        }

    def texto(self) -> str:
        return f"Regra {self.regra.nome}: {self.grandeza} = {self.valor} em {self.dispositivo}"


# Conversão de e para o formato do contrato (Regra em openapi.yaml) -------------------------


def regra_de_dict(dados: dict[str, Any]) -> Regra:
    condicao = dados["condicao"]
    return Regra(
        id=dados["id"],
        nome=dados["nome"],
        ambito=dados.get("ambito", "central"),
        ativa=dados.get("ativa", True),
        condicao=Condicao(
            tipo=TipoCondicao(condicao["tipo"]),
            grandeza=condicao["grandeza"],
            operador=condicao.get("operador"),
            valor=condicao.get("valor"),
            duracao_s=condicao.get("duracao_s"),
            **{campo: condicao.get(campo) for campo in FILTROS},
        ),
        acoes=tuple(
            Acao(
                tipo=TipoAcao(acao["tipo"]),
                severidade=Severidade(acao["severidade"]) if acao.get("severidade") else None,
                mensagem=acao.get("mensagem"),
                canal=acao.get("canal"),
                comando=acao.get("comando"),
                url=acao.get("url"),
                topico=acao.get("topico"),
                dispositivo=acao.get("dispositivo"),
            )
            for acao in dados["acoes"]
        ),
    )


def regra_para_dict(regra: Regra) -> dict[str, Any]:
    condicao = regra.condicao
    return {
        "id": regra.id,
        "nome": regra.nome,
        "ambito": regra.ambito,
        "ativa": regra.ativa,
        "condicao": _sem_nulos(
            {
                "tipo": condicao.tipo.value,
                "grandeza": condicao.grandeza,
                "operador": condicao.operador,
                "valor": condicao.valor,
                "duracao_s": condicao.duracao_s,
                **condicao.filtros(),
            }
        ),
        "acoes": [
            _sem_nulos(
                {
                    "tipo": acao.tipo.value,
                    "severidade": acao.severidade.value if acao.severidade else None,
                    "mensagem": acao.mensagem,
                    "canal": acao.canal,
                    "comando": acao.comando,
                    "url": acao.url,
                    "topico": acao.topico,
                    "dispositivo": acao.dispositivo,
                }
            )
            for acao in regra.acoes
        ],
    }


def _sem_nulos(dados: dict[str, Any]) -> dict[str, Any]:
    return {chave: valor for chave, valor in dados.items() if valor is not None}


def validar_regra(regra: Regra, inquilino: str) -> None:
    """Regras de consistência que o JSON Schema do contrato não expressa."""
    erros = []
    condicao = regra.condicao
    if condicao.tipo in (TipoCondicao.LIMITE, TipoCondicao.JANELA):
        if condicao.operador is None:
            erros.append(ErroDeCampo("/condicao/operador", "obrigatório para limite e janela"))
        if condicao.valor is None:
            erros.append(ErroDeCampo("/condicao/valor", "obrigatório para limite e janela"))
    if condicao.tipo in (TipoCondicao.JANELA, TipoCondicao.AUSENCIA) and condicao.duracao_s is None:
        erros.append(ErroDeCampo("/condicao/duracao_s", "obrigatório para janela e ausência"))
    for indice, acao in enumerate(regra.acoes):
        caminho = f"/acoes/{indice}"
        if acao.tipo is TipoAcao.WEBHOOK and not acao.url:
            erros.append(ErroDeCampo(f"{caminho}/url", "obrigatório para webhook"))
        if acao.tipo is TipoAcao.COMANDO and not acao.comando:
            erros.append(ErroDeCampo(f"{caminho}/comando", "obrigatório para comando"))
        if acao.tipo is TipoAcao.PUBLICAR:
            topico = acao.topico or ""
            if not topico.startswith(f"{inquilino}/") or "+" in topico or "#" in topico:
                erros.append(ErroDeCampo(f"{caminho}/topico", f"use um tópico sem curingas começando por {inquilino}/"))
    if erros:
        raise DadosInvalidos("Regra inconsistente.", erros)


class ServicoDeRegras:
    def __init__(
        self, repositorio: RepositorioDeRegras, relogio: Relogio, ao_mudar: Callable[[str], None] | None = None
    ) -> None:
        self._repositorio = repositorio
        self._relogio = relogio
        self._ao_mudar = ao_mudar

    def criar(self, origem: Origem, regra: Regra) -> Regra:
        inquilino = exigir(origem, Permissao.GERIR_REGRAS)
        validar_regra(regra, inquilino)
        regra = replace(regra, criado_em=self._relogio.agora())
        self._repositorio.inserir_regra(inquilino, regra)
        if self._ao_mudar:
            self._ao_mudar(inquilino)
        return regra

    def listar(self, origem: Origem, pagina: ParametrosDePagina) -> Pagina[Regra]:
        inquilino = exigir(origem, Permissao.LER)
        return self._repositorio.listar_regras(inquilino, pagina, pagina.ordenacao(("id", "nome", "criado_em"), "id"))
