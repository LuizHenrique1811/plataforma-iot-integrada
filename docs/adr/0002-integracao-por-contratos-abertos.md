# ADR-0002: Integração por contratos abertos

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-INT-01, RF-INT-02, RNF-13, critério de aceite 9.3

## Contexto

A plataforma precisa receber dados de dispositivos e sistemas escritos em qualquer linguagem (seção 4.1 do documento). O RF-INT-02 exige exemplos funcionais em três linguagens usando só bibliotecas genéricas de MQTT e HTTP, e o RNF-13 exige que 100% das interfaces sejam descritas por contratos abertos.

## Decisão

A integração é feita apenas por contratos em formatos abertos, guardados em `contratos/`:

- **JSON Schema** para a mensagem canônica (v1.0);
- **AsyncAPI 3** para os tópicos MQTT;
- **OpenAPI 3** para a API REST;
- **GeoJSON** para geometrias.

O contexto em NGSI-LD com Smart Data Models (RF-INT-05, RF-CEN-06) é Importante e fica para a fase 2.

O contrato é escrito antes do código ("contrato primeiro"), segue versionamento semântico (quebra só em versão MAJOR) e é validado no CI. Não existe SDK obrigatório.

## Alternativas consideradas

- **SDK oficial por linguagem.** Facilita o primeiro uso, mas cria dependência e manutenção em várias linguagens, e contradiz a independência de linguagem.
- **Protobuf ou gRPC.** Contrato forte e mensagens menores, mas exige gerador de código e é menos acessível a firmware simples e a ferramentas comuns.
- **JSON sem schema.** Rápido de começar, mas não permite validar mensagens nem informar o motivo da rejeição na DLQ.

## Consequências

- Qualquer cliente MQTT ou HTTP que monte um JSON consegue integrar; os simuladores em três linguagens servem de prova.
- A etapa de validação do pipeline usa o próprio schema e produz o motivo de rejeição que vai para a DLQ.
- JSON é mais verboso que formatos binários, o que pesa na banda da borda.
- Evoluir o contrato exige disciplina de versão: a mensagem declara sua versão no campo `versao`, e o pipeline valida contra o schema correspondente.
- O RF-INT-01 pede o contrato numa URL pública com histórico de versões. O `servico-core` deve servir os arquivos de `contratos/`, e o histórico vem das versões publicadas (tags do Git).
