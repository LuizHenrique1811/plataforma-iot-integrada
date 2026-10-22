from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from dominio.modelos import DispositivoCadastrado, MensagemAceita, MensagemRejeitada, Perfil

if TYPE_CHECKING:
    from dominio.catalogo import Area, ChaveDeApi, Dominio, Inquilino, Site
    from dominio.consultas import Contato, MedicaoConsultada, RejeitadaConsultada
    from dominio.paginacao import Ordenacao, Pagina, ParametrosDePagina


class Catalogo(Protocol):
    """Leitura do catálogo usada no enriquecimento (RF-PRO-01)."""

    def obter_dispositivo(self, inquilino: str, dispositivo: str) -> DispositivoCadastrado | None: ...

    def obter_perfil(self, inquilino: str, perfil: str) -> Perfil | None: ...


class RepositorioDeCatalogo(Catalogo, Protocol):
    """Escrita e listagem do catálogo. As inserções levantam JaExiste quando o identificador já existe."""

    def existe_inquilino(self, inquilino: str) -> bool: ...

    def inserir_inquilino(self, inquilino: Inquilino) -> None: ...

    def listar_inquilinos(self, pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Inquilino]: ...

    def inserir_chave(self, chave: ChaveDeApi, hash_segredo: str) -> None: ...

    def existe_dominio(self, inquilino: str, dominio: str) -> bool: ...

    def inserir_dominio(self, inquilino: str, dominio: Dominio) -> None: ...

    def listar_dominios(self, inquilino: str, pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Dominio]: ...

    def inserir_perfil(self, inquilino: str, perfil: Perfil, criado_em: datetime) -> None: ...

    def listar_perfis(self, inquilino: str, pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Perfil]: ...

    def existe_site(self, inquilino: str, site: str) -> bool: ...

    def inserir_site(self, inquilino: str, site: Site) -> None: ...

    def listar_sites(self, inquilino: str, pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Site]: ...

    def existe_area(self, inquilino: str, site: str, area: str) -> bool: ...

    def inserir_area(self, inquilino: str, area: Area) -> None: ...

    def listar_areas(
        self, inquilino: str, site: str, pagina: ParametrosDePagina, ordenacao: Ordenacao
    ) -> Pagina[Area]: ...

    def inserir_dispositivo(self, dispositivo: DispositivoCadastrado, hash_token: str) -> None: ...

    def listar_dispositivos(
        self, inquilino: str, filtros: dict[str, str], pagina: ParametrosDePagina, ordenacao: Ordenacao
    ) -> Pagina[DispositivoCadastrado]: ...

    def revogar_credencial(self, inquilino: str, dispositivo: str, quando: datetime) -> bool:
        """Revoga o token; devolve False se o dispositivo não existe."""
        ...


class RepositorioDeIngestao(Protocol):
    """Persistência das mensagens aceitas."""

    def ja_recebida(self, id_mensagem: str) -> bool:
        """Consulta rápida da janela de deduplicação (ADR-0011)."""
        ...

    def persistir(self, mensagem: MensagemAceita) -> bool:
        """Grava o id_mensagem, as medidas ou o evento, o último estado e o último contato numa transação.

        Devolve False, sem gravar nada, se o id_mensagem já existia. O último estado e o último contato
        só mudam quando a medição é mais nova que a armazenada (ADR-0017).
        """
        ...


class RepositorioDeConsultas(Protocol):
    def medicoes(
        self,
        inquilino: str,
        dispositivo: str,
        grandeza: str | None,
        inicio: datetime | None,
        fim: datetime | None,
        pagina: ParametrosDePagina,
        ordenacao: Ordenacao,
    ) -> Pagina[MedicaoConsultada]: ...

    def ultimo_estado(self, inquilino: str, dispositivo: str) -> list[MedicaoConsultada]: ...

    def ultimo_contato(self, inquilino: str, dispositivo: str) -> Contato | None: ...

    def contato_da_borda(self, inquilino: str, via: str) -> datetime | None:
        """Última vez que a central recebeu algo passando pelo nó de borda `via` (ADR-0010)."""
        ...

    def rejeitadas(
        self, inquilino: str, pagina: ParametrosDePagina, ordenacao: Ordenacao
    ) -> Pagina[RejeitadaConsultada]: ...


class FilaDeRejeitadas(Protocol):
    """Fila de mensagens inválidas (Dead Letter Channel)."""

    def registrar(self, rejeitada: MensagemRejeitada) -> None: ...
