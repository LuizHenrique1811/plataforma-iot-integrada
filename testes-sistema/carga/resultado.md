# Resultado do teste de carga

Execução em 2026-10-22 14:57 UTC: 1000 msg/s por 60 s, 100 sensores mais o sentinela, MQTT QoS 1 na central. Gerado por `carga.py`; o ambiente está descrito no README.

| Critério | Medido | Resultado |
|---|---|---|
| Nenhuma mensagem perdida | 59998 de 59998 | ok |
| Nenhuma duplicata | 0 | ok |
| Nenhuma rejeitada | 0 | ok |
| Vazão sustentada ≥ 1000 msg/s (RNF-01) | 1000 msg/s | ok |
| p95 envio → persistência ≤ 2 s (RNF-02) | 0.398 s | ok |
| p95 envio → disparo da regra ≤ 3 s (RNF-02) | 0.404 s em 30 disparos | ok |

| Latência envio → persistência | Valor |
|---|---|
| p50 | 0.022 s |
| p95 | 0.398 s |
| p99 | 0.513 s |
| máxima | 0.670 s |
| p95 só dentro do serviço (recebido → persistido) | 0.026 s |

**Resultado geral: aprovado.**
