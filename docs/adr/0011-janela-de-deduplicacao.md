# ADR-0011: Janela de deduplicação

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-ING-08, RF-EDG-02, RNF-04

## Contexto

O RF-ING-08 exige que uma mensagem reenviada pela borda com o mesmo `id_mensagem` seja armazenada uma única vez. A borda pode ficar 72 h sem link (RNF-04) e reenviar lotes inteiros depois de uma falha no meio da sincronização. Cada mensagem canônica pode ter várias medidas (campo `medidas`), então uma mensagem vira várias linhas na série temporal.

## Decisão

- Guardar os `id_mensagem` recebidos por **pelo menos 7 dias**, o que cobre as 72 h de desconexão com mais de duas vezes de folga para atrasos e reenvios.
- **Na central:** tabela própria de identificadores recebidos, com `id_mensagem` como chave primária e a hora de recepção. É uma tabela comum, não uma hypertable, porque o TimescaleDB não aceita chave única só no `id_mensagem`; as linhas com mais de 7 dias são apagadas periodicamente. A inserção do identificador e das medidas acontece na mesma transação.
- **Na borda:** a fila só marca um lote como enviado depois da resposta da central. Um reenvio após falha é seguro porque a central deduplica.

## Alternativas consideradas

- **Redis com expiração.** Rápido, mas, se o Redis for reiniciado sem persistência, a janela some e duplicatas passam.
- **Índice único na própria série.** No TimescaleDB, um índice único precisa incluir a coluna de tempo, e cada medida é uma linha. Seria preciso um índice em (`id_mensagem`, `grandeza`, `timestamp`), o que só funciona se os reenvios trouxerem exatamente o mesmo `timestamp` (garantido pelo ADR-0009). Esse índice não tem janela, mas pesa em toda escrita da série. Vale reavaliar depois do teste de carga.
- **Janela de exatamente 72 h.** Sem folga para atrasos maiores.

## Consequências

- O reenvio é idempotente dentro da janela.
- Uma mensagem reenviada depois de 7 dias seria aceita como nova. A limitação deve ficar documentada.
- O volume depende da taxa: a 1.000 msg/s contínuos, 7 dias somam cerca de 605 milhões de identificadores. O teste de carga é curto, mas o tamanho da janela deve ser dimensionado pela taxa esperada de cada instalação.
