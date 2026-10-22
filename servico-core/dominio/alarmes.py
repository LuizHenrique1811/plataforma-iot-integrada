"""Ciclo de vida dos alarmes: ativo -> reconhecido -> resolvido, com severidade (RF-PRO-05)."""

from __future__ import annotations

from dataclasses import replace

from dominio.erros import Conflito, NaoEncontrado
from dominio.modelos import Origem
from dominio.paginacao import Pagina, ParametrosDePagina
from dominio.permissoes import Permissao, exigir
from dominio.regras import Alarme, EstadoAlarme
from portas.regras import RepositorioDeAlarmes
from portas.relogio import Relogio


class ServicoDeAlarmes:
    def __init__(self, alarmes: RepositorioDeAlarmes, relogio: Relogio) -> None:
        self._alarmes = alarmes
        self._relogio = relogio

    def listar(
        self, origem: Origem, estado: str | None, severidade: str | None, pagina: ParametrosDePagina
    ) -> Pagina[Alarme]:
        inquilino = exigir(origem, Permissao.LER)
        filtros = {campo: valor for campo, valor in (("estado", estado), ("severidade", severidade)) if valor}
        ordenacao = pagina.ordenacao(("ocorrido_em", "severidade", "estado"), "-ocorrido_em")
        return self._alarmes.listar_alarmes(inquilino, filtros, pagina, ordenacao)

    def reconhecer(self, origem: Origem, alarme: str) -> Alarme:
        atual = self._obter(origem, alarme)
        if atual.estado is not EstadoAlarme.ATIVO:
            raise Conflito(f"Só um alarme ativo pode ser reconhecido; este está {atual.estado.value}.")
        atualizado = replace(atual, estado=EstadoAlarme.RECONHECIDO, reconhecido_em=self._relogio.agora())
        self._alarmes.atualizar_alarme(atualizado)
        return atualizado

    def resolver(self, origem: Origem, alarme: str) -> Alarme:
        atual = self._obter(origem, alarme)
        if atual.estado is EstadoAlarme.RESOLVIDO:
            raise Conflito("O alarme já está resolvido.")
        atualizado = replace(atual, estado=EstadoAlarme.RESOLVIDO, resolvido_em=self._relogio.agora())
        self._alarmes.atualizar_alarme(atualizado)
        return atualizado

    def _obter(self, origem: Origem, alarme: str) -> Alarme:
        inquilino = exigir(origem, Permissao.OPERAR_ALARMES)
        encontrado = self._alarmes.obter_alarme(inquilino, alarme)
        if encontrado is None:
            raise NaoEncontrado("Alarme não encontrado no inquilino.")
        return encontrado
