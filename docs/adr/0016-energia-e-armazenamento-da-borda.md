# ADR-0016: Energia e armazenamento da borda

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RNF-07, RNF-10, RNF-06, RF-EDG-01

## Contexto

O RNF-07 exige que uma queda de energia não corrompa a fila nem a configuração da borda (escrita transacional). O RNF-10 exige que nenhuma mensagem confirmada ao emissor seja perdida. Bordas rurais costumam ter energia instável, e o hardware de referência é um Raspberry Pi 5 (RNF-06).

## Decisão

- **Armazenamento:** recomendar SSD (NVMe no Raspberry Pi 5 ou USB 3) em vez de cartão SD.
- **SQLite:** modo WAL com `synchronous=FULL`, para que cada transação confirmada sobreviva a uma queda de energia. As escritas são agrupadas em transações, para diluir o custo do `fsync`.
- **Fila:** uma mensagem só sai da fila depois da confirmação da central (store-and-forward, entrega pelo menos uma vez). As duplicatas são resolvidas pela deduplicação (ADR-0011).
- **Mosquitto:** persistência ligada, com intervalo de gravação curto. O broker confirma a mensagem (PUBACK) antes de o `servico-core` gravá-la. Se o broker cair nesse intervalo, mensagens confirmadas podem se perder, então o intervalo deve ser medido e ajustado nos testes.

## Alternativas consideradas

- **Cartão SD.** Barato, mas corrompe com facilidade em quedas de energia e se desgasta com escrita contínua.
- **Diário de rollback, o padrão do SQLite.** Também é transacional, mas faz mais `fsync` e é mais lento que o WAL.
- **`synchronous=NORMAL`.** Mais rápido e sem risco de corrupção em WAL, mas pode perder as últimas transações numa queda de energia, o que viola o RNF-10.

## Consequências

- A fila e a configuração resistem a quedas de energia.
- O SSD é custo extra de hardware.
- Sem hardware real, a robustez é verificada só em teste. `docker kill` simula a queda do processo, mas não a perda do cache de disco, e essa diferença deve ficar explícita na documentação.
