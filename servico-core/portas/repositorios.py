from typing import Protocol

from dominio.modelos import DispositivoCadastrado, MensagemAceita, MensagemRejeitada, Perfil


class Catalogo(Protocol):
    """Leitura do catálogo usada no enriquecimento (RF-PRO-01)."""

    def obter_dispositivo(self, inquilino: str, dispositivo: str) -> DispositivoCadastrado | None: ...

    def obter_perfil(self, inquilino: str, perfil: str) -> Perfil | None: ...


class RepositorioDeIngestao(Protocol):
    """Persistência das mensagens aceitas."""

    def ja_recebida(self, id_mensagem: str) -> bool:
        """Consulta rápida da janela de deduplicação (ADR-0011)."""
        ...

    def persistir(self, mensagem: MensagemAceita) -> bool:
        """Grava o id_mensagem, as medidas ou o evento e o último estado numa única transação.

        Devolve False, sem gravar nada, se o id_mensagem já existia. O último estado só muda quando
        a medição é mais nova que a armazenada (ADR-0017).
        """
        ...


class FilaDeRejeitadas(Protocol):
    """Fila de mensagens inválidas (Dead Letter Channel)."""

    def registrar(self, rejeitada: MensagemRejeitada) -> None: ...
