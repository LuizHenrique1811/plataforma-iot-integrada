# Simuladores

Clientes externos da plataforma, em três linguagens, cada um usando só uma biblioteca genérica de MQTT ou a biblioteca padrão de HTTP, mais o contrato canônico (RF-INT-02, [ADR-0021](../docs/adr/0021-simuladores-e-adaptador-como-clientes-externos.md)). Rodam em contêineres: a máquina não precisa de Node.js nem de JDK.

| Serviço | Linguagem e protocolo | Envia para | Dispositivos | Caso de uso |
|---|---|---|---|---|
| `rural-python` | Python + MQTT (`paho-mqtt`) | broker da borda (1884) | `solo-talhao07-02`, `silo-02`; ouve o comando da `valvula-talhao07` | UC-01, UC-02 |
| `estacao-legada-python` | Python + MQTT, JSON do fabricante | broker da central (1883), tópico `legado/estacoes/...` | `AR-CENTRO-03` (traduzido pelo adaptador `ar-urbano`) | UC-03 |
| `reservatorio-javascript` | JavaScript + HTTP (`fetch` nativo do Node 22, sem pacotes) | API da central (8000) | `reservatorio-01` | UC-06 |
| `lixeira-java` | Java + HTTP (`HttpClient` nativo do Java 21, sem dependências) | API da central (8000) | `lixeira-17` | UC-04 |

## Como rodar

Antes, prepare o catálogo e os tokens (ver o roteiro no [README](../README.md#roteiro-da-demonstração-10-a-15-min)):

```bash
docker compose -f demo/compose.yaml run --rm preparar
```

```bash
docker compose -f simuladores/compose.yaml up -d --build
```

Para subir um só, acrescente o nome do serviço (ex.: `reservatorio-javascript`). Para acompanhar:

```bash
docker compose -f simuladores/compose.yaml logs -f
```

Os simuladores HTTP leem o token do dispositivo de `demo/.env.demo` (fora do repositório), gerado por `demo/preparar.py` e `demo/dominio_novo.py`. `INTERVALO_S` muda o intervalo entre envios (padrão: 5 s).

## Comportamento

- **Solo:** seca aos poucos. Abaixo de 20%, a regra local da borda abre um alarme e manda abrir a válvula; o simulador recebe o comando e a umidade volta a subir, e o alarme se resolve sozinho.
- **Silo:** a temperatura dos grãos sobe devagar; acima de 30 °C por 1 minuto, a central abre um alarme crítico e registra o SMS (ADR-0012).
- **Estação legada:** envia PM2,5, ruído e temperatura em Fahrenheit; às vezes reenvia a mesma leitura, que o núcleo descarta.
- **Reservatório:** o nível sobe e desce entre 1,5 m e 8,5 m; abaixo de 2 m, a regra do domínio novo abre um alarme.
- **Lixeira:** enche a cada envio e é esvaziada ao passar de 95%; acima de 80%, um alarme pede a coleta.

## Amostras e validação

Cada simulador imprime uma mensagem de exemplo com `--amostra`. O CI valida as amostras das três linguagens contra o JSON Schema canônico:

```bash
python simuladores/python/simulador.py --amostra
node simuladores/javascript/simulador.mjs --amostra
java simuladores/java/Simulador.java --amostra
```
