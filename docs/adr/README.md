# Registro de decisões de arquitetura (ADR)

Cada decisão de arquitetura tem um arquivo curto com contexto, decisão, alternativas e consequências, como pede a seção 7.3 do documento de requisitos.

- **aceito:** decisão em vigor.
- **substituído por ADR-nnnn:** decisão revista; o arquivo antigo é mantido.

| ADR | Decisão | Status | Requisitos |
|---|---|---|---|
| [0001](0001-monorepo.md) | Monorepo | aceito | — |
| [0002](0002-integracao-por-contratos-abertos.md) | Integração por contratos abertos | aceito | RF-INT-01, RF-INT-02, RNF-13 |
| [0003](0003-catalogo-configuravel.md) | Catálogo configurável (Type Object) | aceito | RF-CEN-01/02/03, RNF-08 |
| [0004](0004-python-fastapi-no-nucleo.md) | Python 3.12 e FastAPI no núcleo | aceito | RNF-01, RNF-06, RNF-15 |
| [0005](0005-arquitetura-hexagonal.md) | Arquitetura hexagonal | aceito | RF-PRO-03, RNF-15 |
| [0006](0006-uma-imagem-dois-ambientes.md) | Uma imagem, dois ambientes | aceito | RF-EDG-01/02/03 |
| [0007](0007-infraestrutura-aberta.md) | Infraestrutura aberta e enxuta | aceito | RNF-14, RF-OBS-01 |
| [0008](0008-pipeline-de-ingestao.md) | Pipeline de ingestão | aceito | RF-ING-01/02/03/04/06/08, RF-PRO-01, RF-OBS-02, RNF-10 |
| [0009](0009-relogio-da-borda.md) | Relógio da borda | aceito | RF-ING-04, RF-EDG-02, RF-PRO-05 |
| [0010](0010-estado-desconhecido.md) | Estado "desconhecido" | aceito | RF-DIS-06 |
| [0011](0011-janela-de-deduplicacao.md) | Janela de deduplicação | aceito | RF-ING-08, RF-EDG-02 |
| [0012](0012-sms-pela-central.md) | Envio de SMS pela central | aceito | RF-APP-05 |
| [0013](0013-dados-atrasados-e-agregados.md) | Dados atrasados e agregados | aceito | RF-ING-04, RF-PRO-04 |
| [0014](0014-chave-da-fila-da-borda.md) | Chave de cifragem da fila da borda | aceito | RF-SEG-05 |
| [0015](0015-revogacao-de-credencial-na-borda.md) | Revogação de credencial na borda | aceito | RF-DIS-02 |
| [0016](0016-energia-e-armazenamento-da-borda.md) | Energia e armazenamento da borda | aceito | RNF-07, RNF-10 |
| [0017](0017-ultimo-estado-no-postgresql.md) | Último estado em tabela do PostgreSQL | aceito | RF-DAD-02 |
| [0018](0018-autenticacao-sem-keycloak.md) | Autenticação por token e chave de API, sem Keycloak | aceito | RF-SEG-01/02/03/04, RF-DIS-02 |
| [0019](0019-painel-de-cadastro.md) | Documentação interativa como painel de cadastro | aceito | RF-DIS-01, RF-CEN-01, RF-APP-01 |
