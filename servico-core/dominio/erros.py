"""Erros dos casos de uso. Cada adaptador de entrada os traduz para o seu protocolo."""

from dominio.modelos import ErroDeCampo


class ErroDeDominio(Exception):
    codigo = "erro"

    def __init__(self, mensagem: str, erros: tuple[ErroDeCampo, ...] | list[ErroDeCampo] = ()) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.erros = tuple(erros)


class AcessoNegado(ErroDeDominio):
    codigo = "acesso_negado"


class NaoEncontrado(ErroDeDominio):
    codigo = "nao_encontrado"


class JaExiste(ErroDeDominio):
    codigo = "ja_existe"


class DadosInvalidos(ErroDeDominio):
    codigo = "dados_invalidos"


class Conflito(ErroDeDominio):
    """Transição de estado não permitida (ex.: reconhecer um alarme já resolvido)."""

    codigo = "transicao_invalida"
