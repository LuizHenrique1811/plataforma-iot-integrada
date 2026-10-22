# Teste de carga: 1.000 msg/s

Critério de aceite do MVP (seção 9.3): "teste de carga comprovando o RNF-01 e o RNF-02". As metas:

- **RNF-01:** sustentar 1.000 mensagens/s num servidor central.
- **RNF-02:** com conexão, p95 da ingestão até a persistência ≤ 2 s e até o disparo de uma regra ≤ 3 s.

O resultado da última execução está em [resultado.md](resultado.md).

## O que o teste faz

O script [carga.py](carga.py) é um cliente externo como qualquer outro: fala MQTT e HTTP e lê o banco só para medir.

1. **Cenário próprio.** Cria pela API o inquilino `carga`, com um domínio, um perfil, um local, 100 sensores, um sensor sentinela e uma regra de limite que publica num tópico do inquilino. Nas execuções seguintes, reaproveita o que já existe.
2. **Carga.** Publica 1.000 mensagens canônicas por segundo durante 60 s, em MQTT QoS 1, alternando entre os 100 sensores. Cada mensagem leva no `timestamp` a hora do envio, com milissegundos.
3. **Regra sob carga.** O sentinela alterna acima e abaixo do limite a cada segundo, e cada subida dispara a regra. O script assina o tópico da regra e mede a hora da chegada menos a hora da medição.
4. **Medição no TimescaleDB:**
   - Latência até a persistência: `persistido_em` menos o horário da medição. Inclui a espera na fila do broker, não só o tempo dentro do serviço.
   - Vazão: mensagens gravadas divididas pelo intervalo entre a primeira e a última gravação.
   - Perdas e duplicatas: cada mensagem publicada aparece exatamente uma vez.
   - DLQ vazia.

O teste é aprovado se nada se perde, nada se duplica, nada vai para a DLQ, a vazão é de pelo menos 98% da taxa pedida e os dois p95 ficam dentro das metas.

## Como rodar

Com a central no ar e as réplicas de ingestão ligadas ([ADR-0022](../../docs/adr/0022-escala-da-ingestao-com-assinatura-compartilhada.md)):

```bash
docker compose -f infra/central/compose.yaml --profile escala up -d --wait
```

```bash
docker compose -f testes-sistema/carga/compose.yaml run --rm --build carga
```

Parâmetros opcionais por variável de ambiente: `TAXA` (msg/s, padrão 1000), `DURACAO_S` (padrão 60) e `DISPOSITIVOS` (padrão 100). Antes, pare os simuladores, para a medição não misturar outro tráfego. Depois do teste, para voltar a um processo só:

```bash
docker compose -f infra/central/compose.yaml --profile escala stop
```

## Ambiente da medição

- **Máquina:** notebook com Intel Core Ultra 5 125H e 15,5 GB de RAM, Windows 11 com Docker Desktop (WSL2), 18 CPUs virtuais e 7,5 GB para os contêineres.
- **Tudo no mesmo servidor**, que é o próprio notebook: Mosquitto, TimescaleDB, o gerador de carga e 10 processos do `servico-core`, cada um com 3 threads de ingestão e um MQTT_CLIENTE próprio.
- **Divisão das mensagens:** os processos compartilham a assinatura `$share/ingestao/...`.
- **Banco:** os processos falam com o PostgreSQL pelo socket Unix, num volume compartilhado. As primeiras medições da tabela abaixo usaram TCP pela rede do Docker.
- **Carga do notebook:** o notebook também rodava navegador, Docker Desktop e outros aplicativos, e isso muda o resultado (ver as medições do ensaio).

## Resultados

| Configuração | Vazão sustentada | p95 envio → persistência | Situação |
|---|---|---|---|
| 1 processo, 8 threads (configuração inicial) | 161 msg/s | crescente (fila acumulando) | reprovado |
| 6 processos, 8 threads | 595 msg/s | crescente | reprovado |
| 6 processos, 8 threads, com autocommit e cache de perfil | 777 msg/s | crescente | reprovado |
| 6 processos, 3 threads | 908 msg/s | 3,7 s | reprovado |
| 8 processos, 3 threads | 952 msg/s | 2,8 s | reprovado |
| **10 processos, 3 threads** | **1.000 msg/s** | **0,09 s a 0,40 s** | **aprovado** |
| 10 processos, 3 threads, a 1.200 msg/s | cerca de 1.050 msg/s | crescente | teto da máquina |

