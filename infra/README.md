# Infraestrutura

Dois ambientes Docker Compose usam a mesma imagem do `servico-core` com configurações diferentes ([ADR-0006](../docs/adr/0006-uma-imagem-dois-ambientes.md)). A pilha é enxuta por causa do prazo ([ADR-0007](../docs/adr/0007-infraestrutura-aberta.md)):

| Pasta | Ambiente | Serviços |
|---|---|---|
| [central/](central) | Instância central | Mosquitto, TimescaleDB, Grafana, `servico-core` |
| [borda/](borda) | Nó de borda | Mosquitto (o `servico-core` da borda entra com a fila SQLite) |
| [grafana/](grafana) | Provisionamento do Grafana | Fonte de dados TimescaleDB (painéis depois) |

Na central, o `servico-core` é construído a partir de `servico-core/Dockerfile` no primeiro `up` e aplica as migrações do banco ao iniciar.

Redis, Keycloak, o servidor Prometheus e o PostGIS ficaram fora de propósito e estão registrados como evolução ([ADR-0007](../docs/adr/0007-infraestrutura-aberta.md), [ADR-0017](../docs/adr/0017-ultimo-estado-no-postgresql.md), [ADR-0018](../docs/adr/0018-autenticacao-sem-keycloak.md)).

## Como subir

Em cada pasta (`central/` e `borda/`):

1. Copie `.env.example` para `.env` e preencha as senhas e a `CHAVE_ADMIN`. O Compose recusa subir se uma delas estiver vazia.
2. Rode:

```bash
docker compose up -d --build
```

As versões das imagens são fixas. Com a central no ar:

- documentação interativa da API: <http://localhost:8000/docs>
- saúde: <http://localhost:8000/saude>
- métricas: <http://localhost:8000/metrics>
- Grafana: <http://localhost:3000>

## Portas

Todas são publicadas em `127.0.0.1` por padrão. Use `BIND_ADDR=0.0.0.0` no `.env` para aceitar dispositivos de outras máquinas da rede.

| Serviço | Central | Borda |
|---|---|---|
| MQTT | 1883 | 1884 |
| servico-core: API, Swagger UI e `/metrics` | 8000 | 8001 (futuro) |
| PostgreSQL / TimescaleDB | 5432 | — |
| Grafana | 3000 | — |

## Corte de link na demonstração

A borda sincroniza com a central pela rede Docker `iot-link`, compartilhada entre os dois projetos. Quando o `servico-core` entrar, descomente os blocos `networks` nos dois arquivos e crie a rede uma vez:

```bash
docker network create iot-link
```

Para simular a queda e a volta do link:

```bash
docker network disconnect iot-link iot-borda-servico-core-1
```

```bash
docker network connect iot-link iot-borda-servico-core-1
```

O teste de 72 h não depende disso: ele injeta mensagens com timestamps retroativos ([testes-sistema/desconexao](../testes-sistema/desconexao)).

## Pendências

- **Autenticação e ACL no Mosquitto** (RF-SEG-04, RF-DIS-02): hoje os dois brokers aceitam conexões anônimas. O plano é o plugin de segurança dinâmica do Mosquitto, administrado pelo `servico-core` ([ADR-0018](../docs/adr/0018-autenticacao-sem-keycloak.md)).
- **TLS** (RF-ING-01, RNF-11): os brokers usam a porta 1883 sem TLS.
- **Usuário somente leitura para o Grafana**: a fonte TimescaleDB usa o usuário principal do banco até o esquema existir.
- **Chave da fila da borda** (RF-SEG-05): o Docker secret está previsto no `borda/compose.yaml`, comentado ([ADR-0014](../docs/adr/0014-chave-da-fila-da-borda.md)).
