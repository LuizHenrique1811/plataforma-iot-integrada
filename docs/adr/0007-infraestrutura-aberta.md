# ADR-0007: Infraestrutura aberta e enxuta

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RNF-14, RF-OBS-01, premissas da seção 2.5

## Contexto

A plataforma precisa de broker MQTT, banco de séries temporais, último estado, painéis, identidade e métricas. O documento exige componentes de código aberto, sem dependência de um provedor de nuvem no núcleo (seção 2.5), e execução em contêineres com Docker Compose no MVP e na borda (RNF-14). A seção 9.1 sugere uma pilha completa (Mosquitto, TimescaleDB, PostGIS, Redis, Keycloak, Prometheus, Grafana e outros) e diz que qualquer componente pode ser trocado.

O trabalho tem prazo de um dia e uma pessoa, e a central e a borda rodam juntas num notebook com cerca de 16 GB de RAM.

## Decisão

Usar uma pilha enxuta:

| Função | Componente | Licença |
|---|---|---|
| Broker MQTT | Eclipse Mosquitto 2 | EPL-2.0 / EDL-1.0 |
| Séries temporais | PostgreSQL 17 + TimescaleDB (imagem `timescale/timescaledb`, sem PostGIS) | PostgreSQL; Apache-2.0 e Timescale License |
| Painéis | Grafana, provisionado por arquivo | AGPL-3.0 |
| Métricas | Endpoint `/metrics` do `servico-core`, no formato Prometheus | — |

Os componentes sugeridos pelo documento que ficam de fora são substituídos ou adiados:

- **Último estado:** tabela no PostgreSQL, no lugar de Redis ([ADR-0017](0017-ultimo-estado-no-postgresql.md)).
- **Identidade:** token por dispositivo e chave de API com papéis em tabela, no lugar de Keycloak ([ADR-0018](0018-autenticacao-sem-keycloak.md)).
- **Servidor Prometheus:** não sobe. O endpoint `/metrics` já atende o critério do RF-OBS-01 ("métricas disponíveis em formato Prometheus").
- **PostGIS:** só se sobrar tempo. Basta trocar a imagem por `timescale/timescaledb-ha`, que já inclui o PostGIS.

As versões ficam fixadas nos arquivos Compose.

## Alternativas consideradas

- **A pilha completa da seção 9.1.** Atende mais requisitos de forma direta, mas Keycloak, Redis e Prometheus somam serviços para configurar e memória no notebook, sem mudar nenhum critério de aceite do MVP.
- **Serviços gerenciados de nuvem** (AWS IoT Core, Azure IoT Hub). Há dependência do fornecedor e custo, e eles não rodam numa borda desconectada.
- **InfluxDB.** Bom para séries temporais, mas o TimescaleDB mantém SQL e junções com o catálogo no mesmo banco.
- **Barramento interno dedicado** (Kafka, NATS ou RabbitMQ). No MVP, o próprio Mosquitto faz o papel de publicação e assinatura entre os componentes.

## Consequências

- A central sobe com três serviços próprios de infraestrutura (Mosquitto, TimescaleDB e Grafana) mais o `servico-core`, e a borda com Mosquitto e `servico-core`.
- Sem servidor Prometheus, os painéis de latência do Grafana (RNF-02) leem do TimescaleDB. Para isso, a ingestão grava a hora de recepção e a hora de persistência de cada mensagem.
- **Evolução prevista:** Redis para o último estado, Keycloak para OIDC e MFA, um servidor Prometheus coletando o `/metrics` e PostGIS para geometrias. A arquitetura hexagonal ([ADR-0005](0005-arquitetura-hexagonal.md)) permite cada troca escrevendo um adaptador.
- Os continuous aggregates do TimescaleDB ([ADR-0013](0013-dados-atrasados-e-agregados.md)) estão na Timescale License, que permite uso gratuito mas não é uma licença OSI. As imagens `-oss` não os incluem.
