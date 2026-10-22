# ADR-0006: Uma imagem, dois ambientes

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-EDG-01, RF-EDG-02, RF-EDG-03

## Contexto

A central e a borda executam ingestão, catálogo e regras. O documento descreve o nó de borda como uma versão reduzida da plataforma que fala o mesmo contrato (seção 3.3) e pede que a mesma imagem sirva à central e à borda (seção 7.3). Manter dois artefatos dobraria o trabalho de build e de teste.

## Decisão

O `servico-core` gera uma única imagem Docker. O papel de cada instância é definido por variáveis de ambiente: o papel (central ou borda), o banco e, na borda, o endereço da central para a sincronização. Os nomes das variáveis serão definidos no esqueleto do serviço.

- **Central:** PostgreSQL com TimescaleDB, com séries, catálogo e último estado no mesmo banco ([ADR-0017](0017-ultimo-estado-no-postgresql.md)).
- **Borda:** ingestão local por MQTT e HTTP (RF-EDG-01), SQLite cifrado com SQLCipher para a fila e para a cópia local do catálogo, e sincronização em lotes com a central por `POST /api/v1/ingestao/lote` (RF-EDG-02).

Cada ambiente tem seu Compose: `infra/central/compose.yaml` e `infra/borda/compose.yaml`.

## Alternativas consideradas

- **Uma imagem por ambiente.** Imagens menores e sob medida, mas dois pipelines de build e risco de as versões divergirem.
- **Borda sem núcleo, só com um bridge MQTT para a central.** Mais simples, mas não executa regra local (RF-EDG-03) nem controla a fila durante a desconexão.

## Consequências

- O que é testado na central é exatamente o que roda na borda.
- A imagem carrega os drivers dos dois bancos, e o SQLCipher exige biblioteca nativa, o que complica o build.
- Se a borda for um Raspberry Pi, a imagem precisa ser multi-arquitetura (amd64 e arm64), gerada com `docker buildx` no CI.
