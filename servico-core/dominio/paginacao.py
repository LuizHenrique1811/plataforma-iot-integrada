"""Paginação, filtros e ordenação iguais em todas as listagens (RF-APP-07)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from dominio.erros import DadosInvalidos
from dominio.modelos import ErroDeCampo

TAMANHO_PADRAO = 50
TAMANHO_MAXIMO = 500


@dataclass(frozen=True)
class Ordenacao:
    campo: str
    decrescente: bool = False


@dataclass(frozen=True)
class ParametrosDePagina:
    pagina: int = 1
    tamanho: int = TAMANHO_PADRAO
    ordenar: str | None = None

    def __post_init__(self) -> None:
        erros = []
        if self.pagina < 1:
            erros.append(ErroDeCampo("pagina", "a página começa em 1"))
        if not 1 <= self.tamanho <= TAMANHO_MAXIMO:
            erros.append(ErroDeCampo("tamanho", f"o tamanho vai de 1 a {TAMANHO_MAXIMO}"))
        if erros:
            raise DadosInvalidos("Parâmetros de paginação inválidos.", erros)

    @property
    def deslocamento(self) -> int:
        return (self.pagina - 1) * self.tamanho

    def ordenacao(self, permitidos: Iterable[str], padrao: str) -> Ordenacao:
        """Lê `ordenar` (prefixo `-` para decrescente), aceitando só os campos permitidos."""
        valor = self.ordenar or padrao
        campo = valor.removeprefix("-")
        permitidos = tuple(permitidos)
        if campo not in permitidos:
            raise DadosInvalidos(
                "Campo de ordenação inválido.",
                [ErroDeCampo("ordenar", f"use um de: {', '.join(permitidos)}")],
            )
        return Ordenacao(campo, valor.startswith("-"))


@dataclass(frozen=True)
class Pagina[T]:
    itens: tuple[T, ...]
    pagina: int
    tamanho: int
    total: int
