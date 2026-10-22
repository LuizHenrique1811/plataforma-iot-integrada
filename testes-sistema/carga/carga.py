"""Teste de carga da central: 1.000 msg/s por MQTT (RNF-01) e latência p95 (RNF-02).

Mede de fora, como um cliente qualquer, contra a central que está no ar (infra/central):

- Vazão: publica TAXA mensagens/s durante DURACAO_S segundos, em QoS 1, espalhadas por DISPOSITIVOS sensores.
- Latência até a persistência: persistido_em menos o timestamp da medição, que o gerador carimba na hora do
  envio. Inclui a espera na fila do broker, não só o tempo dentro do pipeline.
- Latência até a regra: um sensor sentinela alterna acima e abaixo do limite a cada segundo; a regra publica
  num tópico do inquilino e o gerador mede a hora da chegada menos a hora da medição.
- Perdas e duplicatas: cada mensagem publicada aparece exatamente uma vez em medicoes, e nada é rejeitado.

O catálogo do teste fica num inquilino próprio ("carga"), criado pela API e reaproveitado nas execuções
seguintes. As medidas vêm do TimescaleDB da central (só leitura). O resultado vai para resultado.md.

Uso: docker compose -f testes-sistema/carga/compose.yaml run --rm --build carga
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

import paho.mqtt.client as mqtt
import psycopg
from paho.mqtt.enums import CallbackAPIVersion

RAIZ = Path(__file__).resolve().parents[2]
RESULTADO = Path(__file__).resolve().parent / "resultado.md"

TAXA = int(os.environ.get("TAXA", "1000"))
DURACAO_S = int(os.environ.get("DURACAO_S", "60"))
DISPOSITIVOS = int(os.environ.get("DISPOSITIVOS", "100"))
CENTRAL = os.environ.get("CENTRAL_URL", "http://host.docker.internal:8000").rstrip("/")
MQTT_HOST = os.environ.get("MQTT_HOST", "host.docker.internal")
MQTT_PORTA = int(os.environ.get("MQTT_PORTA", "1883"))
BANCO_HOST = os.environ.get("BANCO_HOST", "host.docker.internal")

# Metas do documento de requisitos.
META_P95_PERSISTENCIA_S = 2.0  # RNF-02
META_P95_REGRA_S = 3.0  # RNF-02

INQUILINO, SITE, DOMINIO = "carga", "laboratorio", "teste_carga"
SENTINELA = "carga-sentinela"
TOPICO_DE_ALERTA = f"{INQUILINO}/alertas/sentinela"


def ler_env(caminho: Path) -> dict[str, str]:
    if not caminho.exists():
        return {}
    pares = (linha.split("=", 1) for linha in caminho.read_text(encoding="utf-8").splitlines() if "=" in linha)
    return {chave.strip(): valor.strip() for chave, valor in pares if not chave.lstrip().startswith("#")}


def chamar(metodo: str, caminho: str, chave: str, corpo: dict | None = None) -> int:
    requisicao = urllib.request.Request(
        CENTRAL + caminho,
        data=json.dumps(corpo).encode() if corpo is not None else None,
        headers={"Content-Type": "application/json", "X-Chave-API": chave, "X-Inquilino": INQUILINO},
        method=metodo,
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=15) as resposta:
            return resposta.status
    except urllib.error.HTTPError as erro:
        if erro.code != 409:
            sys.exit(f"falhou {metodo} {caminho}: HTTP {erro.code} {erro.read()[:300]!r}")
        return erro.code
    except urllib.error.URLError as erro:
        sys.exit(f"central fora do ar em {CENTRAL}: {erro.reason}. Suba infra/central (infra/README.md).")


def preparar_catalogo(chave: str, sensores: list[str]) -> None:
    """Cria (ou reaproveita) o cenário do teste só pela API, como qualquer outro cenário (RNF-08)."""
    itens = [
        ("/api/v1/inquilinos", {"id": INQUILINO, "nome": "Teste de carga"}),
        ("/api/v1/catalogo/dominios", {"id": DOMINIO, "nome": "Teste de carga"}),
        ("/api/v1/catalogo/perfis", {"id": "sensor-carga", "nome": "Sensor do teste de carga", "intervalo_envio_s": 1,
                                     "grandezas": [{"grandeza": "nivel", "unidade": "%", "minimo": 0,
                                                    "maximo": 100}]}),
        ("/api/v1/sites", {"id": SITE, "nome": "Laboratório"}),
        ("/api/v1/sites/laboratorio/areas", {"id": "bancada", "nome": "Bancada"}),
    ] + [
        ("/api/v1/dispositivos", {"id": nome, "perfil": "sensor-carga", "dominio": DOMINIO, "site": SITE,
                                  "area": "bancada"})
        for nome in (*sensores, SENTINELA)
    ] + [
        ("/api/v1/regras", {"id": "sentinela-acima", "nome": "Sentinela acima de 90%",
                            "condicao": {"tipo": "limite", "grandeza": "nivel", "operador": ">", "valor": 90,
                                         "dispositivo": SENTINELA},
                            "acoes": [{"tipo": "publicar", "topico": TOPICO_DE_ALERTA}]}),
    ]  # fmt: skip
    criados = sum(chamar("POST", caminho, chave, corpo) == 201 for caminho, corpo in itens)
    print(f"catálogo do inquilino '{INQUILINO}': {criados} itens criados, {len(itens) - criados} já existiam")


def mensagem(dispositivo: str, valor: float) -> tuple[str, str]:
    agora = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    carga = {
        "versao": "1.0",
        "id_mensagem": str(uuid.uuid4()),
        "dispositivo": dispositivo,
        "tipo": "telemetria",
        "timestamp": agora,
        "medidas": [{"grandeza": "nivel", "valor": valor, "unidade": "%"}],
    }
    return f"{INQUILINO}/{SITE}/{DOMINIO}/{dispositivo}/telemetria", json.dumps(carga)


def conectar(cliente_id: str) -> mqtt.Client:
    cliente = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=cliente_id, protocol=mqtt.MQTTv311)
    cliente.max_inflight_messages_set(1000)
    cliente.max_queued_messages_set(0)
    cliente.connect(MQTT_HOST, MQTT_PORTA, keepalive=30)
    cliente.loop_start()
    return cliente


def percentil(valores: list[float], p: float) -> float:
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, int(round(p * (len(ordenados) - 1))))] if ordenados else float("nan")


def publicar_carga(sensores: list[str]) -> tuple[datetime, int, list[float], float]:
    """Publica a carga no ritmo pedido; devolve o início, o total publicado, as latências da regra e a duração."""
    latencias_da_regra: list[float] = []
    observador = conectar(f"carga-observador-{uuid.uuid4().hex[:6]}")

    def ao_receber_alerta(_cliente, _dados, msg) -> None:
        ocorrido = datetime.fromisoformat(json.loads(msg.payload)["ocorrido_em"].replace("Z", "+00:00"))
        latencias_da_regra.append((datetime.now(UTC) - ocorrido).total_seconds())

    observador.on_message = ao_receber_alerta
    observador.subscribe(TOPICO_DE_ALERTA, qos=1)

    confirmadas = threading.Semaphore(0)
    gerador = conectar(f"carga-gerador-{uuid.uuid4().hex[:6]}")
    gerador.on_publish = lambda *_argumentos: confirmadas.release()
    time.sleep(1)  # assinatura do observador ativa antes da primeira mensagem

    # Truncado em milissegundos, como os timestamps das mensagens; senão a primeira ficaria de fora da contagem.
    agora = datetime.now(UTC)
    inicio = agora.replace(microsecond=agora.microsecond // 1000 * 1000)
    relogio_inicial = time.perf_counter()
    publicadas = 0
    proximo_sentinela = 0.0
    alto = False
    while (decorrido := time.perf_counter() - relogio_inicial) < DURACAO_S:
        # Sentinela: alterna a cada segundo, e a regra dispara a cada subida (na transição).
        if decorrido >= proximo_sentinela:
            alto = not alto
            gerador.publish(*mensagem(SENTINELA, 95.0 if alto else 5.0), qos=1)
            publicadas += 1
            proximo_sentinela += 1.0
        devidas = int(decorrido * TAXA)
        while publicadas < devidas:
            gerador.publish(*mensagem(sensores[publicadas % len(sensores)], round(publicadas % 80 + 0.5, 1)), qos=1)
            publicadas += 1
        time.sleep(0.002)
    duracao = time.perf_counter() - relogio_inicial

    # Todas as publicações confirmadas pelo broker (PUBACK) antes de medir.
    for _ in range(publicadas):
        if not confirmadas.acquire(timeout=60):
            sys.exit("o broker não confirmou todas as publicações em 60 s")
    gerador.disconnect()
    gerador.loop_stop()
    time.sleep(3)  # o último alerta da regra ainda pode estar a caminho
    observador.disconnect()
    observador.loop_stop()
    return inicio, publicadas, latencias_da_regra, duracao


def esperar_persistencia(banco: psycopg.Connection, inicio: datetime, publicadas: int) -> int:
    """Espera a central terminar de gravar; para se a contagem não andar por 30 s."""
    gravadas, ultima_mudanca = -1, time.monotonic()
    while time.monotonic() - ultima_mudanca < 30:
        atual = banco.execute(
            "SELECT count(*) FROM medicoes WHERE inquilino_id = %s AND medido_em >= %s", (INQUILINO, inicio)
        ).fetchone()[0]
        if atual >= publicadas:
            return atual
        if atual != gravadas:
            gravadas, ultima_mudanca = atual, time.monotonic()
        time.sleep(1)
    return gravadas


def medir(banco: psycopg.Connection, inicio: datetime) -> dict:
    linha = banco.execute(
        """
        SELECT count(*), count(DISTINCT id_mensagem),
               extract(epoch FROM max(persistido_em) - min(persistido_em)),
               percentile_cont(ARRAY[0.5, 0.95, 0.99]) WITHIN GROUP (
                   ORDER BY extract(epoch FROM persistido_em - medido_em)),
               max(extract(epoch FROM persistido_em - medido_em)),
               percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM persistido_em - recebido_em))
        FROM medicoes WHERE inquilino_id = %s AND medido_em >= %s
        """,
        (INQUILINO, inicio),
    ).fetchone()
    rejeitadas = banco.execute(
        "SELECT count(*) FROM rejeitadas WHERE inquilino_id = %s AND recebido_em >= %s", (INQUILINO, inicio)
    ).fetchone()[0]
    total, distintas, janela, (p50, p95, p99), maximo, p95_pipeline = linha
    return {
        "gravadas": total,
        "distintas": distintas,
        "vazao": total / float(janela) if janela else float("nan"),
        "p50": p50,
        "p95": p95,
        "p99": p99,
        "max": float(maximo),
        "p95_pipeline": p95_pipeline,
        "rejeitadas": rejeitadas,
    }


def main() -> None:
    env = ler_env(RAIZ / "infra" / "central" / ".env")
    if not env.get("CHAVE_ADMIN") or not env.get("POSTGRES_PASSWORD"):
        sys.exit("Preencha CHAVE_ADMIN e POSTGRES_PASSWORD em infra/central/.env (infra/README.md).")
    sensores = [f"carga-{numero:03d}" for numero in range(DISPOSITIVOS)]
    preparar_catalogo(env["CHAVE_ADMIN"], sensores)

    print(f"publicando {TAXA} msg/s por {DURACAO_S} s em {DISPOSITIVOS} sensores (QoS 1)...")
    inicio, publicadas, latencias_da_regra, duracao = publicar_carga(sensores)
    print(f"{publicadas} mensagens publicadas e confirmadas pelo broker em {duracao:.1f} s")

    conexao = (
        f"host={BANCO_HOST} port=5432 dbname={env.get('POSTGRES_DB', 'iot')} "
        f"user={env.get('POSTGRES_USER', 'iot')} password={env['POSTGRES_PASSWORD']}"
    )
    with psycopg.connect(conexao, autocommit=True) as banco:
        esperar_persistencia(banco, inicio, publicadas)
        resultado = medir(banco, inicio)

    p95_regra = percentil(latencias_da_regra, 0.95)
    disparos_esperados = DURACAO_S // 2
    criterios = [
        ("Nenhuma mensagem perdida", f"{resultado['gravadas']} de {publicadas}", resultado["gravadas"] == publicadas),
        ("Nenhuma duplicata", f"{resultado['gravadas'] - resultado['distintas']}",
         resultado["gravadas"] == resultado["distintas"]),
        ("Nenhuma rejeitada", f"{resultado['rejeitadas']}", resultado["rejeitadas"] == 0),
        (f"Vazão sustentada ≥ {TAXA} msg/s (RNF-01)", f"{resultado['vazao']:.0f} msg/s",
         resultado["vazao"] >= 0.98 * TAXA),
        (f"p95 envio → persistência ≤ {META_P95_PERSISTENCIA_S:.0f} s (RNF-02)", f"{resultado['p95']:.3f} s",
         resultado["p95"] <= META_P95_PERSISTENCIA_S),
        (f"p95 envio → disparo da regra ≤ {META_P95_REGRA_S:.0f} s (RNF-02)",
         f"{p95_regra:.3f} s em {len(latencias_da_regra)} disparos",
         p95_regra <= META_P95_REGRA_S and len(latencias_da_regra) >= disparos_esperados - 1),
    ]  # fmt: skip
    aprovado = all(ok for _, _, ok in criterios)

    linhas = [
        "# Resultado do teste de carga",
        "",
        f"Execução em {inicio:%Y-%m-%d %H:%M} UTC: {TAXA} msg/s por {DURACAO_S} s, {DISPOSITIVOS} sensores mais o "
        f"sentinela, MQTT QoS 1 na central. Gerado por `carga.py`; o ambiente está descrito no README.",
        "",
        "| Critério | Medido | Resultado |",
        "|---|---|---|",
        *[f"| {nome} | {medido} | {'ok' if ok else 'FALHOU'} |" for nome, medido, ok in criterios],
        "",
        "| Latência envio → persistência | Valor |",
        "|---|---|",
        f"| p50 | {resultado['p50']:.3f} s |",
        f"| p95 | {resultado['p95']:.3f} s |",
        f"| p99 | {resultado['p99']:.3f} s |",
        f"| máxima | {resultado['max']:.3f} s |",
        f"| p95 só dentro do serviço (recebido → persistido) | {resultado['p95_pipeline']:.3f} s |",
        "",
        f"**Resultado geral: {'aprovado' if aprovado else 'reprovado'}.**",
    ]
    texto = "\n".join(linhas) + "\n"
    RESULTADO.write_text(texto, encoding="utf-8")
    print("\n" + texto)
    sys.exit(0 if aprovado else 1)


if __name__ == "__main__":
    main()
