# ADR-0012: Envio de SMS pela central

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-APP-05 (Importante), RF-PRO-03, UC-02

## Contexto

O RF-APP-05 pede notificação por e-mail, aplicativo de mensagens e SMS, com o critério "alarme crítico chega ao produtor por SMS mesmo sem internet móvel". O SMS chega ao celular sem dados móveis, mas alguém precisa enviá-lo: a central, por um provedor, ou a borda, por um modem GSM. O RF-APP-05 é Importante (fase 2), mas aparece no UC-02. A ação "notificar" do motor de regras é Essencial (RF-PRO-03).

## Decisão

- A notificação é uma porta do domínio (ADR-0005), e cada canal é um adaptador.
- No trabalho, o SMS é enviado pela central, por um provedor com API HTTP. Para testes e para a demonstração, um adaptador falso registra a notificação no log. A credencial do provedor real vem de variável de ambiente.
- SMS direto da borda, com modem GSM, fica registrado como evolução.

## Alternativas consideradas

- **Modem GSM na borda.** Funciona sem internet, justamente quando o link cai, mas exige hardware, chip e cobertura de operadora.
- **Só e-mail ou notificação por aplicativo.** Não atende o critério sem internet móvel.

## Consequências

- Implementação simples, e a ação "notificar" (RF-PRO-03) é testada com o adaptador falso.
- **Limitação:** um alarme gerado na borda durante a desconexão só vira SMS depois da reconexão. No cenário rural, é exatamente quando o link cai. A regra local (RF-EDG-03) continua acionando o atuador, mas o produtor só é avisado depois.
- O provedor real tem custo e credencial, e por isso não é usado na demonstração.
