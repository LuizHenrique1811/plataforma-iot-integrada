# Roteiro da apresentação

Roteiro para 12 a 15 minutos de demonstração. Os tempos de espera foram medidos no ensaio de 22/10 no notebook da apresentação. Os comandos rodam na raiz do repositório.

## Na véspera: deixar o ambiente zerado

Apaga os dados das demonstrações anteriores e prepara os cenários rural e urbano. Levou 1 minuto no ensaio.

```bash
docker compose -f simuladores/compose.yaml down
```

```bash
docker compose -f adaptadores-plugaveis/ar-urbano/compose.yaml down
```

```bash
docker compose -f infra/borda/compose.yaml down -v
```

```bash
docker compose -f infra/central/compose.yaml --profile escala down -v
```

```bash
docker compose -f infra/central/compose.yaml up -d --build --wait
```

```bash
docker compose -f infra/borda/compose.yaml up -d --build --wait
```

```bash
docker compose -f demo/compose.yaml run --rm preparar
```

```bash
docker compose -f infra/borda/compose.yaml up -d --wait
```

O `preparar` emite uma chave nova para a borda, porque o banco foi recriado. O último comando aplica essa chave. Confira em <http://localhost:8000/saude> e <http://localhost:8001/saude>.

## Antes de começar (5 minutos antes)

- **Notebook:** na tomada, com o modo de energia em "Melhor desempenho". Feche abas pesadas do navegador: o teste de carga depende da CPU livre.
- **Docker Desktop** aberto, com central e borda no ar. Os simuladores devem estar parados.
- **Abas do navegador:**
  - <http://localhost:8000/docs>: Swagger da central;
  - <http://localhost:3000>: Grafana, no painel "Plataforma IoT - visão geral", com o intervalo "Last 15 minutes" e atualização a cada 5 s;
  - [docs/rastreabilidade.md](rastreabilidade.md) e [testes-sistema/carga/resultado.md](../testes-sistema/carga/resultado.md) no GitHub.
- **Dois terminais:** um para os comandos e outro já mostrando o log da borda.

```bash
docker logs -f iot-borda-servico-core-1
```

**No PowerShell**, variáveis vão antes do comando assim: `$env:TAXA=600; docker compose ...`. No Git Bash, `TAXA=600 docker compose ...`.

## A demonstração

| # | Passo | Tempo | Requisitos |
|---|---|---|---|
| 0 | Abertura | 1 min | — |
| 1 | Domínio novo ao vivo | 2 min | UC-06, RNF-08 |
| 2 | Rural com borda | 2 min | UC-01, UC-02, RF-EDG-03 |
| 3 | Corte de link | 3 min | RF-EDG-01/02, RF-ING-08, RNF-04 |
| 4 | Urbano nível 2 | 1,5 min | UC-03, RF-INT-03 |
| 5 | Três linguagens | 1 min | RF-INT-02 |
| 6 | Carga | 2 min | RNF-01, RNF-02 |
| 7 | Fechamento | 1 min | Critérios de aceite 9.3 |

### 0. Abertura

Uma plataforma para cidade e campo que não conhece nenhum dos dois: domínios, perfis e regras são dados. Mostre o diagrama de implantação em [arquitetura.md](arquitetura.md). Integração é só contrato (JSON Schema, AsyncAPI, OpenAPI). A borda guarda, decide e sincroniza.

**Já deixe o rural rodando:** a regra local leva cerca de 40 s para disparar, e esse tempo é coberto pelo passo 1.

```bash
docker compose -f simuladores/compose.yaml up -d rural-python
```

### 1. Domínio novo ao vivo

```bash
docker compose -f demo/compose.yaml run --rm dominio-novo
```

O script roda em 1 s e narra os quatro passos: domínio `recursos_hidricos`, perfil de reservatório, área e sensor com token, e regra. Mostre no Swagger (`GET /api/v1/catalogo/dominios`) que o domínio existe. Diga: "nenhuma linha de código mudou, nenhum serviço reiniciou". O simulador em JavaScript manda o primeiro dado em 2 s:

```bash
docker compose -f simuladores/compose.yaml up -d reservatorio-javascript
```

### 2. Rural com borda

O log da borda e o do simulador mostram a umidade caindo. Quando passa de 20% para baixo, a regra local abre o alarme e manda `abrir` para a válvula pelo broker da borda, sem passar pela central. A umidade volta a subir.

```bash
docker compose -f simuladores/compose.yaml logs -f rural-python
```

Procure a linha `válvula recebeu o comando {'nome': 'abrir', ...}`. No Grafana, o alarme aparece com origem `borda`, e o do silo (janela de 1 minuto acima de 30 °C, com "SMS" no log) com origem `central`.

### 3. Corte de link

```bash
docker network disconnect iot-link iot-borda-servico-core-1
```

**Espere um minuto.** No log da borda, `sincronização interrompida ... (N pendentes)` cresce a cada 5 s (no ensaio, 22 pendentes em 60 s). A regra local continua funcionando. O painel "bordas sem sincronizar" acusa a borda.

```bash
docker network connect iot-link iot-borda-servico-core-1
```

Em cerca de 6 s aparece `lote sincronizado`. No Grafana, o gráfico do solo e do silo fica sem buracos, uma medição a cada 5 s, na hora da medição. Diga que as 72 h são provadas pelo teste automatizado com timestamps retroativos, que também reinicia a borda e perde a resposta de um lote ([testes-sistema/desconexao](../testes-sistema/desconexao/README.md)).

**Durante o corte, `localhost:8001` não responde** (Docker Desktop). É esperado: os dados entram pelo Mosquitto da borda.

