"""Adaptadores em memória: testes do domínio e execução sem banco em desenvolvimento."""

from __future__ import annotations

import hmac
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from adaptadores.credenciais import hash_segredo
from dominio.catalogo import Area, ChaveDeApi, Dominio, Inquilino, Site
from dominio.consultas import Contato, MedicaoConsultada, RejeitadaConsultada
from dominio.erros import JaExiste
from dominio.modelos import (
    DispositivoCadastrado,
    Medida,
    MensagemAceita,
    MensagemRejeitada,
    Origem,
    Perfil,
    TipoOrigem,
)
from dominio.paginacao import Ordenacao, Pagina, ParametrosDePagina


def _paginar(itens: list[Any], pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Any]:
    def chave(item: Any) -> tuple[bool, Any]:
        valor = getattr(item, ordenacao.campo)
        return (valor is None, "" if valor is None else valor)

    ordenados = sorted(itens, key=chave, reverse=ordenacao.decrescente)
    fatia = ordenados[pagina.deslocamento : pagina.deslocamento + pagina.tamanho]
    return Pagina(tuple(fatia), pagina.pagina, pagina.tamanho, len(itens))


def _inserir(tabela: dict, chave: Any, valor: Any, descricao: str) -> None:
    if chave in tabela:
        raise JaExiste(f"Já existe {descricao} com esse identificador.")
    tabela[chave] = valor


@dataclass
class CatalogoEmMemoria:
    inquilinos: dict[str, Inquilino] = field(default_factory=dict)
    chaves: dict[str, ChaveDeApi] = field(default_factory=dict)  # hash -> chave
    dominios: dict[tuple[str, str], Dominio] = field(default_factory=dict)
    perfis: dict[tuple[str, str], Perfil] = field(default_factory=dict)
    sites: dict[tuple[str, str], Site] = field(default_factory=dict)
    areas: dict[tuple[str, str, str], Area] = field(default_factory=dict)
    dispositivos: dict[tuple[str, str], DispositivoCadastrado] = field(default_factory=dict)
    tokens: dict[str, tuple[str, str]] = field(default_factory=dict)  # hash -> (inquilino, dispositivo)

    # Atalhos para os testes montarem o catálogo.
    def adicionar_perfil(self, inquilino: str, perfil: Perfil) -> None:
        self.perfis[(inquilino, perfil.id)] = perfil

    def adicionar_dispositivo(self, dispositivo: DispositivoCadastrado) -> None:
        self.dispositivos[(dispositivo.inquilino, dispositivo.id)] = dispositivo

    # Catalogo
    def obter_dispositivo(self, inquilino: str, dispositivo: str) -> DispositivoCadastrado | None:
        return self.dispositivos.get((inquilino, dispositivo))

    def obter_perfil(self, inquilino: str, perfil: str) -> Perfil | None:
        return self.perfis.get((inquilino, perfil))

    # RepositorioDeCatalogo
    def existe_inquilino(self, inquilino: str) -> bool:
        return inquilino in self.inquilinos

    def inserir_inquilino(self, inquilino: Inquilino) -> None:
        _inserir(self.inquilinos, inquilino.id, inquilino, "inquilino")

    def listar_inquilinos(self, pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Inquilino]:
        return _paginar(list(self.inquilinos.values()), pagina, ordenacao)

    def inserir_chave(self, chave: ChaveDeApi, hash_segredo: str) -> None:
        self.chaves[hash_segredo] = chave

    def existe_dominio(self, inquilino: str, dominio: str) -> bool:
        return (inquilino, dominio) in self.dominios

    def inserir_dominio(self, inquilino: str, dominio: Dominio) -> None:
        _inserir(self.dominios, (inquilino, dominio.id), dominio, "domínio")

    def listar_dominios(self, inquilino: str, pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Dominio]:
        return _paginar(_do_inquilino(self.dominios, inquilino), pagina, ordenacao)

    def inserir_perfil(self, inquilino: str, perfil: Perfil, criado_em: datetime) -> None:
        _inserir(self.perfis, (inquilino, perfil.id), perfil, "perfil")

    def listar_perfis(self, inquilino: str, pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Perfil]:
        return _paginar(_do_inquilino(self.perfis, inquilino), pagina, ordenacao)

    def existe_site(self, inquilino: str, site: str) -> bool:
        return (inquilino, site) in self.sites

    def inserir_site(self, inquilino: str, site: Site) -> None:
        _inserir(self.sites, (inquilino, site.id), site, "local")

    def listar_sites(self, inquilino: str, pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Site]:
        return _paginar(_do_inquilino(self.sites, inquilino), pagina, ordenacao)

    def existe_area(self, inquilino: str, site: str, area: str) -> bool:
        return (inquilino, site, area) in self.areas

    def inserir_area(self, inquilino: str, area: Area) -> None:
        _inserir(self.areas, (inquilino, area.site, area.id), area, "área")

    def listar_areas(self, inquilino: str, site: str, pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Area]:
        areas = [area for (dono, local, _), area in self.areas.items() if (dono, local) == (inquilino, site)]
        return _paginar(areas, pagina, ordenacao)

    def inserir_dispositivo(self, dispositivo: DispositivoCadastrado, hash_token: str) -> None:
        _inserir(self.dispositivos, (dispositivo.inquilino, dispositivo.id), dispositivo, "dispositivo")
        self.tokens[hash_token] = (dispositivo.inquilino, dispositivo.id)

    def listar_dispositivos(
        self, inquilino: str, filtros: dict[str, str], pagina: ParametrosDePagina, ordenacao: Ordenacao
    ) -> Pagina[DispositivoCadastrado]:
        encontrados = [
            dispositivo
            for dispositivo in _do_inquilino(self.dispositivos, inquilino)
            if all(getattr(dispositivo, campo) == valor for campo, valor in filtros.items())
        ]
        return _paginar(encontrados, pagina, ordenacao)

    def revogar_credencial(self, inquilino: str, dispositivo: str, quando: datetime) -> bool:
        atual = self.dispositivos.get((inquilino, dispositivo))
        if atual is None:
            return False
        self.dispositivos[(inquilino, dispositivo)] = replace(atual, revogado_em=quando)
        self.tokens = {hash_: dono for hash_, dono in self.tokens.items() if dono != (inquilino, dispositivo)}
        return True


