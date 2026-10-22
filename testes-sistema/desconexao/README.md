# Teste de desconexão de 72 h

Critério de aceite do MVP (seção 9.3): "link da borda cortado por 72 h sem perda nem duplicação de dados após a reconexão". Requisitos cobertos: RF-EDG-01, RF-EDG-02, RF-EDG-03, RF-ING-08, RF-PRO-05, RNF-04 e RNF-07.

**As 72 h não são esperadas em tempo real.** O teste envia à borda 72 h de leituras com timestamps retroativos (três sensores, uma leitura a cada 10 minutos, 1.296 mensagens), como elas chegariam de sensores durante um corte de 72 h. Na demonstração ao vivo, o corte dura poucos minutos; este teste é a prova das 72 h.

## O que o teste faz

1. Monta a central e a borda pela mesma raiz de composição do serviço real (`principal.montar_servico`): central com PostgreSQL (ou em memória, sem `BANCO_URL_TESTE`) e borda com SQLite cifrado.
2. Corta o link e envia à borda a primeira metade das 72 h, mais 20 reenvios de mensagens já recebidas.
3. Reinicia a borda no meio do corte (queda de energia) e confere que a fila cifrada continua no disco.
4. Envia a segunda metade; a última leitura de um sensor, atual e abaixo de 20%, dispara a regra local de irrigação sem link.
5. Religa o link, mas faz a resposta do primeiro lote se perder depois de a central gravar; a borda reenvia o lote.
6. Confere na central, pela API:
   - 432 medições por sensor, exatamente uma vez cada, na ordem e na hora da medição;
   - o campo `via` com a borda;
   - o alarme da regra local com origem `borda` e o horário em que ocorreu;
   - nenhuma mensagem rejeitada.

## Como rodar

Junto com os demais testes, em contêiner (TimescaleDB descartável):

```bash
MSYS_NO_PATHCONV=1 docker compose -f servico-core/compose.testes.yaml run --rm --build testes pytest /testes-sistema/desconexao -q -s
```

`MSYS_NO_PATHCONV=1` só é necessário no Git Bash do Windows. O CI roda o mesmo teste a cada push.
