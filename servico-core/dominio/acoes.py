"""Ações do motor de regras no padrão Strategy: uma classe por tipo de ação (RF-PRO-03, seção 7.2).

Uma ação nova é uma classe nova registrada no motor, sem alterar o motor.
"""

from __future__ import annotations

import logging
import uuid
from typing import Protocol

from dominio.regras import Acao, Alarme, Disparo, EstadoAlarme, Severidade, TipoAcao
from dominio.sincronizacao import PRIORIDADE_EVENTO
from portas.acoes import ClienteWebhook, Notificador, Publicador
from portas.regras import RepositorioDeAlarmes
from portas.relogio import Relogio
from portas.repositorios import Catalogo
from portas.sincronizacao import FilaDeSincronizacao

log = logging.getLogger("servico_core.acoes")


class ExecutorDeAcao(Protocol):
    def executar(self, disparo: Disparo, acao: Acao) -> object: ...


class GerarAlarme:
    def __init__(self, alarmes: RepositorioDeAlarmes, origem: str) -> None:
        self._alarmes = alarmes
        self._origem = origem

    def executar(self, disparo: Disparo, acao: Acao) -> bool:
        """Devolve True se abriu um alarme novo."""
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
        return self._alarmes.inserir_alarme(alarme)


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

    def executar(self, disparo: Disparo, acao: Acao) -> str | None:
        """Devolve o dispositivo de destino, ou None se ele não estiver cadastrado."""
        destino = self._catalogo.obter_dispositivo(disparo.inquilino, acao.dispositivo or disparo.dispositivo)
        if destino is None:
            log.warning("comando sem destino cadastrado: %s", acao.dispositivo, extra={"inquilino": disparo.inquilino})
            return None
        carga = {
            "versao": "1.0",
            "id_mensagem": str(uuid.uuid4()),
            "dispositivo": destino.id,
            "tipo": "comando",
            "timestamp": self._relogio.agora().isoformat().replace("+00:00", "Z"),
            "comando": acao.comando,
        }
        self._publicador.publicar(f"{disparo.inquilino}/{destino.site}/{destino.dominio}/{destino.id}/comando", carga)
        return destino.id


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


# Nó de borda: as ações também viram eventos para a central (RF-EDG-03, RF-PRO-05) --------------


def evento_para_a_central(
    disparo: Disparo, dispositivo: str, nome: str, borda: str, severidade: Severidade | None, detalhes: dict
) -> dict:
    """Evento canônico (tipo evento) com o horário em que a regra disparou."""
    evento: dict = {"nome": nome, "detalhes": detalhes}
    if severidade is not None:
        evento["severidade"] = severidade.value
    return {
        "versao": "1.0",
        "id_mensagem": str(uuid.uuid4()),
        "dispositivo": dispositivo,
        "tipo": "evento",
        "timestamp": disparo.ocorrido_em.isoformat().replace("+00:00", "Z"),
        "via": borda,
        "evento": evento,
    }


class GerarAlarmeNaBorda(GerarAlarme):
    """Abre o alarme local e enfileira o evento "alarme", que a central registra com o horário original."""

    def __init__(self, alarmes: RepositorioDeAlarmes, fila: FilaDeSincronizacao, borda: str) -> None:
        super().__init__(alarmes, origem="borda")
        self._fila = fila
        self._borda = borda

    def executar(self, disparo: Disparo, acao: Acao) -> bool:
        if not super().executar(disparo, acao):
            return False
        severidade = acao.severidade or Severidade.AVISO
        detalhes = {"regra": disparo.regra.id, "mensagem": acao.mensagem or disparo.texto(), "valor": disparo.valor}
        carga = evento_para_a_central(disparo, disparo.dispositivo, "alarme", self._borda, severidade, detalhes)
        self._fila.enfileirar(carga, PRIORIDADE_EVENTO)
        return True


class EnviarComandoNaBorda(EnviarComando):
    """Comanda o atuador local, mesmo sem link, e enfileira o evento "comando_enviado" (UC-01)."""

    def __init__(
        self, catalogo: Catalogo, publicador: Publicador, relogio: Relogio, fila: FilaDeSincronizacao, borda: str
    ) -> None:
        super().__init__(catalogo, publicador, relogio)
        self._fila = fila
        self._borda = borda

    def executar(self, disparo: Disparo, acao: Acao) -> str | None:
        destino = super().executar(disparo, acao)
        if destino is not None:
            detalhes = {"regra": disparo.regra.id, "comando": acao.comando, "origem": disparo.dispositivo}
            carga = evento_para_a_central(disparo, destino, "comando_enviado", self._borda, None, detalhes)
            self._fila.enfileirar(carga, PRIORIDADE_EVENTO)
        return destino


def executores_da_borda(
    *,
    alarmes: RepositorioDeAlarmes,
    catalogo: Catalogo,
    notificador: Notificador,
    publicador: Publicador,
    webhook: ClienteWebhook,
    relogio: Relogio,
    fila: FilaDeSincronizacao,
    borda: str,
) -> dict[TipoAcao, ExecutorDeAcao]:
    executores = executores_padrao(
        alarmes=alarmes,
        catalogo=catalogo,
        notificador=notificador,
        publicador=publicador,
        webhook=webhook,
        relogio=relogio,
        origem="borda",
    )
    executores[TipoAcao.ALARME] = GerarAlarmeNaBorda(alarmes, fila, borda)
    executores[TipoAcao.COMANDO] = EnviarComandoNaBorda(catalogo, publicador, relogio, fila, borda)
    return executores


def aviso_de_resolucao(fila: FilaDeSincronizacao, borda: str):
    """Quando um alarme local se resolve na borda, a central fica sabendo pelo evento "alarme_resolvido"."""

    def avisar(inquilino: str, regra: str, dispositivo: str, quando) -> None:
        carga = {
            "versao": "1.0",
            "id_mensagem": str(uuid.uuid4()),
            "dispositivo": dispositivo,
            "tipo": "evento",
            "timestamp": quando.isoformat().replace("+00:00", "Z"),
            "via": borda,
            "evento": {"nome": "alarme_resolvido", "detalhes": {"regra": regra}},
        }
        fila.enfileirar(carga, PRIORIDADE_EVENTO)

    return avisar