### 4. Urbano nível 2

```bash
docker compose -f simuladores/compose.yaml up -d estacao-legada-python
```

```bash
docker compose -f adaptadores-plugaveis/ar-urbano/compose.yaml up -d
```

Em cerca de 9 s a estação aparece no inquilino `semma`. O JSON do fabricante (`pm2_5`, `temp_f` em Fahrenheit) vira a mensagem canônica, e a temperatura chega em Celsius. O núcleo não foi reiniciado. Mostre no log do adaptador a tradução de cada leitura.

### 5. Três linguagens

```bash
docker compose -f simuladores/compose.yaml up -d lixeira-java
```

O primeiro 202 do Java vem em 2 s, e o alarme "lixeira cheia" aparece em menos de 30 s. Até aqui, estão no ar:

- Python com MQTT (`paho-mqtt`);
- JavaScript só com `fetch`;
- Java só com `HttpClient`.

Nenhum deles usa biblioteca da plataforma.

```bash
docker compose -f simuladores/compose.yaml logs --tail 3
```

### 6. Carga

Pare os simuladores e suba as réplicas. O `--wait` só devolve o terminal quando os 10 processos estão saudáveis (13 s no ensaio).

```bash
docker compose -f simuladores/compose.yaml stop
```

```bash
docker compose -f infra/central/compose.yaml --profile escala up -d --wait
```

**Ao vivo, use 600 msg/s por 30 s** (no ensaio: aprovado, com p95 de 9 ms). Mostre a vazão e a latência no Grafana.

```bash
TAXA=600 DURACAO_S=30 docker compose -f testes-sistema/carga/compose.yaml run --rm carga
```

Depois, abra o [resultado de 1.000 msg/s](../testes-sistema/carga/resultado.md) e conte a história do [README do teste](../testes-sistema/carga/README.md):

- um processo Python faz cerca de 150 msg/s;
- a escala horizontal chegou a 1.000 msg/s;
- o teto do notebook é de cerca de 1.050 msg/s;
- o próximo passo seria gravar em micro-lotes.

Rodar 1.000 msg/s ao vivo é arriscado: com o notebook ocupado, o resultado já caiu para menos de 900. Para voltar a um processo só:

```bash
docker compose -f infra/central/compose.yaml --profile escala stop
```

### 7. Fechamento

Abra a [rastreabilidade](rastreabilidade.md). Todos os requisitos Essenciais têm status e evidência, e os só documentados têm justificativa. Os cinco critérios de aceite da seção 9.3 estão cumpridos, com a ressalva de que a folga da carga é pequena e o ambiente é o notebook, não uma homologação. Os ADRs registram cada decisão, inclusive o que foi trocado: Keycloak, Redis, Prometheus e PostGIS.

## Se algo der errado

| Sintoma | O que fazer |
|---|---|
| `dominio-novo` responde "já existia" | O ambiente não foi zerado. Siga em frente e diga que o script é idempotente; os itens já estão lá |
| A válvula demora a receber `abrir` | A umidade começa em 26% e cai cerca de 0,8 ponto a cada 5 s, então a regra dispara em uns 40 s. Enquanto isso, fale da borda |
| A borda não sincroniza depois de religar (`a central respondeu 401` no log) | A chave da borda não vale na central: rode o `preparar` e depois `docker compose -f infra/borda/compose.yaml up -d` |
| O teste de carga sai na hora com "central fora do ar" | As réplicas ainda estavam subindo. Rode o `up --wait` de novo e repita |
| O teste de carga reprova | Mostre o `resultado.md` registrado e explique o teto do notebook. A reprovação com a fila crescendo é justamente o que o teste mede |
| Grafana sem dados | Confira o intervalo ("Last 15 minutes") e as variáveis `$inquilino` e `$dispositivo` no topo do painel |

## Perguntas prováveis

- **Por que Python, se o desempenho é limitado?** O prazo era de um dia, e o núcleo só fala por contrato: trocar a linguagem de um serviço não muda nada fora dele. A escala é horizontal ([ADR-0004](adr/0004-python-fastapi-no-nucleo.md), [ADR-0022](adr/0022-escala-da-ingestao-com-assinatura-compartilhada.md)).
- **Como não há duplicatas?** Cada mensagem tem um `id_mensagem`, gravado na mesma transação dos dados com `ON CONFLICT DO NOTHING`. Os ids ficam guardados por 7 dias, mais que as 72 h de corte ([ADR-0011](adr/0011-janela-de-deduplicacao.md)).
- **E se a borda reenviar um lote que a central já gravou?** Esse caso está no teste de 72 h: a resposta do primeiro lote se perde, a borda reenvia e a central responde "duplicada".
- **Dado atrasado gera alarme?** Não. Ele entra no histórico na hora da medição, mas só dados com até 5 minutos de atraso disparam regras ([ADR-0013](adr/0013-dados-atrasados-e-agregados.md)).
- **Os sensores ficam offline durante o corte?** Ficam "desconhecidos", e não offline, porque a central não sabe ([ADR-0010](adr/0010-estado-desconhecido.md)).
- **E a segurança?** Chave de API com papéis, token por dispositivo (só o hash é guardado), isolamento por inquilino e fila da borda cifrada. Faltam TLS, ACL no broker e OIDC, que estão documentados ([ADR-0018](adr/0018-autenticacao-sem-keycloak.md)).
- **Como chegar a 10.000 msg/s?** Micro-lotes na gravação, mais servidores com o mesmo grupo de assinatura e réplicas do banco.
