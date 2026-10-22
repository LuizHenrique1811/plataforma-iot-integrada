# Plataforma IoT Integrada

Trabalho da disciplina de Internet das Coisas (UniEVANGÉLICA). Implementa a plataforma descrita no Documento de Requisitos v2.0 ([docs/requisitos.md](docs/requisitos.md)), que é a fonte da verdade do projeto. Os IDs citados aqui (RF-XXX-nn, RNF-nn, UC-nn) são os do documento.

> **Status:** em construção. O andamento de cada requisito está em [docs/rastreabilidade.md](docs/rastreabilidade.md).

## Ideias centrais

1. **Independência de linguagem.** Não existe biblioteca obrigatória. A integração é feita por contratos abertos (JSON Schema, AsyncAPI 3, OpenAPI 3, GeoJSON): qualquer coisa que fale MQTT ou HTTP e monte um JSON integra.
2. **Neutralidade de cenário (RNF-08).** O núcleo não conhece "praça", "talhão" ou "silo". Domínios, perfis de dispositivo, locais e regras são dados configuráveis, nunca constantes ou classes no código.
3. **Operação desconectada.** O nó de borda guarda os dados numa fila persistente, executa regras locais e sincroniza em lotes quando o link volta. A central deduplica por `id_mensagem`, ordena pelo `timestamp` da medição e aceita dados atrasados.

## Arquitetura

- **Núcleo:** Python 3.12 + FastAPI, com arquitetura hexagonal. O `dominio/` não importa framework, driver MQTT nem banco; tudo entra e sai por `portas/`, implementadas em `adaptadores/`.
- **Uma imagem, dois ambientes:** o `servico-core` gera uma única imagem Docker. A central usa PostgreSQL + TimescaleDB; a borda usa SQLite cifrado.
- **Infraestrutura aberta e enxuta:** Mosquitto (MQTT), PostgreSQL + TimescaleDB (séries, catálogo e último estado), Grafana (painéis provisionados) e endpoint `/metrics` no formato Prometheus. Autenticação por token de dispositivo e chave de API com papéis. Redis, Keycloak, servidor Prometheus e PostGIS ficam como evolução ([ADR-0007](docs/adr/0007-infraestrutura-aberta.md)).
- **Pipeline de ingestão:** autenticar → validar contra o JSON Schema → deduplicar por `id_mensagem` → enriquecer com perfil, domínio, local e área → ordenar pelo `timestamp` da medição → persistir. Mensagens rejeitadas vão para a DLQ com o motivo.

## Estrutura do repositório

```
plataforma-iot-integrada/
├── contratos/              # contrato primeiro
│   ├── json-schema/        # mensagem canônica v1.0
│   ├── asyncapi.yaml
│   └── openapi.yaml
├── servico-core/           # API, catálogo, ingestão, regras
│   ├── dominio/
│   ├── portas/
│   ├── adaptadores/        # mqtt, rest, lote, postgres, sqlite
│   └── testes/
├── adaptadores-plugaveis/
│   └── ar-urbano/          # contêiner próprio: JSON legado -> canônico
├── simuladores/            # integração em 3 linguagens
│   ├── python/
│   ├── javascript/
│   └── java/
├── infra/
│   ├── central/            # compose: Mosquitto, TimescaleDB, Grafana, servico-core
│   ├── borda/              # compose: Mosquitto, servico-core com SQLite
│   └── grafana/            # painéis provisionados
├── testes-sistema/
│   ├── desconexao/         # injeta 72 h de mensagens retroativas
│   └── carga/              # 1.000 msg/s
├── docs/
│   ├── requisitos.md
│   ├── arquitetura.md
│   ├── rastreabilidade.md  # requisito -> status -> evidência
│   └── adr/
└── .github/workflows/      # CI: testes, validação de contratos
```

## Roteiro da demonstração (10 a 15 min)

| # | Passo | O que mostrar | Requisitos |
|---|---|---|---|
| 1 | Domínio novo ao vivo | Criar o domínio `recursos_hidricos` e um perfil de reservatório só por configuração, sem tocar no código nem reiniciar serviços. | UC-06, RNF-08 |
| 2 | Rural com borda | Simuladores de solo e silo publicam no Mosquitto da borda. A regra local liga a irrigação sem depender da central. | UC-01, UC-02, RF-EDG-03 |
| 3 | Corte de link | Desconectar a borda da central e continuar gerando dados. Ao religar, o histórico chega completo, sem duplicatas e na hora da medição. | RF-ING-08, RF-EDG-01/02 |
| 4 | Urbano nível 2 | Um simulador envia JSON legado; o adaptador `ar-urbano`, em contêiner próprio, traduz para a mensagem canônica sem reiniciar o núcleo. | UC-03, RF-INT-03 |
| 5 | Três linguagens | Simuladores em Python, JavaScript e Java usando só bibliotecas genéricas de MQTT e HTTP. | RF-INT-02, critério 9.3 |
| 6 | Carga | Script a 1.000 msg/s com a latência acompanhada no Grafana. | RNF-01, RNF-02 |

