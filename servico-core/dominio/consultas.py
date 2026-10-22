"""Consultas de histórico, último estado e DLQ (RF-DAD-01, RF-DAD-02, RF-DIS-06)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from dominio.erros import DadosInvalidos, NaoEncontrado
from dominio.modelos import DispositivoCadastrado, ErroDeCampo, Origem
from dominio.paginacao import Pagina, ParametrosDePagina
from dominio.permissoes import Permissao, exigir
from portas.relogio import Relogio
from portas.repositorios import Catalogo, RepositorioDeConsultas

# Sem dados por mais que este múltiplo do intervalo esperado do perfil, o dispositivo deixa de estar online.
FATOR_TOLERANCIA = 2
# Intervalo usado se o perfil do dispositivo tiver sido apagado.
INTERVALO_PADRAO_S = 3600


class SituacaoDispositivo(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    DESCONHECIDO = "desconhecido"


@dataclass(frozen=True)
class MedicaoConsultada:
    timestamp: datetime
    grandeza: str
    valor: float | bool | str | None
    unidade: str | None
    suspeita: bool
    id_mensagem: str
    via: str | None = None


@dataclass(frozen=True)
class Contato:
    """Última medição recebida de um dispositivo e o nó de borda pelo qual passou."""

    medido_em: datetime
    via: str | None = None


@dataclass(frozen=True)
class EstadoDoDispositivo:
    dispositivo: str
    situacao: SituacaoDispositivo
    ultimo_contato: datetime | None
    grandezas: tuple[MedicaoConsultada, ...]


@dataclass(frozen=True)
class RejeitadaConsultada:
    id: int
    recebido_em: datetime
    etapa: str
    motivo: str
    erros: tuple[dict[str, str], ...]
    origem: str | None
    carga: Any


def calcular_situacao(
    agora: datetime, contato: Contato | None, intervalo_s: int, contato_da_borda: datetime | None
) -> SituacaoDispositivo:
    """Online/offline pelo intervalo esperado do perfil, com o estado "desconhecido" do ADR-0010.

    Um dispositivo atrás de uma borda que está sem sincronizar não é marcado offline: a central não
    sabe se ele parou ou se só o link caiu.
    """
    if contato is None:
        return SituacaoDispositivo.OFFLINE
    limite = timedelta(seconds=intervalo_s * FATOR_TOLERANCIA)
    if agora - contato.medido_em <= limite:
        return SituacaoDispositivo.ONLINE
    if contato.via is not None and (contato_da_borda is None or agora - contato_da_borda > limite):
        return SituacaoDispositivo.DESCONHECIDO
    return SituacaoDispositivo.OFFLINE


class ServicoDeConsultas:
    def __init__(self, consultas: RepositorioDeConsultas, catalogo: Catalogo, relogio: Relogio) -> None:
        self._consultas = consultas
        self._catalogo = catalogo
        self._relogio = relogio

    def telemetria(
        self,
        origem: Origem,
        dispositivo: str,
        grandeza: str | None,
        inicio: datetime | None,
        fim: datetime | None,
        pagina: ParametrosDePagina,
    ) -> Pagina[MedicaoConsultada]:
        """Histórico pelo horário da medição, com dados atrasados já no lugar certo (RF-DAD-01)."""
        inquilino = exigir(origem, Permissao.LER)
        self._dispositivo(inquilino, dispositivo)
        if inicio is not None and fim is not None and inicio >= fim:
            raise DadosInvalidos("Intervalo vazio.", [ErroDeCampo("inicio", "o início deve ser anterior ao fim")])
        ordenacao = pagina.ordenacao(("timestamp",), "timestamp")
        return self._consultas.medicoes(inquilino, dispositivo, grandeza, inicio, fim, pagina, ordenacao)

    def estado(self, origem: Origem, dispositivo: str) -> EstadoDoDispositivo:
        """Último valor de cada grandeza, sem consultar o histórico (RF-DAD-02), e a situação (RF-DIS-06)."""
        inquilino = exigir(origem, Permissao.LER)
        cadastrado = self._dispositivo(inquilino, dispositivo)
        perfil = self._catalogo.obter_perfil(inquilino, cadastrado.perfil)
        contato = self._consultas.ultimo_contato(inquilino, dispositivo)
        contato_da_borda = self._consultas.contato_da_borda(inquilino, contato.via) if contato and contato.via else None
        situacao = calcular_situacao(
            self._relogio.agora(),
            contato,
            perfil.intervalo_envio_s if perfil else INTERVALO_PADRAO_S,
            contato_da_borda,
        )
        return EstadoDoDispositivo(
            dispositivo,
            situacao,
            contato.medido_em if contato else None,
            tuple(self._consultas.ultimo_estado(inquilino, dispositivo)),
        )

    def rejeitadas(self, origem: Origem, pagina: ParametrosDePagina) -> Pagina[RejeitadaConsultada]:
        inquilino = exigir(origem, Permissao.LER)
        return self._consultas.rejeitadas(inquilino, pagina, pagina.ordenacao(("recebido_em",), "-recebido_em"))

    def _dispositivo(self, inquilino: str, dispositivo: str) -> DispositivoCadastrado:
        cadastrado = self._catalogo.obter_dispositivo(inquilino, dispositivo)
        if cadastrado is None:
            raise NaoEncontrado("Dispositivo não encontrado no inquilino.")
        return cadastrado
