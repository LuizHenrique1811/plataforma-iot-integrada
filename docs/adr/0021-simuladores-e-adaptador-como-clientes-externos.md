# ADR-0021: Simuladores e adaptador como clientes externos

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-INT-02, RF-INT-03, UC-03, UC-06, critério de aceite 9.3 (três linguagens)

## Contexto

O critério de aceite pede integração demonstrada em pelo menos três linguagens, e o RF-INT-02 exige que ela use só bibliotecas genéricas de MQTT e HTTP. O RF-INT-03 pede adaptadores de protocolo em contêineres plugáveis, implantados sem recompilar nem reiniciar o núcleo. Não há hardware: tudo é simulado. A máquina da apresentação tem Docker, mas não necessariamente Node.js nem JDK.

## Decisão

- **Clientes de verdade, fora do núcleo.** Os simuladores e o adaptador não importam nada do `servico-core`; usam só o protocolo e o contrato (`contratos/`). Se funcionam, qualquer projeto externo funciona do mesmo jeito.
- **Uma linguagem por protocolo, com o mínimo de dependências:**
  - **Python + MQTT** (`paho-mqtt`): sensores de solo e silo publicando na borda; a válvula ouve o tópico `comando` e reage à regra local (UC-01, UC-02).
  - **JavaScript + HTTP** (`fetch` nativo do Node 22, sem pacotes): o reservatório do domínio criado ao vivo (UC-06).
  - **Java + HTTP** (`HttpClient` nativo do Java 21, sem dependências, executado direto com `java Simulador.java`): a lixeira (UC-04).
  - **Estação urbana legada** em Python, publicando um JSON de fabricante num tópico próprio.
- **Adaptador `ar-urbano` em contêiner próprio** (Python + MQTT): traduz o JSON legado para a mensagem canônica e publica no tópico canônico. O `id_mensagem` é um UUID v5 da estação e do horário, para a leitura reenviada pela estação ser deduplicada; a unidade de origem (Fahrenheit) segue na mensagem e o núcleo converte.
- **Tudo em contêineres**, alcançando a central e a borda pelas portas publicadas (`host.docker.internal`, com `host-gateway` para funcionar também no Linux). Os tokens dos dispositivos HTTP ficam em `demo/.env.demo`, fora do repositório, gerados pelos scripts de demonstração.
- **Evidência no CI:** cada simulador imprime uma amostra (`--amostra`), e as amostras das três linguagens são validadas contra o JSON Schema canônico; a saída do adaptador também é testada contra o contrato.

## Alternativas consideradas

- **Bibliotecas de MQTT nas três linguagens** (MQTT.js, Eclipse Paho Java). Mostraria só um protocolo e exigiria gerenciador de pacotes no Node e no Java.
- **SDK próprio da plataforma.** Contraria a independência de linguagem (ADR-0002).
- **Adaptador dentro do núcleo, como plugin Python.** Mais simples, mas o RF-INT-03 pede implantação sem reiniciar o núcleo e em qualquer linguagem.

## Consequências

- Os quatro critérios de integração aparecem lado a lado: MQTT e HTTP, nível 1 (canônico) e nível 2 (adaptador).
- Os simuladores não dependem do ambiente da máquina, só do Docker.
- O adaptador descarta (com log) o JSON legado que não consegue traduzir; ele não tem DLQ própria. A DLQ do núcleo continua recebendo as mensagens canônicas que o núcleo recusar.
