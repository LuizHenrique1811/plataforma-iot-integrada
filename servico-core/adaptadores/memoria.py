"""Adaptadores em memória: testes do domínio e execução sem banco em desenvolvimento."""

from __future__ import annotations

import hmac
import threading
from dataclasses import dataclass, field

from adaptadores.credenciais import hash_segredo
from dominio.modelos import (
    DispositivoCadastrado,
    Medida,
    MensagemAceita,
    MensagemRejeitada,
    Origem,
    Perfil,
    TipoOrigem,
)


@dataclass
class CatalogoEmMemoria:
    dispositivos: dict[tuple[str, str], DispositivoCadastrado] = field(default_factory=dict)
    perfis: dict[tuple[str, str], Perfil] = field(default_factory=dict)

    def adicionar_perfil(self, inquilino: str, perfil: Perfil) -> None:
        self.perfis[(inquilino, perfil.id)] = perfil

    def adicionar_dispositivo(self, dispositivo: DispositivoCadastrado) -> None:
        self.dispositivos[(dispositivo.inquilino, dispositivo.id)] = dispositivo

    def obter_dispositivo(self, inquilino: str, dispositivo: str) -> DispositivoCadastrado | None:
        return self.dispositivos.get((inquilino, dispositivo))

    def obter_perfil(self, inquilino: str, perfil: str) -> Perfil | None:
        return self.perfis.get((inquilino, perfil))


@dataclass
class RepositorioEmMemoria:
    ids: set[str] = field(default_factory=set)
    mensagens: list[MensagemAceita] = field(default_factory=list)
    ultimo_estado: dict[tuple[str, str, str], tuple[Medida, MensagemAceita]] = field(default_factory=dict)
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
            return True


@dataclass
class FilaDeRejeitadasEmMemoria:
    itens: list[MensagemRejeitada] = field(default_factory=list)

    def registrar(self, rejeitada: MensagemRejeitada) -> None:
        self.itens.append(rejeitada)


@dataclass
class AutenticadorEmMemoria:
    """Tokens e chaves em claro só nos testes; aqui também se compara pelo hash."""

    tokens: dict[str, tuple[str, str]] = field(default_factory=dict)  # hash -> (inquilino, dispositivo)
    chaves: dict[str, tuple[str | None, str]] = field(default_factory=dict)  # hash -> (inquilino, papel)
    chave_admin: str | None = None

    def registrar_token(self, token: str, inquilino: str, dispositivo: str) -> None:
        self.tokens[hash_segredo(token)] = (inquilino, dispositivo)

    def registrar_chave(self, chave: str, inquilino: str | None, papel: str) -> None:
        self.chaves[hash_segredo(chave)] = (inquilino, papel)

    def por_token_dispositivo(self, token: str) -> Origem | None:
        encontrado = self.tokens.get(hash_segredo(token))
        if encontrado is None:
            return None
        return Origem(TipoOrigem.DISPOSITIVO, inquilino=encontrado[0], dispositivo=encontrado[1])

    def por_chave(self, chave: str) -> Origem | None:
        if self.chave_admin and hmac.compare_digest(chave, self.chave_admin):
            return Origem(TipoOrigem.CHAVE, inquilino=None, papel="administrador")
        encontrado = self.chaves.get(hash_segredo(chave))
        if encontrado is None:
            return None
        return Origem(TipoOrigem.CHAVE, inquilino=encontrado[0], papel=encontrado[1])
