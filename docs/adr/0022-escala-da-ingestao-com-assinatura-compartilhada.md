# ADR-0022: Escala da ingestão com processos e assinatura compartilhada

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RNF-01, RNF-02, RNF-09, RNF-10, critério de aceite 9.3 (teste de carga)

## Contexto

O RNF-01 pede 1.000 mensagens/s num servidor central. Na primeira medição ([testes-sistema/carga](../../testes-sistema/carga/README.md)), um processo do `servico-core` sustentou só 161 msg/s:

- o processo estava limitado pela CPU, com o GIL do Python disputado por 8 threads;
- o banco tinha folga, e o fsync não era o gargalo;
- cada mensagem custava várias idas e voltas ao banco, e quase metade da CPU era tempo de sistema.

O núcleo já foi pensado para escalar na horizontal (RNF-09): os processos não guardam estado, e o consumidor MQTT aceita uma assinatura compartilhada (`$share/<grupo>/...`).

## Decisão

1. **Vários processos no mesmo servidor, num grupo de assinatura compartilhada.**
   - O `servico-core` principal entra no grupo `ingestao`.
   - O perfil `escala` do Compose da central acrescenta 9 réplicas, cada uma com seu `MQTT_CLIENTE`, sem portas publicadas: `docker compose --profile escala up -d`.
   - Sem o perfil, a central continua com um processo, o que basta para a demonstração.
2. **Réplicas com sessão limpa; o principal com sessão persistente.** O Mosquitto continua entregando a parte do grupo a uma sessão persistente desconectada: numa medição com 5 de 6 processos parados, 5/6 das mensagens ficaram presas até eles voltarem.
   - Por isso as réplicas usam sessão limpa (`MQTT_SESSAO_PERSISTENTE=0`): parada, a réplica sai do grupo.
   - Ao parar, a réplica cancela a assinatura, processa o que já estava a caminho e só então desconecta.
   - O principal mantém a sessão persistente, que guarda as mensagens se todos os processos caírem.
3. **Só o principal verifica ausência de dados.** As réplicas usam `VERIFICACAO_AUSENCIA_S=0`, para a mesma ausência não ser notificada várias vezes.
4. **3 threads de ingestão por processo** (padrão de `MQTT_TRABALHADORES`). Mais threads só disputam o GIL; medido: +17% de vazão com 3 em vez de 8.
5. **Menos idas e voltas ao banco por mensagem, sem mudar a semântica:**
   - conexões do pool em autocommit: consulta avulsa sem transação nem COMMIT extra; as gravações compostas usam `transaction()`;
   - cache, no pipeline, dos perfis de dispositivo, que não mudam depois de criados (o contrato não tem rota para alterá-los);
   - modo pipeline do psycopg na gravação. O SQLite da borda aceita a mesma chamada e não faz nada com ela.
6. **PostgreSQL pelo socket Unix.** O banco e os processos estão no mesmo servidor, então os processos montam o diretório do socket num volume compartilhado e usam `BANCO_URL=...@/iot?host=/var/run/postgresql`. Medido no ensaio, nas mesmas condições: a vazão foi de cerca de 890 msg/s por TCP para cerca de 1.000 msg/s pelo socket. O Grafana continua por TCP.

## Alternativas consideradas

- **Gravar em micro-lotes** (uma transação para dezenas de mensagens). É o que reduz de verdade o custo por mensagem e será necessário para as 10.000 msg/s. Fica como evolução: muda o pipeline, que hoje grava cada mensagem por conta própria, e o prazo não comporta essa mudança com segurança.
- **`synchronous_commit = off` no PostgreSQL.** Medido: quase não mudou a vazão. Além disso, uma mensagem já confirmada poderia se perder numa queda (RNF-10).
- **`uvicorn --workers`.** Os processos dividiriam o mesmo `MQTT_CLIENTE`, e o broker desconectaria um a cada conexão do outro.
- **Réplicas com sessão persistente e identificador fixo.** Funcionam enquanto todas estão no ar, mas a réplica parada segura a sua parte das mensagens (o problema da decisão 2).

## Consequências

- **RNF-01 cumprido nesta máquina:** 1.000 msg/s sustentadas com 10 processos, sem perdas nem duplicatas, com p95 de 0,09 s a 0,40 s até a persistência e de 0,40 s até o disparo da regra.
  - A folga é pequena: o teto medido vai de 1.020 a 1.050 msg/s, conforme o que mais roda no notebook. Com o notebook carregado e o banco por TCP, duas execuções ficaram em 884 e 903 msg/s.
- **Socket local sem senha.** A imagem do TimescaleDB aceita conexões pelo socket com a regra `trust` do `pg_hba.conf`. Só os contêineres que montam o volume do socket chegam a ele, e são os do `servico-core`. Num ambiente real, a regra local deve exigir senha (`POSTGRES_INITDB_ARGS=--auth-local=scram-sha-256`).
- **Banco e processos no mesmo servidor.** Para separar o banco em outra máquina, basta voltar o `BANCO_URL` para TCP, com a perda de desempenho medida.
- **Uma réplica que cai sem parar direito** (queda do processo, não `docker compose stop`) perde as mensagens que já tinha recebido e ainda não tinha confirmado: no máximo a janela de envio do broker, 20 mensagens por réplica. O principal, com sessão persistente, não tem essa perda. É uma exceção ao RNF-10 restrita às réplicas de carga.
- **Ordem:** mensagens de um mesmo dispositivo podem ser processadas fora de ordem entre processos, como já acontecia entre threads. O armazenamento ordena pelo horário da medição e o último estado só avança com medição mais nova, então o resultado não muda.
- **10.000 msg/s ficam documentadas:** exigem micro-lotes, mais servidores e réplicas do banco.