def _do_inquilino(tabela: dict[tuple, Any], inquilino: str) -> list[Any]:
    return [valor for chave, valor in tabela.items() if chave[0] == inquilino]


@dataclass
class RepositorioEmMemoria:
    ids: set[str] = field(default_factory=set)
    mensagens: list[MensagemAceita] = field(default_factory=list)
    ultimo_estado: dict[tuple[str, str, str], tuple[Medida, MensagemAceita]] = field(default_factory=dict)
    ultimo_contato: dict[tuple[str, str], Contato] = field(default_factory=dict)
    contato_da_borda: dict[tuple[str, str], datetime] = field(default_factory=dict)
    _trava: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def ja_recebida(self, id_mensagem: str) -> bool:
        return id_mensagem in self.ids

    def persistir(self, mensagem: MensagemAceita) -> bool:
        with self._trava:
            if mensagem.id_mensagem in self.ids:
                return False
            self.ids.add(mensagem.id_mensagem)
            self.mensagens.append(mensagem)
            for medida in mensagem.medidas:
                chave = (mensagem.inquilino, mensagem.dispositivo, medida.grandeza)
                atual = self.ultimo_estado.get(chave)
                if atual is None or atual[1].timestamp < mensagem.timestamp:
                    self.ultimo_estado[chave] = (medida, mensagem)
            dono = (mensagem.inquilino, mensagem.dispositivo)
            contato = self.ultimo_contato.get(dono)
            if contato is None or contato.medido_em < mensagem.timestamp:
                self.ultimo_contato[dono] = Contato(mensagem.timestamp, mensagem.via)
            if mensagem.via:
                borda = (mensagem.inquilino, mensagem.via)
                self.contato_da_borda[borda] = max(
                    self.contato_da_borda.get(borda, mensagem.recebido_em), mensagem.recebido_em
                )
            return True


@dataclass
class FilaDeRejeitadasEmMemoria:
    itens: list[MensagemRejeitada] = field(default_factory=list)

    def registrar(self, rejeitada: MensagemRejeitada) -> None:
        self.itens.append(rejeitada)


