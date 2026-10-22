# Infraestrutura

Dois ambientes Docker Compose usam a mesma imagem do `servico-core` com configurações diferentes ([ADR-0006](../docs/adr/0006-uma-imagem-dois-ambientes.md)). A pilha é enxuta por causa do prazo ([ADR-0007](../docs/adr/0007-infraestrutura-aberta.md)):

| Pasta | Ambiente | Serviços |
|---|---|---|
| [central/](central) | Instância central | Mosquitto, TimescaleDB, Grafana, `servico-core` (PostgreSQL) |
| [borda/](borda) | Nó de borda | Mosquitto, `servico-core` (SQLite cifrado, fila, regras locais e sincronização) |
| [grafana/](grafana) | Provisionamento do Grafana | Fonte de dados TimescaleDB e o painel "Plataforma IoT - visão geral" |

O `servico-core` é construído a partir de `servico-core/Dockerfile` no primeiro `up` e aplica as migrações do banco ao iniciar. Redis, Keycloak, o servidor Prometheus e o PostGIS ficaram fora de propósito e estão registrados como evolução ([ADR-0007](../docs/adr/0007-infraestrutura-aberta.md), [ADR-0017](../docs/adr/0017-ultimo-estado-no-postgresql.md), [ADR-0018](../docs/adr/0018-autenticacao-sem-keycloak.md)).

## Como subir

**1. Rede entre a central e a borda (uma vez).** Ela fica fora dos dois projetos, para cada um subir independente do outro:

```bash
docker network create iot-link
```

**2. Central.** Em `infra/central/`, copie `.env.example` para `.env` e preencha as senhas e a `CHAVE_ADMIN` (o Compose recusa subir se uma delas estiver vazia). Depois:

```bash
docker compose up -d --build
```

**3. Chave da fila da borda.** Em `infra/borda/`, crie a pasta `segredos/` e, nela, o arquivo `chave-fila` com um conteúdo aleatório. A pasta fica fora do volume de dados e fora do repositório (não existe num clone novo), simulando a mídia separada do [ADR-0014](../docs/adr/0014-chave-da-fila-da-borda.md):

```bash
mkdir segredos
```

```bash
docker run --rm python:3.12-slim python -c "import secrets; print(secrets.token_hex(32))" > segredos/chave-fila
```

**4. Borda.** Em `infra/borda/`, copie `.env.example` para `.env`, preencha `CHAVE_ADMIN` e rode o comando abaixo. `CHAVE_CENTRAL` pode ficar vazia por enquanto: sem ela, a borda funciona e acumula a fila, mas não sincroniza.

```bash
docker compose up -d --build
```

**5. Chave da borda na central.** A borda precisa de uma chave de papel `no_borda` emitida pela central. O script de preparação da demonstração ([README](../README.md#comandos-na-ordem)) faz isso: monta os cenários, emite a chave e a grava em `infra/borda/.env`. Ele também troca a chave se a central não a reconhecer mais, por exemplo depois de recriar o banco. Na raiz do repositório:

```bash
docker compose -f demo/compose.yaml run --rm preparar
```

Depois, em `infra/borda/`, aplique a chave:

```bash
docker compose up -d
```

Sem o script, emita a chave em <http://localhost:8000/docs> (`POST /api/v1/chaves` com `{"papel": "no_borda"}` e o cabeçalho `X-Inquilino`), copie-a para `CHAVE_CENTRAL` e rode o mesmo `docker compose up -d`. O catálogo e as regras locais (com `"ambito": "borda"`) são cadastrados pela API da própria borda, em <http://localhost:8001/docs>; a distribuição automática a partir da central é o RF-EDG-04 (Importante).

**6. Réplicas de ingestão (só para o teste de carga).** Em `infra/central/`, `docker compose --profile escala up -d --wait` acrescenta 9 processos de ingestão e só devolve o terminal quando todos estão saudáveis; `docker compose --profile escala stop` volta a um só ([ADR-0022](../docs/adr/0022-escala-da-ingestao-com-assinatura-compartilhada.md)).

| Endereço | Central | Borda |
|---|---|---|
| Documentação interativa da API | <http://localhost:8000/docs> | <http://localhost:8001/docs> |
| Saúde | <http://localhost:8000/saude> | <http://localhost:8001/saude> |
| Métricas (`iot_fila_pendente` na borda) | <http://localhost:8000/metrics> | <http://localhost:8001/metrics> |
| Grafana | <http://localhost:3000> | — |

## Portas

Todas são publicadas em `127.0.0.1` por padrão. Use `BIND_ADDR=0.0.0.0` no `.env` para aceitar dispositivos de outras máquinas da rede.

| Serviço | Central | Borda |
|---|---|---|
| MQTT | 1883 | 1884 |
| servico-core: API, Swagger UI e `/metrics` | 8000 | 8001 |
| PostgreSQL / TimescaleDB | 5432 | — |
| Grafana | 3000 | — |

## Corte de link na demonstração

A borda alcança a central pela rede `iot-link`, onde a central atende pelo nome `central`. Para simular a queda e a volta do link:

```bash
docker network disconnect iot-link iot-borda-servico-core-1
```

```bash
docker network connect iot-link iot-borda-servico-core-1
```

Durante o corte, a borda aceita as mensagens, executa as regras locais (o comando chega à válvula pelo broker da borda) e acumula a fila. Ao religar, a sincronização roda a cada 5 s (`SINCRONIZACAO_S`) e esvazia a fila em lotes, removendo cada lote só depois da confirmação da central.

No Docker Desktop, a porta publicada da borda (8001: API e `/metrics`) para de responder enquanto o contêiner está fora da rede `iot-link` e volta quando ele é reconectado. Os dados não são afetados, porque os sensores publicam no Mosquitto da borda, que é outro contêiner. Para acompanhar a fila durante o corte, use o log da borda, que mostra `sincronização interrompida ... (N pendentes)` a cada tentativa, ou o painel "bordas sem sincronizar" do Grafana:

```bash
docker logs -f iot-borda-servico-core-1
```

O teste de 72 h não depende disso: ele injeta mensagens com timestamps retroativos ([testes-sistema/desconexao](../testes-sistema/desconexao)).

## Consumo medido

Em repouso, numa máquina x86 com Docker Desktop, a borda inteira usou cerca de 77 MB de memória (`servico-core` 74 MB, Mosquitto 3 MB), bem abaixo dos 4 GB do equipamento de referência do RNF-06. A imagem ainda não é multi-arquitetura para ARM (ADR-0006).

## Pendências

- **Autenticação e ACL no Mosquitto** (RF-SEG-04, RF-DIS-02): hoje os dois brokers aceitam conexões anônimas, e o `servico-core` recusa mensagens publicadas no tópico de outro dispositivo ([ADR-0018](../docs/adr/0018-autenticacao-sem-keycloak.md)).
- **TLS** (RF-ING-01, RNF-11): os brokers e as APIs usam portas sem TLS.
- **Usuário somente leitura para o Grafana**: a fonte TimescaleDB usa o usuário principal do banco.
