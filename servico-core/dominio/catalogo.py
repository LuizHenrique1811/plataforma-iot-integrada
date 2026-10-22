"""Catálogo e cadastro: inquilinos, chaves, domínios, perfis, locais, áreas e dispositivos.

Tudo é dado (Type Object, ADR-0003): criar um domínio novo é só uma chamada (RF-CEN-01, RNF-08, UC-06).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from dominio.erros import AcessoNegado, DadosInvalidos, NaoEncontrado
from dominio.modelos import DispositivoCadastrado, ErroDeCampo, Origem, Perfil
from dominio.paginacao import Pagina, ParametrosDePagina
from dominio.permissoes import PERMISSOES, Permissao, exigir
from portas.credenciais import GeradorDeCredenciais
from portas.relogio import Relogio
from portas.repositorios import RepositorioDeCatalogo

CAMPOS_ORDENAVEIS = ("id", "nome", "criado_em")
CAMPOS_ORDENAVEIS_DISPOSITIVO = ("id", "criado_em", "perfil", "dominio", "site")
FILTROS_DISPOSITIVO = ("dominio", "perfil", "site", "area")


@dataclass(frozen=True)
class Inquilino:
    id: str
    nome: str
    criado_em: datetime | None = None


@dataclass(frozen=True)
class ChaveDeApi:
    id: str
    inquilino: str | None
    papel: str
    descricao: str | None
    criado_em: datetime


@dataclass(frozen=True)
class Dominio:
    id: str
    nome: str
    descricao: str | None = None
    criado_em: datetime | None = None


@dataclass(frozen=True)
class Site:
    id: str
    nome: str
    geo: dict[str, Any] | None = None
    criado_em: datetime | None = None


@dataclass(frozen=True)
class Area:
    id: str
    site: str
    nome: str
    geo: dict[str, Any] | None = None
    criado_em: datetime | None = None


class ServicoDeCatalogo:
    def __init__(self, repositorio: RepositorioDeCatalogo, credenciais: GeradorDeCredenciais, relogio: Relogio) -> None:
        self._repositorio = repositorio
        self._credenciais = credenciais
        self._relogio = relogio

    # Inquilinos e chaves --------------------------------------------------------------------

    def criar_inquilino(self, origem: Origem, inquilino: Inquilino) -> Inquilino:
        exigir(origem, Permissao.GERIR_INQUILINOS, com_inquilino=False)
        inquilino = replace(inquilino, criado_em=self._relogio.agora())
        self._repositorio.inserir_inquilino(inquilino)
        return inquilino

    def listar_inquilinos(self, origem: Origem, pagina: ParametrosDePagina) -> Pagina[Inquilino]:
        exigir(origem, Permissao.GERIR_INQUILINOS, com_inquilino=False)
        return self._repositorio.listar_inquilinos(pagina, pagina.ordenacao(CAMPOS_ORDENAVEIS, "id"))

    def emitir_chave(self, origem: Origem, papel: str, descricao: str | None) -> tuple[ChaveDeApi, str]:
        """Devolve a chave e o segredo, que só aparece aqui; guarda-se apenas o hash."""
        exigir(origem, Permissao.GERIR_CHAVES, com_inquilino=False)
        if papel not in PERMISSOES:
            raise DadosInvalidos("Papel desconhecido.", [ErroDeCampo("/papel", f"papel {papel!r} não existe")])
        if papel == "administrador" and origem.papel != "administrador":
            raise AcessoNegado("só o administrador emite chaves de administrador")
        inquilino = origem.inquilino
        if inquilino is None and papel != "administrador":
            raise DadosInvalidos(
                "Chave de inquilino sem inquilino.",
                [ErroDeCampo("X-Inquilino", "informe o inquilino da chave")],
            )
        if inquilino is not None:
            self._garantir_inquilino(inquilino)
        segredo = self._credenciais.novo_segredo()
        chave = ChaveDeApi(self._credenciais.novo_id(), inquilino, papel, descricao, self._relogio.agora())
        self._repositorio.inserir_chave(chave, self._credenciais.hash(segredo))
        return chave, segredo

    # Domínios, perfis, locais e áreas ------------------------------------------------------

    def criar_dominio(self, origem: Origem, dominio: Dominio) -> Dominio:
        inquilino = self._para_escrita(origem, Permissao.GERIR_CATALOGO)
        dominio = replace(dominio, criado_em=self._relogio.agora())
        self._repositorio.inserir_dominio(inquilino, dominio)
        return dominio

    def listar_dominios(self, origem: Origem, pagina: ParametrosDePagina) -> Pagina[Dominio]:
        inquilino = exigir(origem, Permissao.LER)
        return self._repositorio.listar_dominios(inquilino, pagina, pagina.ordenacao(CAMPOS_ORDENAVEIS, "id"))

    def criar_perfil(self, origem: Origem, perfil: Perfil) -> Perfil:
        inquilino = self._para_escrita(origem, Permissao.GERIR_CATALOGO)
        erros = [
            ErroDeCampo(f"/grandezas/{indice}", "mínimo maior que o máximo")
            for indice, grandeza in enumerate(perfil.grandezas.values())
            if grandeza.minimo is not None and grandeza.maximo is not None and grandeza.minimo > grandeza.maximo
        ]
        if erros:
            raise DadosInvalidos("Perfil inválido.", erros)
        self._repositorio.inserir_perfil(inquilino, perfil, self._relogio.agora())
        return perfil

    def listar_perfis(self, origem: Origem, pagina: ParametrosDePagina) -> Pagina[Perfil]:
        inquilino = exigir(origem, Permissao.LER)
        return self._repositorio.listar_perfis(inquilino, pagina, pagina.ordenacao(("id", "nome"), "id"))

    def criar_site(self, origem: Origem, site: Site) -> Site:
        inquilino = self._para_escrita(origem, Permissao.GERIR_CATALOGO)
        site = replace(site, criado_em=self._relogio.agora())
        self._repositorio.inserir_site(inquilino, site)
        return site

    def listar_sites(self, origem: Origem, pagina: ParametrosDePagina) -> Pagina[Site]:
        inquilino = exigir(origem, Permissao.LER)
        return self._repositorio.listar_sites(inquilino, pagina, pagina.ordenacao(CAMPOS_ORDENAVEIS, "id"))

    def criar_area(self, origem: Origem, area: Area) -> Area:
        inquilino = self._para_escrita(origem, Permissao.GERIR_CATALOGO)
        self._garantir_site(inquilino, area.site)
        area = replace(area, criado_em=self._relogio.agora())
        self._repositorio.inserir_area(inquilino, area)
        return area

    def listar_areas(self, origem: Origem, site: str, pagina: ParametrosDePagina) -> Pagina[Area]:
        inquilino = exigir(origem, Permissao.LER)
        self._garantir_site(inquilino, site)
        return self._repositorio.listar_areas(inquilino, site, pagina, pagina.ordenacao(CAMPOS_ORDENAVEIS, "id"))

    # Dispositivos ---------------------------------------------------------------------------

    def cadastrar_dispositivo(self, origem: Origem, dados: DispositivoCadastrado) -> tuple[DispositivoCadastrado, str]:
        """Cadastra e emite o token do dispositivo (RF-DIS-01, RF-DIS-02)."""
        inquilino = self._para_escrita(origem, Permissao.CADASTRAR_DISPOSITIVOS)
        repositorio = self._repositorio
        erros = []
        if repositorio.obter_perfil(inquilino, dados.perfil) is None:
            erros.append(ErroDeCampo("/perfil", "perfil não cadastrado no inquilino"))
        if not repositorio.existe_dominio(inquilino, dados.dominio):
            erros.append(ErroDeCampo("/dominio", "domínio não cadastrado no inquilino"))
        if not repositorio.existe_site(inquilino, dados.site):
            erros.append(ErroDeCampo("/site", "local não cadastrado no inquilino"))
        elif dados.area and not repositorio.existe_area(inquilino, dados.site, dados.area):
            erros.append(ErroDeCampo("/area", "área não cadastrada no local"))
        if erros:
            raise DadosInvalidos("O dispositivo referencia itens que não existem no catálogo.", erros)
        token = self._credenciais.novo_segredo()
        dispositivo = replace(dados, inquilino=inquilino, criado_em=self._relogio.agora(), revogado_em=None)
        repositorio.inserir_dispositivo(dispositivo, self._credenciais.hash(token))
        return dispositivo, token

    def obter_dispositivo(self, origem: Origem, dispositivo: str) -> DispositivoCadastrado:
        inquilino = exigir(origem, Permissao.LER)
        encontrado = self._repositorio.obter_dispositivo(inquilino, dispositivo)
        if encontrado is None:
            raise NaoEncontrado("Dispositivo não encontrado no inquilino.")
        return encontrado

    def listar_dispositivos(
        self, origem: Origem, filtros: dict[str, str | None], pagina: ParametrosDePagina
    ) -> Pagina[DispositivoCadastrado]:
        inquilino = exigir(origem, Permissao.LER)
        filtros = {campo: valor for campo, valor in filtros.items() if campo in FILTROS_DISPOSITIVO and valor}
        return self._repositorio.listar_dispositivos(
            inquilino, filtros, pagina, pagina.ordenacao(CAMPOS_ORDENAVEIS_DISPOSITIVO, "id")
        )

    def revogar_credencial(self, origem: Origem, dispositivo: str) -> None:
        inquilino = exigir(origem, Permissao.CADASTRAR_DISPOSITIVOS)
        if not self._repositorio.revogar_credencial(inquilino, dispositivo, self._relogio.agora()):
            raise NaoEncontrado("Dispositivo não encontrado no inquilino.")

    # Apoio ----------------------------------------------------------------------------------

    def _para_escrita(self, origem: Origem, permissao: Permissao) -> str:
        inquilino = exigir(origem, permissao)
        assert inquilino is not None
        self._garantir_inquilino(inquilino)
        return inquilino

    def _garantir_inquilino(self, inquilino: str) -> None:
        if not self._repositorio.existe_inquilino(inquilino):
            raise NaoEncontrado(f"Inquilino {inquilino!r} não cadastrado.")

    def _garantir_site(self, inquilino: str, site: str) -> None:
        if not self._repositorio.existe_site(inquilino, site):
            raise NaoEncontrado(f"Local {site!r} não encontrado no inquilino.")
