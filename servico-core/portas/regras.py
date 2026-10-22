from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from dominio.paginacao import Ordenacao, Pagina, ParametrosDePagina
    from dominio.regras import Alarme, EstadoDaRegra, Regra


class RepositorioDeRegras(Protocol):
    def inserir_regra(self, inquilino: str, regra: Regra) -> None:
        """Levanta JaExiste se já houver regra com o mesmo id no inquilino."""
        ...

    def listar_regras(self, inquilino: str, pagina: ParametrosDePagina, ordenacao: Ordenacao) -> Pagina[Regra]: ...

    def regras_ativas(self, inquilino: str, ambito: str) -> list[Regra]: ...

    def regras_de_ausencia(self, ambito: str) -> list[tuple[str, Regra]]:
        """Regras ativas de ausência de dados de todos os inquilinos, com o inquilino de cada uma."""
        ...

    def obter_estado(self, inquilino: str, regra: str, dispositivo: str) -> EstadoDaRegra | None: ...

    def salvar_estado(self, inquilino: str, regra: str, dispositivo: str, estado: EstadoDaRegra) -> None: ...

    def ultimas_leituras(
        self, inquilino: str, filtros: dict[str, str], grandeza: str
    ) -> list[tuple[str, datetime | None]]:
        """Dispositivos ativos que casam com os filtros e o horário da última leitura da grandeza.

        Sem leitura, vale a data de cadastro do dispositivo, para um dispositivo novo não disparar na hora.
        """
        ...


class RepositorioDeAlarmes(Protocol):
    def inserir_alarme(self, alarme: Alarme) -> bool:
        """Grava o alarme; devolve False se já existe um alarme aberto da mesma regra e dispositivo."""
        ...

    def obter_alarme(self, inquilino: str, alarme: str) -> Alarme | None: ...

    def atualizar_alarme(self, alarme: Alarme) -> None: ...

    def resolver_abertos(self, inquilino: str, regra: str, dispositivo: str, quando: datetime) -> int: ...

    def listar_alarmes(
        self, inquilino: str, filtros: dict[str, Any], pagina: ParametrosDePagina, ordenacao: Ordenacao
    ) -> Pagina[Alarme]: ...
