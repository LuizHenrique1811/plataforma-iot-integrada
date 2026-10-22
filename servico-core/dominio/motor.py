"""Motor de regras: avalia cada mensagem aceita logo depois de gravada (RF-PRO-02, até 3 s).

- Limite: dispara quando a comparação passa a valer.
- Janela: dispara quando a comparação vale continuamente por `duracao_s`, contado pelo horário da medição.
- Ausência: verificada periodicamente; dispara quando a grandeza fica `duracao_s` sem leitura.

Cada regra dispara uma vez por transição e é rearmada quando a condição deixa de valer; nesse momento
os alarmes abertos da regra para o dispositivo são resolvidos. Só dado atual é avaliado: um dado atrasado
entra no histórico mas não dispara ação (RF-ING-04, ADR-0013).
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

from dominio.acoes import ExecutorDeAcao
from dominio.modelos import Medida, MensagemAceita
from dominio.regras import (
    Alarme,
    Disparo,
    EstadoAlarme,
    EstadoDaRegra,
    Regra,
    Severidade,
    TipoAcao,
    TipoCondicao,
)
from portas.regras import RepositorioDeAlarmes, RepositorioDeRegras

log = logging.getLogger("servico_core.regras")

EVENTO_DE_ALARME = "alarme"
EVENTO_DE_ALARME_RESOLVIDO = "alarme_resolvido"
ORIGEM_IMPORTADA = "borda"

# Aviso de que alarmes de uma regra foram resolvidos neste nó: (inquilino, regra, dispositivo, quando).
AoResolver = Callable[[str, str, str, datetime], None]


class MotorDeRegras:
    """Cada nó abre e resolve só os alarmes que ele mesmo gera (origem igual ao âmbito do motor).

    Os alarmes que chegam da borda como evento são abertos e resolvidos pelos eventos "alarme" e
    "alarme_resolvido", com o horário em que aconteceram lá (RF-PRO-05).
    """

    def __init__(
        self,
        regras: RepositorioDeRegras,
        alarmes: RepositorioDeAlarmes,
        executores: dict[TipoAcao, ExecutorDeAcao],
        *,
        ambito: str,
        validade_do_cache_s: float = 10.0,
        ao_resolver: AoResolver | None = None,
    ) -> None:
        self._regras = regras
        self._alarmes = alarmes
        self._executores = executores
        self._ambito = ambito
        self._validade_do_cache_s = validade_do_cache_s
        self._ao_resolver = ao_resolver
        self._cache: dict[str, tuple[float, list[Regra]]] = {}
        self._trava = threading.Lock()

    # Observador do pipeline de ingestão ---------------------------------------------------

    def mensagem_aceita(self, mensagem: MensagemAceita) -> list[Disparo]:
        nome_do_evento = (mensagem.evento or {}).get("nome") if mensagem.tipo == "evento" else None
        if nome_do_evento == EVENTO_DE_ALARME:
            self._registrar_alarme_da_borda(mensagem)
            return []
        if nome_do_evento == EVENTO_DE_ALARME_RESOLVIDO:
            regra = str(((mensagem.evento or {}).get("detalhes") or {}).get("regra") or "borda")
            self._alarmes.resolver_abertos(
                mensagem.inquilino, regra, mensagem.dispositivo, mensagem.timestamp, ORIGEM_IMPORTADA
            )
            return []
        if mensagem.tipo != "telemetria" or not mensagem.atual:
            return []
        disparos = []
        for regra in self._regras_ativas(mensagem.inquilino):
            condicao = regra.condicao
            medida = next((m for m in mensagem.medidas if m.grandeza == condicao.grandeza), None)
            if medida is None or not condicao.casa_com(mensagem):
                continue
            if condicao.tipo is TipoCondicao.AUSENCIA:
                self._rearmar(regra, mensagem.inquilino, mensagem.dispositivo, mensagem.timestamp)
                continue
            disparo = self._avaliar(regra, mensagem, medida)
            if disparo is not None:
                disparos.append(disparo)
                self.executar(disparo)
        return disparos

    def verificar_ausencias(self, agora: datetime) -> list[Disparo]:
        disparos = []
        for inquilino, regra in self._regras.regras_de_ausencia(self._ambito):
            limite = timedelta(seconds=regra.condicao.duracao_s)
            filtros = regra.condicao.filtros()
            for dispositivo, ultima in self._regras.ultimas_leituras(inquilino, filtros, regra.condicao.grandeza):
                if ultima is not None and agora - ultima < limite:
                    continue
                estado = self._regras.obter_estado(inquilino, regra.id, dispositivo) or EstadoDaRegra()
                if estado.disparada:
                    continue
                self._regras.salvar_estado(inquilino, regra.id, dispositivo, EstadoDaRegra(True, ultima, True))
                disparo = Disparo(regra, inquilino, dispositivo, regra.condicao.grandeza, None, agora)
                disparos.append(disparo)
                self.executar(disparo)
        return disparos

    def executar(self, disparo: Disparo) -> None:
        log.info(disparo.texto(), extra={"inquilino": disparo.inquilino, "dispositivo": disparo.dispositivo})
        for acao in disparo.regra.acoes:
            try:
                self._executores[acao.tipo].executar(disparo, acao)
            except Exception:
                # Uma ação com falha (webhook fora do ar, broker indisponível) não impede as outras.
                log.exception("falha na ação %s da regra %s", acao.tipo.value, disparo.regra.id)

    def esquecer_cache(self, inquilino: str) -> None:
        with self._trava:
            self._cache.pop(inquilino, None)

    # Apoio ----------------------------------------------------------------------------------

    def _regras_ativas(self, inquilino: str) -> list[Regra]:
        agora = time.monotonic()
        with self._trava:
            guardado = self._cache.get(inquilino)
            if guardado and agora - guardado[0] < self._validade_do_cache_s:
                return guardado[1]
        regras = self._regras.regras_ativas(inquilino, self._ambito)
        with self._trava:
            self._cache[inquilino] = (agora, regras)
        return regras

    def _avaliar(self, regra: Regra, mensagem: MensagemAceita, medida: Medida) -> Disparo | None:
        inquilino, dispositivo = mensagem.inquilino, mensagem.dispositivo
        if not regra.condicao.atende(medida.valor):
            self._rearmar(regra, inquilino, dispositivo, mensagem.timestamp)
            return None
        estado = self._regras.obter_estado(inquilino, regra.id, dispositivo) or EstadoDaRegra()
        desde = estado.desde if estado.condicao_ativa and estado.desde else mensagem.timestamp
        if regra.condicao.tipo is TipoCondicao.JANELA:
            cumprida = mensagem.timestamp - desde >= timedelta(seconds=regra.condicao.duracao_s)
        else:
            cumprida = True
        novo = EstadoDaRegra(True, desde, estado.disparada or cumprida)
        if novo != estado:
            self._regras.salvar_estado(inquilino, regra.id, dispositivo, novo)
        if not cumprida or estado.disparada:
            return None
        return Disparo(
            regra,
            inquilino,
            dispositivo,
            medida.grandeza,
            medida.valor,
            mensagem.timestamp,
            site=mensagem.site,
            dominio=mensagem.dominio,
            area=mensagem.area,
        )

    def _rearmar(self, regra: Regra, inquilino: str, dispositivo: str, quando: datetime) -> None:
        estado = self._regras.obter_estado(inquilino, regra.id, dispositivo)
        if estado is None or estado == EstadoDaRegra():
            return
        if estado.disparada:
            resolvidos = self._alarmes.resolver_abertos(inquilino, regra.id, dispositivo, quando, self._ambito)
            if resolvidos:
                log.info("alarme resolvido: condição da regra %s deixou de valer", regra.id)
                if self._ao_resolver is not None:
                    self._ao_resolver(inquilino, regra.id, dispositivo, quando)
        self._regras.salvar_estado(inquilino, regra.id, dispositivo, EstadoDaRegra())

    def _registrar_alarme_da_borda(self, mensagem: MensagemAceita) -> None:
        """Alarme gerado por regra local da borda, com o horário em que ocorreu, mesmo atrasado (RF-PRO-05)."""
        evento = mensagem.evento or {}
        detalhes = evento.get("detalhes") or {}
        self._alarmes.inserir_alarme(
            Alarme(
                id=str(uuid.uuid4()),
                inquilino=mensagem.inquilino,
                regra=str(detalhes.get("regra") or "borda"),
                dispositivo=mensagem.dispositivo,
                severidade=Severidade(evento.get("severidade") or "aviso"),
                estado=EstadoAlarme.ATIVO,
                ocorrido_em=mensagem.timestamp,
                mensagem=detalhes.get("mensagem"),
                origem=ORIGEM_IMPORTADA,
                id_mensagem=mensagem.id_mensagem,
            )
        )