@dataclass
class ConsultasEmMemoria:
    repositorio: RepositorioEmMemoria
    rejeitadas_: FilaDeRejeitadasEmMemoria

    def medicoes(
        self,
        inquilino: str,
        dispositivo: str,
        grandeza: str | None,
        inicio: datetime | None,
        fim: datetime | None,
        pagina: ParametrosDePagina,
        ordenacao: Ordenacao,
    ) -> Pagina[MedicaoConsultada]:
        encontradas = [
            MedicaoConsultada(
                mensagem.timestamp,
                medida.grandeza,
                medida.valor,
                medida.unidade,
                medida.suspeita,
                mensagem.id_mensagem,
                mensagem.via,
            )
            for mensagem in self.repositorio.mensagens
            if (mensagem.inquilino, mensagem.dispositivo) == (inquilino, dispositivo)
            and (inicio is None or mensagem.timestamp >= inicio)
            and (fim is None or mensagem.timestamp < fim)
            for medida in mensagem.medidas
            if grandeza is None or medida.grandeza == grandeza
        ]
        return _paginar(encontradas, pagina, ordenacao)

    def ultimo_estado(self, inquilino: str, dispositivo: str) -> list[MedicaoConsultada]:
        return [
            MedicaoConsultada(
                mensagem.timestamp,
                medida.grandeza,
                medida.valor,
                medida.unidade,
                medida.suspeita,
                mensagem.id_mensagem,
                mensagem.via,
            )
            for (dono, aparelho, _), (medida, mensagem) in sorted(self.repositorio.ultimo_estado.items())
            if (dono, aparelho) == (inquilino, dispositivo)
        ]

    def ultimo_contato(self, inquilino: str, dispositivo: str) -> Contato | None:
        return self.repositorio.ultimo_contato.get((inquilino, dispositivo))

    def contato_da_borda(self, inquilino: str, via: str) -> datetime | None:
        return self.repositorio.contato_da_borda.get((inquilino, via))

    def rejeitadas(
        self, inquilino: str, pagina: ParametrosDePagina, ordenacao: Ordenacao
    ) -> Pagina[RejeitadaConsultada]:
        itens = [
            RejeitadaConsultada(
                indice + 1,
                item.recebido_em,
                item.etapa.value,
                item.motivo.value,
                tuple({"caminho": erro.caminho, "mensagem": erro.mensagem} for erro in item.erros),
                item.origem,
                item.carga,
            )
            for indice, item in enumerate(self.rejeitadas_.itens)
            if item.inquilino == inquilino
        ]
        return _paginar(itens, pagina, ordenacao)


@dataclass
class AutenticadorEmMemoria:
    """Confere pelo hash, como o adaptador do banco. Também enxerga as credenciais emitidas pelo catálogo."""

    tokens: dict[str, tuple[str, str]] = field(default_factory=dict)  # hash -> (inquilino, dispositivo)
    chaves: dict[str, tuple[str | None, str]] = field(default_factory=dict)  # hash -> (inquilino, papel)
    chave_admin: str | None = None
    catalogo: CatalogoEmMemoria | None = None

    def registrar_token(self, token: str, inquilino: str, dispositivo: str) -> None:
        self.tokens[hash_segredo(token)] = (inquilino, dispositivo)

    def registrar_chave(self, chave: str, inquilino: str | None, papel: str) -> None:
        self.chaves[hash_segredo(chave)] = (inquilino, papel)

    def por_token_dispositivo(self, token: str) -> Origem | None:
        hash_ = hash_segredo(token)
        encontrado = self.tokens.get(hash_) or (self.catalogo.tokens.get(hash_) if self.catalogo else None)
        if encontrado is None:
            return None
        return Origem(TipoOrigem.DISPOSITIVO, inquilino=encontrado[0], dispositivo=encontrado[1])

    def por_chave(self, chave: str) -> Origem | None:
        if self.chave_admin and hmac.compare_digest(chave, self.chave_admin):
            return Origem(TipoOrigem.CHAVE, inquilino=None, papel="administrador")
        hash_ = hash_segredo(chave)
        encontrado = self.chaves.get(hash_)
        if encontrado is None and self.catalogo and hash_ in self.catalogo.chaves:
            emitida = self.catalogo.chaves[hash_]
            encontrado = (emitida.inquilino, emitida.papel)
        if encontrado is None:
            return None
        return Origem(TipoOrigem.CHAVE, inquilino=encontrado[0], papel=encontrado[1])