**Sobre as 72 horas de desconexão:** na demonstração o corte dura poucos minutos. As 72 h exigidas são comprovadas por um teste automatizado ([testes-sistema/desconexao](testes-sistema/desconexao)) que injeta mensagens com timestamps retroativos e verifica que não houve perda nem duplicação.

### Critérios de aceite do MVP (seção 9.3 do documento)

- Um projeto urbano e um rural integrados; o rural com nó de borda.
- Teste de desconexão de 72 h sem perda nem duplicação após a reconexão.
- Um domínio novo criado só por configuração (RNF-08).
- Integração demonstrada em pelo menos três linguagens.
- Teste de carga comprovando RNF-01 e RNF-02.

## Plano de construção

Entrega na sexta-feira, 23/10/2026, à noite. As funcionalidades congelam por volta das 18h; o restante do tempo é para documentação e ensaio.

- [x] **Base:** estrutura, contratos (JSON Schema, AsyncAPI, OpenAPI), Compose da central e da borda, CI que valida os contratos.
- [x] **Núcleo central:** catálogo e cadastro com `tenant_id`, token por dispositivo, pipeline de ingestão por HTTP e MQTT, último estado, `/api/v1/ingestao` e `/api/v1/ingestao/lote`, paginação padronizada.
- [x] **Regras e alarmes:** ações por Strategy (alarme, notificar em log, comando, webhook, publicar em tópico), regras de limite e de janela de tempo, ciclo de vida do alarme, dado atrasado sem alarme.
- [x] **Borda:** fila SQLite, sincronização em lotes com remoção só após confirmação, regra local, teste de desconexão de 72 h.
- [ ] **Integração e demonstração:** simuladores em três linguagens (em contêineres), adaptador urbano, painéis do Grafana, `/metrics`, logs JSON, domínio novo por API.
- [ ] **Fechamento:** rastreabilidade com status e evidências, `docs/arquitetura.md`, README, teste de carga se houver tempo, ensaio da demo do zero.

Se o tempo apertar, são cortados nesta ordem e passam a ser documentados: PostGIS, teste de carga, painéis elaborados, adaptador urbano e cifragem da fila. Não são cortados: o pipeline de ingestão, a borda com sincronização e o teste de desconexão, o domínio novo só por configuração e os simuladores em três linguagens.

## Convenções

- **Contrato primeiro.** O JSON Schema, o AsyncAPI e o OpenAPI são escritos ou ajustados antes do código e validados no CI.
- **Commits rastreáveis.** A mensagem cita o ID do requisito, por exemplo `RF-ING-08: deduplicação por id_mensagem`. A matriz de rastreabilidade usa esses commits como evidência.
- **Idioma.** Campos do contrato, termos de domínio e documentação em português (`id_mensagem`, `grandeza`, `inquilino`).
- **Testes.** pytest, com cobertura mínima de 70% no núcleo (RNF-15). Cada ação do motor de regras tem um teste automatizado (RF-PRO-03).
- **Configuração externa** por variáveis de ambiente. Nenhum segredo no código.
- **Versionamento semântico** para contratos e serviços. Quebra de contrato só em versão MAJOR.
- **ADRs** curtos em [docs/adr](docs/adr) para cada decisão de arquitetura: contexto, alternativas e consequência.

## Como executar

A central e a borda sobem com Docker Compose. Os passos, as portas e o corte de link estão em [infra/README.md](infra/README.md).

Testes e validação, sem instalar Python, Node ou JDK na máquina (tudo em contêiner):

```bash
docker compose -f servico-core/compose.testes.yaml run --rm --build testes
```

```bash
docker run --rm -v "$PWD/contratos:/c" -w /c node:22-alpine npx -y @asyncapi/cli@6.2.1 validate asyncapi.yaml
```

O primeiro comando roda os testes do `servico-core` contra um TimescaleDB descartável, valida os contratos (JSON Schema, exemplos e OpenAPI) e exige cobertura mínima de 70%. O segundo valida o AsyncAPI. O CI ([.github/workflows/ci.yaml](.github/workflows/ci.yaml)) roda os dois, o ruff e o build da imagem a cada push.
