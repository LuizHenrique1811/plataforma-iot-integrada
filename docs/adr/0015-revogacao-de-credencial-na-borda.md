# ADR-0015: Revogação de credencial na borda

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-DIS-02, RF-SEG-04, RF-SEG-05

## Contexto

O RF-DIS-02 pede credenciais únicas por dispositivo (certificado X.509 **ou token**) e o critério diz: "credencial revogada é recusada na conexão seguinte, na central e nos nós de borda". Uma borda desconectada não tem como saber de uma revogação feita na central depois da queda do link. Esse critério conflita com a operação desconectada.

## Decisão

- **Credencial:** token por dispositivo, uma das duas opções que o próprio requisito aceita. A borda guarda só o hash dos tokens.
- **Lista de revogação:** a borda mantém uma lista de revogação sincronizada com a central, com versão incremental. Ao conectar, ela recebe as revogações novas e passa a recusar essas credenciais.
- **Mitigação na central:** ao receber um lote, a central recusa (DLQ, motivo "credencial revogada") as mensagens de dispositivos revogados cujo `timestamp` de medição seja posterior à revogação.
- **Limitação documentada:** durante a desconexão, uma credencial revogada na central continua aceita pela borda até a próxima sincronização.

## Alternativas consideradas

- **A borda consultar a central a cada conexão de dispositivo.** Não funciona sem link.
- **Tokens com expiração curta.** Dispositivos sem relógio confiável e uma borda sem link tornam a expiração frágil, e a renovação dependeria da central.

## Consequências

- O critério é atendido na central e nas bordas conectadas. Nas desconectadas, vale a partir da reconexão.
- A janela de exposição é igual à duração da desconexão.
- Os dados enviados nesse período por um dispositivo revogado não entram no histórico, por causa da mitigação na central.
