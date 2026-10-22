# ADR-0017: Último estado em tabela do PostgreSQL

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-DAD-02, RF-ING-04

## Contexto

O RF-DAD-02 pede o último valor de cada grandeza de cada dispositivo, disponível sem consultar o histórico. O documento sugere Redis (seção 9.1). O prazo do trabalho é de um dia ([ADR-0007](0007-infraestrutura-aberta.md)).

## Decisão

Guardar o último estado numa tabela comum, com chave (`dispositivo`, `grandeza`), atualizada pela etapa de persistência do pipeline com um upsert condicional: a linha só muda se o `timestamp` da medição nova for maior que o armazenado. Na borda, a mesma tabela existe no SQLite, que também aceita upsert com condição.

## Alternativas consideradas

- **Redis** (sugerido pelo documento). Leituras mais rápidas, mas é mais um serviço, e a atualização condicional exigiria um script Lua.
- **Consultar a última linha da série.** Viola o critério ("sem consultar o histórico") e fica lento com o volume.

## Consequências

- Um serviço a menos na central.
- A regra "dado atrasado não sobrescreve o atual" ([ADR-0008](0008-pipeline-de-ingestao.md)) fica numa única instrução SQL.
- Sob carga, as linhas mais atualizadas concentram escrita. É aceitável para 1.000 msg/s e deve ser observado no teste de carga.
- **Evolução:** Redis atrás da mesma porta de repositório, sem mudar o domínio.