Medições do ensaio da demonstração do zero, num clone novo, com o notebook mais carregado (cerca de 68% de CPU do Windows fora do Docker):

| Configuração | Vazão sustentada | p95 envio → persistência | Situação |
|---|---|---|---|
| 10 processos, banco por TCP | 884 e 903 msg/s (duas execuções) | 7,7 s e 6,2 s | reprovado |
| **10 processos, banco por socket Unix** | **997 msg/s** | **0,53 s** | **aprovado** |
| 10 processos, socket Unix, a 1.200 msg/s | cerca de 1.020 msg/s | crescente | teto da máquina nesse estado |

Na configuração aprovada, sem perdas nem duplicatas, a regra disparou com p95 de 0,40 s (0,60 s no ensaio). Dentro do serviço, do recebimento à gravação, o p95 fica entre 15 e 30 ms; o resto é espera na fila do broker. Cada processo ocupa cerca de 70 MB. O [resultado.md](resultado.md) guarda a última execução registrada.

## O que a medição mostrou

1. **Cada processo é limitado pela CPU, não pelo banco.** Com 10 processos, cada um fica perto de 100% de um núcleo, e o TimescaleDB, em torno de 250% de 18 CPUs. Desligar a confirmação síncrona do PostgreSQL quase não mudou a vazão (739 msg/s contra 694 na mesma configuração), então o fsync não é o gargalo.
2. **Mais threads pioram.** Com o GIL do Python, 8 threads por processo só disputavam a CPU. Com 3 threads, o mesmo número de processos rende 17% mais, e a configuração passou a ter 3 threads como padrão.
3. **O custo está nas idas e voltas ao banco.** Quase metade da CPU de cada processo e do banco era tempo de sistema (rede). Duas mudanças reduziram esse custo, sem mudar a semântica:
   - conexões em autocommit, para uma consulta avulsa não pagar um COMMIT a mais;
   - cache dos perfis, que não mudam depois de criados.

   O modo pipeline do psycopg na gravação junta os comandos da transação, mas o ganho ficou dentro da variação da medição.
4. **Socket Unix em vez de TCP.** Banco e processos estão no mesmo servidor, então a conexão pelo socket Unix evita a pilha de rede do Docker. Nas mesmas condições, a vazão subiu de cerca de 890 para cerca de 1.000 msg/s (+13% a 15%).
5. **Escala horizontal funciona como previsto (RNF-09).** Os processos não guardam estado e dividem a assinatura MQTT. Somar processos aumentou a vazão quase em proporção, até o teto da máquina: de 1.020 a 1.050 msg/s, conforme a carga do notebook.

## Limitações e próximos passos

- **Margem pequena.** O teto de 1.020 a 1.050 msg/s deixa de 2% a 5% de folga sobre a meta, e o resultado depende do que mais roda no notebook. Para a demonstração ao vivo, é mais seguro mostrar o resultado registrado ou rodar numa taxa menor (por exemplo, `TAXA=600`). Num servidor dedicado, sem o Windows e o Docker Desktop no meio, a folga tende a ser maior, mas isso não foi medido.
- **10.000 msg/s (segunda meta do RNF-01) só documentado.** No ritmo atual, de cerca de 100 msg/s por processo, seriam necessários uns 100 processos. O próximo passo é gravar em micro-lotes, com uma transação e um `executemany` para dezenas de mensagens, como o `/api/v1/ingestao/lote` já permite receber. Junto com mais servidores e mais réplicas do banco, isso reduz o custo por mensagem.
- **Medido por MQTT.** A ingestão por HTTP passa pelo mesmo pipeline, mas não foi medida sob carga.
