# Matriz de rastreabilidade

Liga cada requisito do Documento de Requisitos v2.0 ([requisitos.md](requisitos.md)) ao seu status e à evidência de que foi atendido.

> **Pendente:** a lista abaixo foi montada a partir do briefing do projeto, antes de o documento de requisitos estar no repositório. Quando `docs/requisitos.md` chegar, conferir se todos os requisitos Essenciais estão aqui e preencher a coluna **Descrição**.

## Legenda

**Tratamento previsto:** o que se planeja fazer com o requisito.

- **implementar**: implementado de verdade, com testes.
- **simplificar**: implementado numa versão reduzida; a simplificação fica descrita nas observações.
- **documentar**: não implementado; a justificativa fica descrita (no ADR ou em `arquitetura.md`).

**Status:** `pendente` → `implementado`, `simplificado` ou `documentado`.

**Evidência:** hash do commit (que cita o ID do requisito), caminho do teste automatizado e/ou ADR.

## Requisitos funcionais Essenciais

### CEN

| ID | Descrição | Tratamento previsto | Status | Evidência | Observações |
|---|---|---|---|---|---|
| RF-CEN-01 | | implementar | pendente | | |
| RF-CEN-02 | | implementar | pendente | | |
| RF-CEN-03 | | implementar | pendente | | |

### ING

| ID | Descrição | Tratamento previsto | Status | Evidência | Observações |
|---|---|---|---|---|---|
| RF-ING-01 | | implementar | pendente | | |
| RF-ING-02 | | implementar | pendente | | |
| RF-ING-03 | | implementar | pendente | | |
| RF-ING-04 | | implementar | pendente | | Regras só avaliam dado "atual", para não gerar alarme com dado velho (ADR de dados atrasados). |
| RF-ING-06 | | implementar | pendente | | |
| RF-ING-08 | | implementar | pendente | | Deduplicação por `id_mensagem` (Idempotent Receiver); janela de pelo menos 7 dias (ADR). |

### EDG

| ID | Descrição | Tratamento previsto | Status | Evidência | Observações |
|---|---|---|---|---|---|
| RF-EDG-01 | | implementar | pendente | | |
| RF-EDG-02 | | implementar | pendente | | |

### DIS

| ID | Descrição | Tratamento previsto | Status | Evidência | Observações |
|---|---|---|---|---|---|
| RF-DIS-01 | | implementar | pendente | | |
| RF-DIS-02 | | simplificar | pendente | | A borda só aplica revogações novas de credencial após reconectar (ADR). |
| RF-DIS-06 | | implementar | pendente | | Terceiro estado "desconhecido" para dispositivos atrás de borda sem sincronizar (ADR). |

### PRO

| ID | Descrição | Tratamento previsto | Status | Evidência | Observações |
|---|---|---|---|---|---|
| RF-PRO-01 | | implementar | pendente | | |
| RF-PRO-02 | | implementar | pendente | | No MVP, "área" é filtro por identificador; a condição geométrica depende de RF-CEN-04 (fase 2). |
| RF-PRO-03 | | implementar | pendente | | Cada ação do motor de regras tem um teste automatizado. |
| RF-PRO-05 | | implementar | pendente | | Depende de regra local na borda (RF-EDG-03); ver inconsistências. |

### DAD

| ID | Descrição | Tratamento previsto | Status | Evidência | Observações |
|---|---|---|---|---|---|
| RF-DAD-01 | | implementar | pendente | | |
| RF-DAD-02 | | implementar | pendente | | |
| RF-DAD-05 | | simplificar | pendente | | |
| RF-DAD-06 | | documentar | pendente | | Auditoria completa fica fora do escopo; justificar. |

### APP

| ID | Descrição | Tratamento previsto | Status | Evidência | Observações |
|---|---|---|---|---|---|
| RF-APP-01 | | implementar | pendente | | |
| RF-APP-07 | | implementar | pendente | | |

### INT

| ID | Descrição | Tratamento previsto | Status | Evidência | Observações |
|---|---|---|---|---|---|
| RF-INT-01 | | implementar | pendente | | |
| RF-INT-02 | | implementar | pendente | | |
| RF-INT-03 | | implementar | pendente | | |

### SEG

| ID | Descrição | Tratamento previsto | Status | Evidência | Observações |
|---|---|---|---|---|---|
| RF-SEG-01 | | simplificar | pendente | | |
| RF-SEG-02 | | simplificar | pendente | | |
| RF-SEG-03 | | simplificar | pendente | | |
| RF-SEG-04 | | simplificar | pendente | | |
| RF-SEG-05 | | simplificar | pendente | | SQLCipher na fila da borda; o local da chave fica em ADR (no mesmo disco não cumpre o critério). |

Simplificações previstas para o grupo SEG (associar a cada ID quando o documento estiver disponível):

