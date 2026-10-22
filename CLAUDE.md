# Plataforma IoT Integrada: contexto do projeto

Trabalho de disciplina (UniEVANGÉLICA, Internet das Coisas). O objetivo é implementar a plataforma descrita no Documento de Requisitos v2.0. Coloque o documento original em `docs/requisitos.md` e trate-o como fonte da verdade. Os IDs citados aqui (RF-XXX-nn, RNF-nn, UC-nn) são os do documento.

## Ideias centrais (nunca violar)

1. **Independência de linguagem.** Não existe biblioteca obrigatória. A integração é por contratos abertos: JSON Schema, AsyncAPI 3, OpenAPI 3, GeoJSON. Qualquer coisa que fale MQTT ou HTTP e monte um JSON integra.
2. **Neutralidade de cenário (RNF-08).** O núcleo não conhece "praça", "talhão" ou "silo". Domínios, perfis de dispositivo, locais e regras são **dados configuráveis** (padrão Type Object), nunca constantes ou classes no código.
3. **Operação desconectada.** O nó de borda guarda dados numa fila persistente, executa regras locais e sincroniza em lotes quando o link volta. Isso exige: deduplicação por `id_mensagem`, ordenação pelo `timestamp` da medição e aceitação de dados atrasados.

## Decisões já tomadas

