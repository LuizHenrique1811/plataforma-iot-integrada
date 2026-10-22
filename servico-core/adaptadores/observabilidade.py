"""Logs JSON com correlation_id e métricas no formato Prometheus (RF-OBS-01, RF-OBS-02)."""

import json
import logging
import sys
from datetime import UTC, datetime

from prometheus_client import Counter, Histogram

from dominio.modelos import ResultadoIngestao

_CAMPOS_EXTRAS = ("correlation_id", "entrada", "situacao", "etapa", "motivo", "inquilino", "dispositivo")

MENSAGENS = Counter(
    "iot_mensagens_total",
    "Mensagens processadas pelo pipeline de ingestão.",
    ["entrada", "situacao", "motivo"],
)
DURACAO = Histogram(
    "iot_ingestao_duracao_segundos",
    "Tempo de processamento de uma mensagem no pipeline, até a persistência.",
    ["entrada"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

log = logging.getLogger("servico_core.ingestao")


class FormatadorJson(logging.Formatter):
    def format(self, registro: logging.LogRecord) -> str:
        dados = {
            "ts": datetime.fromtimestamp(registro.created, UTC).isoformat(),
            "nivel": registro.levelname,
            "logger": registro.name,
            "mensagem": registro.getMessage(),
        }
        for campo in _CAMPOS_EXTRAS:
            if hasattr(registro, campo):
                dados[campo] = getattr(registro, campo)
        if registro.exc_info:
            dados["excecao"] = self.formatException(registro.exc_info)
        return json.dumps(dados, ensure_ascii=False)


def configurar_logs(nivel: str) -> None:
    saida = logging.StreamHandler(sys.stdout)
    saida.setFormatter(FormatadorJson())
    raiz = logging.getLogger()
    raiz.handlers[:] = [saida]
    raiz.setLevel(nivel.upper())


def observar(resultado: ResultadoIngestao, entrada: str, duracao_s: float) -> None:
    """Registra uma mensagem processada: métrica e log com correlation_id igual ao id_mensagem."""
    rejeicao = resultado.rejeicao
    motivo = rejeicao.motivo.value if rejeicao else ""
    MENSAGENS.labels(entrada=entrada, situacao=resultado.situacao.value, motivo=motivo).inc()
    DURACAO.labels(entrada=entrada).observe(duracao_s)
    extras = {"correlation_id": resultado.id_mensagem, "entrada": entrada, "situacao": resultado.situacao.value}
    if rejeicao:
        extras.update(etapa=rejeicao.etapa.value, motivo=motivo)
    if resultado.mensagem:
        extras.update(inquilino=resultado.mensagem.inquilino, dispositivo=resultado.mensagem.dispositivo)
    nivel = logging.WARNING if rejeicao else logging.INFO
    log.log(nivel, "mensagem %s", resultado.situacao.value, extra=extras)
