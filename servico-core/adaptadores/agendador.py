"""Tarefa periódica em segundo plano (verificação de ausência de dados, RF-PRO-02)."""

import logging
import threading
from collections.abc import Callable

log = logging.getLogger("servico_core.agendador")


class TarefaPeriodica:
    def __init__(self, nome: str, intervalo_s: float, funcao: Callable[[], object]) -> None:
        self._nome = nome
        self._intervalo_s = intervalo_s
        self._funcao = funcao
        self._parar = threading.Event()
        self._thread = threading.Thread(target=self._laco, name=nome, daemon=True)

    def iniciar(self) -> None:
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
        if self._thread.is_alive():
            self._thread.join(timeout=self._intervalo_s + 5)

    def _laco(self) -> None:
        while not self._parar.wait(self._intervalo_s):
            try:
                self._funcao()
            except Exception:
                log.exception("falha na tarefa periódica %s", self._nome)
