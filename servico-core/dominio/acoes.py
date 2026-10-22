"""Ações do motor de regras no padrão Strategy: uma classe por tipo de ação (RF-PRO-03, seção 7.2).

Uma ação nova é uma classe nova registrada no motor, sem alterar o motor.
"""

from __future__ import annotations

import logging
import uuid
from typing import Protocol

from dominio.regras import Acao, Alarme, Disparo, EstadoAlarme, Severidade, TipoAcao
from portas.acoes import ClienteWebhook, Notificador, Publicador
from portas.regras import RepositorioDeAlarmes
from portas.relogio import Relogio
from portas.repositorios import Catalogo

log = logging.getLogger("servico_core.acoes")


class ExecutorDeAcao(Protocol):
    def executar(self, disparo: Disparo, acao: Acao) -> None: ...


class GerarAlarme:
    def __init__(self, alarmes: RepositorioDeAlarmes, origem: str) -> None:
        self._alarmes = alarmes
        self._origem = origem

    def executar(self, disparo: Disparo, acao: Acao) -> None:
        alarme = Alarme(
            id=str(uuid.uuid4()),
            inquilino=disparo.inquilino,
            regra=disparo.regra.id,
            dispositivo=disparo.dispositivo,
            severidade=acao.severidade or Severidade.AVISO,
            estado=EstadoAlarme.ATIVO,
            ocorrido_em=disparo.ocorrido_em,
            mensagem=acao.mensagem or disparo.texto(),
            origem=self._origem,
        )
        # Um alarme aberto por regra e dispositivo: o repositório recusa o repetido.
        self._alarmes.inserir_alarme(alarme)


class Notificar:
    def __init__(self, notificador: Notificador) -> None:
        self._notificador = notificador

    def executar(self, disparo: Disparo, acao: Acao) -> None:
        self._notificador.notificar(
            disparo.inquilino, acao.canal or "log", acao.mensagem or disparo.texto(), disparo.como_json()
        )


class EnviarComando:
    """Publica um comando canônico no tópico do dispositivo de destino (asyncapi.yaml, canal comando)."""

    def __init__(self, catalogo: Catalogo, publicador: Publicador, relogio: Relogio) -> None:
        self._catalogo = catalogo
        self._publicador = publicador
        self._relogio = relogio

    def executar(self, disparo: Disparo, acao: Acao) -> None:
        destino = self._catalogo.obter_dispositivo(disparo.inquilino, acao.dispositivo or disparo.dispositivo)
        if destino is None:
            log.warning("comando sem destino cadastrado: %s", acao.dispositivo, extra={"inquilino": disparo.inquilino})
            return
        carga = {
            "versao": "1.0",
            "id_mensagem": str(uuid.uuid4()),
            "dispositivo": destino.id,
            "tipo": "comando",
            "timestamp": self._relogio.agora().isoformat().replace("+00:00", "Z"),
            "comando": acao.comando,
        }
        self._publicador.publicar(f"{disparo.inquilino}/{destino.site}/{destino.dominio}/{destino.id}/comando", carga)


class ChamarWebhook:
    def __init__(self, cliente: ClienteWebhook) -> None:
        self._cliente = cliente

    def executar(self, disparo: Disparo, acao: Acao) -> None:
        self._cliente.enviar(acao.url, disparo.como_json())


class PublicarEmTopico:
    def __init__(self, publicador: Publicador) -> None:
        self._publicador = publicador

    def executar(self, disparo: Disparo, acao: Acao) -> None:
        self._publicador.publicar(acao.topico, disparo.como_json())


def executores_padrao(
    *,
    alarmes: RepositorioDeAlarmes,
    catalogo: Catalogo,
    notificador: Notificador,
    publicador: Publicador,
    webhook: ClienteWebhook,
    relogio: Relogio,
    origem: str,
) -> dict[TipoAcao, ExecutorDeAcao]:
    return {
        TipoAcao.ALARME: GerarAlarme(alarmes, origem),
        TipoAcao.NOTIFICAR: Notificar(notificador),
        TipoAcao.COMANDO: EnviarComando(catalogo, publicador, relogio),
        TipoAcao.WEBHOOK: ChamarWebhook(webhook),
        TipoAcao.PUBLICAR: PublicarEmTopico(publicador),
    }
