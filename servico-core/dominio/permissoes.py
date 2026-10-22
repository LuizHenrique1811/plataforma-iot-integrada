"""Papéis e permissões (RF-SEG-02, ADR-0018).

Critério do documento: "operador não consegue alterar regras nem dispositivos".
"""

from enum import StrEnum

from dominio.erros import AcessoNegado, DadosInvalidos
from dominio.modelos import ErroDeCampo, Origem, TipoOrigem


class Permissao(StrEnum):
    LER = "ler"
    GERIR_CATALOGO = "gerir o catálogo"
    CADASTRAR_DISPOSITIVOS = "cadastrar dispositivos"
    GERIR_CHAVES = "emitir chaves de API"
    GERIR_INQUILINOS = "gerir inquilinos"
    GERIR_REGRAS = "gerir regras"
    OPERAR_ALARMES = "operar alarmes"


PERMISSOES: dict[str, frozenset[Permissao]] = {
    "administrador": frozenset(Permissao),
    "gestor": frozenset(
        {
            Permissao.LER,
            Permissao.GERIR_CATALOGO,
            Permissao.CADASTRAR_DISPOSITIVOS,
            Permissao.GERIR_CHAVES,
            Permissao.GERIR_REGRAS,
            Permissao.OPERAR_ALARMES,
        }
    ),
    "integrador": frozenset({Permissao.LER, Permissao.CADASTRAR_DISPOSITIVOS}),
    "operador": frozenset({Permissao.LER, Permissao.OPERAR_ALARMES}),
    "leitor": frozenset({Permissao.LER}),
    "no_borda": frozenset({Permissao.LER}),
}


def exigir(origem: Origem, permissao: Permissao, *, com_inquilino: bool = True) -> str | None:
    """Confere a permissão e devolve o inquilino em que a operação acontece."""
    papel = origem.papel or ""
    if origem.tipo is not TipoOrigem.CHAVE or permissao not in PERMISSOES.get(papel, frozenset()):
        quem = f"o papel {papel!r}" if papel else "um dispositivo"
        raise AcessoNegado(f"{quem} não pode {permissao.value}")
    if com_inquilino and origem.inquilino is None:
        raise DadosInvalidos(
            "Operação dentro de um inquilino.",
            [ErroDeCampo("X-Inquilino", "o administrador da plataforma precisa informar o inquilino")],
        )
    return origem.inquilino
