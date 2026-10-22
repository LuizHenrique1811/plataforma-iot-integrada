# ADR-0008: Pipeline de ingestão

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-ING-01, RF-ING-02, RF-ING-03, RF-ING-04, RF-ING-06, RF-ING-08, RF-PRO-01, RF-OBS-02, RNF-10

## Contexto

As mensagens chegam por MQTT (RF-ING-01), por HTTP (RF-ING-02) e em lotes vindos da borda (RF-ING-03). Podem chegar duplicadas (reenvio após falha), fora de ordem e com atraso de até 72 h. Mensagens inválidas não podem sumir em silêncio, e nenhuma mensagem confirmada ao emissor pode ser perdida (RNF-10). O documento descreve o pipeline como Pipes and Filters (figura 5.1).

## Decisão

Toda mensagem passa pelo mesmo pipeline, qualquer que seja a entrada:

1. **Autenticar** a origem.
2. **Validar** contra o JSON Schema da versão declarada no campo `versao` (RF-ING-06).
3. **Deduplicar** por `id_mensagem` (Idempotent Receiver, RF-ING-08).
4. **Enriquecer** com inquilino, perfil, domínio, local e área do cadastro, normalizando unidades (RF-PRO-01).
5. **Ordenar** pelo `timestamp` da medição (RF-ING-04).
6. **Persistir** na série temporal e no último estado.

Mensagens rejeitadas em qualquer etapa vão para a DLQ (Dead Letter Channel), com o motivo e a etapa. Os logs usam o `id_mensagem` como `correlation_id`, o que permite seguir uma mensagem da borda à central (RF-OBS-02).

## Alternativas consideradas

- **Um único handler que valida e persiste.** Mais simples, mas mistura responsabilidades e dificulta a DLQ com motivo e os testes por etapa.
- **Broker de streaming entre as etapas (Kafka).** Escala bem, mas é pesado demais para a borda e para o prazo.

## Consequências

- Cada etapa é testada isoladamente.
- Uma entrada nova, como o adaptador urbano, só precisa produzir a mensagem canônica.
- As respostas seguem os critérios do documento: HTTP devolve 202 para mensagem válida e 400 com a lista de erros para inválida (RF-ING-02); o lote devolve o resultado de cada mensagem (RF-ING-03).
- "Ordenar" num fluxo contínuo significa gravar a medição na posição do seu `timestamp`, não segurar mensagens num buffer. Dados atrasados entram no lugar certo da série (ADR-0013).
- O último estado só é atualizado se a medição for mais nova que a já armazenada; assim, um dado atrasado não sobrescreve o atual.
- A deduplicação precisa de armazenamento com janela de retenção (ADR-0011).
- Para cumprir o RNF-10, a confirmação ao emissor (202 no HTTP, resultado do lote) só sai depois da escrita durável. No MQTT, quem confirma é o broker, então a durabilidade depende também da persistência do Mosquitto (ADR-0016).