- **Monorepo** chamado `plataforma-iot-integrada`.
- **Linguagem do núcleo:** Python 3.12 + FastAPI (pode ser trocada, pois os serviços só se falam por contrato).
- **Infraestrutura aberta:** Mosquitto (MQTT), PostgreSQL + TimescaleDB + PostGIS (séries e geometrias), Redis (último estado), Grafana (painéis), Keycloak (OIDC, papéis, MFA), Prometheus (métricas).
- **Uma imagem Docker, dois ambientes.** O `servico-core` gera uma única imagem. A central e a borda são dois Compose que a usam com configuração diferente (PostgreSQL na central, SQLite cifrado na borda).
- **Arquitetura hexagonal** em cada serviço: `dominio/` não importa FastAPI, drivers MQTT nem banco. Tudo entra e sai por `portas/`, implementadas em `adaptadores/`.
- **Escopo do trabalho:** todos os requisitos Essenciais, cada um marcado como *implementado*, *simplificado* ou *documentado* (com justificativa), mais a regra local na borda (RF-EDG-03) e o domínio novo ao vivo (UC-06).
- **Hardware:** não obrigatório. Dois ambientes Docker e simuladores bastam.

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
├── simuladores/            # critério das 3 linguagens
│   ├── python/
│   ├── javascript/
│   └── java/
├── infra/
│   ├── central/            # compose: Mosquitto, Timescale, Grafana, Keycloak
│   ├── borda/              # compose: Mosquitto, servico-core com SQLite
│   ├── grafana/            # painéis provisionados
│   └── keycloak/           # realm exportado
├── testes-sistema/
│   ├── desconexao/         # injeta 72 h de mensagens retroativas
│   └── carga/              # 1.000 msg/s
├── docs/
│   ├── requisitos.md
│   ├── arquitetura.md
│   ├── rastreabilidade.md  # requisito -> status -> evidência
│   └── adr/
├── .github/workflows/      # CI: testes, validação de contratos
└── README.md
```

## Convenções

- **Contrato primeiro.** Escreva ou ajuste o JSON Schema/AsyncAPI/OpenAPI antes do código e valide no CI.
- **Commits rastreáveis.** Cite o ID do requisito na mensagem, por exemplo `RF-ING-08: deduplicação por id_mensagem`. A matriz de rastreabilidade aponta para esses commits como evidência.
- **Idioma.** Campos do contrato e termos de domínio em português, como no documento (`id_mensagem`, `grandeza`, `inquilino`). Documentação em português.
- **Testes.** pytest, cobertura mínima de 70% no núcleo (RNF-15). Cada ação do motor de regras tem um teste automatizado (RF-PRO-03).
- **Configuração externa** por variáveis de ambiente (Twelve-Factor). Nenhum segredo no código.
- **Versionamento semântico** para contratos e serviços. Quebra de contrato só em versão MAJOR.
- **ADRs** curtos em `docs/adr/` para cada decisão de arquitetura (contexto, alternativas, consequência).

## Tratamento dos requisitos Essenciais

| Tratamento | Requisitos | Como |
|---|---|---|
| Implementar de verdade | CEN-01/02/03, ING-01/02/03/04/06/08, EDG-01/02, DIS-01/06, PRO-01/02/03/05, DAD-01/02, APP-01/07, INT-01/02/03 | Catálogo, pipeline de ingestão, borda com sincronização, regras e alarmes |
| Simplificar | SEG-01 a 05, DIS-02, DAD-05, OBS-01/02 | Keycloak com TOTP para o administrador; token por dispositivo em vez de X.509; `tenant_id` com row-level security; ACL de tópicos no Mosquitto; SQLCipher na fila da borda; `/metrics` e logs JSON com `correlation_id` igual ao `id_mensagem` |
| Só documentar | DAD-06 (auditoria completa), RNF-18 (backup e RTO), RNF-01 em 10.000 msg/s | Descrever o que ficou de fora, com justificativa |

Pipeline de ingestão (Pipes and Filters): autenticar, validar contra o JSON Schema da versão, deduplicar por `id_mensagem` (Idempotent Receiver), enriquecer com perfil/domínio/local/área, ordenar pelo `timestamp` da medição e persistir. Mensagens rejeitadas vão para a DLQ com o motivo (Dead Letter Channel).

## Decisões em aberto (virar ADR, com a recomendação)

1. **Relógio da borda.** Dispositivos sem RTC e borda sem internet: a borda carimba a hora de recepção quando o dispositivo não envia `timestamp` confiável, e mantém a hora por NTP ou GPS quando possível.
2. **Online/offline com borda sem sincronizar.** Criar um terceiro estado, "desconhecido", em vez de marcar todos os sensores da fazenda como offline (RF-DIS-06).
3. **Janela de deduplicação.** Guardar os `id_mensagem` por pelo menos 7 dias, o que cobre as 72 h de desconexão com folga.
4. **SMS (RF-APP-05).** No trabalho, enviar pela central por um provedor de SMS. SMS direto da borda com modem GSM fica como evolução.
5. **Dados atrasados e agregados.** Usar continuous aggregates do Timescale, que recalculam a janela afetada. Regras só avaliam dado "atual" (diferença pequena entre chegada e medição), para não gerar alarme com dado velho (RF-ING-04).
6. **Segurança da fila da borda (RF-SEG-05).** Definir onde fica a chave do SQLCipher; no mesmo disco não cumpre o critério.
7. **Revogação de credencial na borda (RF-DIS-02).** A borda mantém uma lista de revogação sincronizada e só aplica as revogações novas após reconectar. Documentar essa limitação.
8. **Energia (RNF-07).** Recomendar SSD em vez de cartão SD se rodar em Raspberry Pi; escrita transacional no SQLite (WAL).

## Inconsistências do documento original (para tratar na rastreabilidade)

- Os casos de uso UC-01 e RF-PRO-05 dependem de regras locais na borda (RF-EDG-03) e de desenho de áreas (RF-CEN-04), que o documento marca como "Importante" (fase 2), enquanto o MVP promete o caso rural com borda. Decisão: implementar uma regra local simples já no MVP.
- RF-PRO-02 (Essencial) inclui condição por área geográfica, mas consultas espaciais (RF-CEN-04) são fase 2. Decisão: no MVP, "área" é filtro por identificador; geometria fica para depois.

## Ordem de construção (6 semanas, ajustável)

1. Contratos, repositório, Compose, CI, ADRs iniciais, modelo do catálogo.
2. Catálogo e cadastro (CEN, DIS), Keycloak, `tenant_id` e papéis.
3. Pipeline de ingestão central: validação, deduplicação, DLQ, ordenação, séries e último estado.
4. Regras e alarmes (PRO), painéis no Grafana.
5. Borda: fila SQLite, sincronização em lotes, regra local, teste de desconexão.
6. Adaptador urbano, simuladores em 3 linguagens, teste de carga, documentação e ensaio da demo.

Se o prazo apertar, corte primeiro o adaptador urbano e o teste de carga (viram "documentado"). Não cortar: pipeline de ingestão, borda com sincronização e domínio novo ao vivo.

## Roteiro da demonstração (10 a 15 min)

1. Domínio novo ao vivo (UC-06): criar "recursos_hidricos" e um perfil de reservatório, sem tocar no código.
2. Rural com borda (UC-01 e UC-02): simuladores de solo e silo publicam na borda; regra local liga a irrigação.
3. Corte de link: desconectar a borda, continuar gerando dados, religar. Histórico completo, sem duplicatas, na hora da medição. As 72 h reais são simuladas por um teste automatizado com timestamps retroativos, o que deve ficar explícito na documentação.
4. Urbano nível 2 (UC-03): simulador com JSON legado e adaptador em contêiner traduzindo para o canônico, sem reiniciar o núcleo.
5. Três linguagens: simuladores em Python, JavaScript e Java, só com bibliotecas genéricas de MQTT e HTTP.
6. Carga: script a 1.000 msg/s com latência no Grafana (RNF-01 e RNF-02).

## Critérios de aceite do MVP (seção 9.3 do documento)

- Um projeto urbano e um rural integrados; o rural com nó de borda.
- Teste de desconexão de 72 h sem perda nem duplicação após a reconexão.
- Um domínio novo criado só por configuração (RNF-08).
- Integração demonstrada em pelo menos três linguagens.
- Teste de carga comprovando RNF-01 e RNF-02.

## Primeiros passos sugeridos para o Claude Code

1. Criar a árvore de pastas acima e o `README.md` com o roteiro da demo.
2. Escrever os contratos: JSON Schema da mensagem canônica v1.0 (seção 4.4 do documento), AsyncAPI com a convenção de tópicos (seção 4.5) e OpenAPI com os endpoints da seção 4.6.
3. Criar `docs/rastreabilidade.md` com todos os requisitos Essenciais, cada um com status e evidência vazia.
4. Criar `infra/central/compose.yaml` e `infra/borda/compose.yaml`.
5. Implementar o esqueleto do `servico-core` (hexagonal) com `POST /api/v1/ingestao`, validação por JSON Schema, deduplicação e DLQ, com testes.
6. Configurar o CI para validar os contratos e rodar os testes.