- Keycloak com TOTP para o administrador.
- Token por dispositivo em vez de certificado X.509.
- `tenant_id` com row-level security no PostgreSQL.
- ACL de tópicos no Mosquitto.
- SQLCipher na fila da borda.

### OBS

| ID | Descrição | Tratamento previsto | Status | Evidência | Observações |
|---|---|---|---|---|---|
| RF-OBS-01 | | simplificar | pendente | | |
| RF-OBS-02 | | simplificar | pendente | | |

Simplificação prevista para o grupo OBS: endpoint `/metrics` (Prometheus) e logs em JSON com `correlation_id` igual ao `id_mensagem`.

## Requisitos não funcionais citados no briefing

Prioridade a confirmar no documento de requisitos.

| ID | Descrição | Tratamento previsto | Status | Evidência | Observações |
|---|---|---|---|---|---|
| RNF-01 | | implementar até 1.000 msg/s; documentar 10.000 msg/s | pendente | | Teste de carga em `testes-sistema/carga`. |
| RNF-02 | | implementar | pendente | | Latência medida no teste de carga e exibida no Grafana. |
| RNF-07 | | implementar WAL; documentar hardware | pendente | | SSD em vez de cartão SD no Raspberry Pi; SQLite em modo WAL (ADR). |
| RNF-08 | | implementar | pendente | | Neutralidade de cenário; comprovada pelo UC-06 ao vivo. |
| RNF-15 | | implementar | pendente | | Cobertura mínima de 70% no núcleo, medida no CI. |
| RNF-18 | | documentar | pendente | | Backup e RTO ficam fora do escopo; justificar. |

## Requisitos fora do Essencial que entram no escopo

| ID | Prioridade no documento | Tratamento previsto | Status | Evidência | Observações |
|---|---|---|---|---|---|
| RF-EDG-03 | Importante | simplificar | pendente | | Regra local simples na borda já no MVP; necessária para UC-01 e RF-PRO-05. |
| RF-CEN-04 | Importante | documentar | pendente | | Desenho de áreas e consultas espaciais ficam para a fase 2; no MVP, área é identificador. |
| RF-APP-05 | a confirmar | simplificar | pendente | | SMS enviado pela central por provedor; SMS direto da borda com modem GSM fica como evolução (ADR). |

## Casos de uso demonstrados

| UC | Passo da demo | Status | Evidência |
|---|---|---|---|
| UC-01 | 2. Rural com borda | pendente | |
| UC-02 | 2. Rural com borda | pendente | |
| UC-03 | 4. Urbano nível 2 | pendente | |
| UC-06 | 1. Domínio novo ao vivo | pendente | |

## Critérios de aceite do MVP (seção 9.3)

| Critério | Status | Evidência |
|---|---|---|
| Um projeto urbano e um rural integrados; o rural com nó de borda | pendente | |
| Teste de desconexão de 72 h sem perda nem duplicação após a reconexão | pendente | |
| Um domínio novo criado só por configuração (RNF-08) | pendente | |
| Integração demonstrada em pelo menos três linguagens | pendente | |
| Teste de carga comprovando RNF-01 e RNF-02 | pendente | |

## Inconsistências do documento original

1. **Regra local na borda.** UC-01 e RF-PRO-05 dependem de regras locais na borda (RF-EDG-03) e de desenho de áreas (RF-CEN-04), que o documento marca como "Importante" (fase 2), enquanto o MVP promete o caso rural com borda. **Decisão:** implementar uma regra local simples já no MVP.
2. **Condição por área geográfica.** RF-PRO-02 (Essencial) inclui condição por área geográfica, mas as consultas espaciais (RF-CEN-04) são fase 2. **Decisão:** no MVP, "área" é filtro por identificador; a geometria fica para depois.

## Decisões em aberto (ADRs a escrever)

| # | Decisão | Requisito | Recomendação | ADR |
|---|---|---|---|---|
| 1 | Relógio da borda | | Borda carimba a hora de recepção quando o dispositivo não envia `timestamp` confiável; hora mantida por NTP ou GPS quando possível. | |
| 2 | Online/offline com borda sem sincronizar | RF-DIS-06 | Terceiro estado "desconhecido". | |
| 3 | Janela de deduplicação | RF-ING-08 | Guardar `id_mensagem` por pelo menos 7 dias. | |
| 4 | Envio de SMS | RF-APP-05 | Pela central, via provedor; modem GSM na borda como evolução. | |
| 5 | Dados atrasados e agregados | RF-ING-04 | Continuous aggregates do Timescale; regras só avaliam dado atual. | |
| 6 | Chave do SQLCipher na borda | RF-SEG-05 | A definir (chave no mesmo disco não cumpre o critério). | |
| 7 | Revogação de credencial na borda | RF-DIS-02 | Lista de revogação sincronizada, aplicada após reconectar; documentar a limitação. | |
| 8 | Energia | RNF-07 | SSD em vez de cartão SD; SQLite em modo WAL. | |
