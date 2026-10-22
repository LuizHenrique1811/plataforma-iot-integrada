# ADR-0013: Dados atrasados e agregados

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-ING-04, RF-PRO-02, RF-PRO-04 (Importante), RF-DAD-01

## Contexto

O RF-ING-04 exige que uma medição de 48 h atrás entre na posição correta do histórico **e não gere alarme como se fosse atual**. Depois de uma desconexão longa, a borda envia horas de dados de uma vez. Os agregados por hora e por dia (RF-PRO-04) precisam refletir esses dados, e o motor de regras não pode disparar alarmes atrasados em massa.

## Decisão

- **Séries:** hypertable do TimescaleDB indexada pelo `timestamp` da medição.
- **Agregados:** continuous aggregates, com política de atualização que cobre a janela de atraso aceita (pelo menos 72 h com folga). Um dado atrasado faz o TimescaleDB recalcular só a janela afetada.
- **Regras:** só avaliam dado "atual", isto é, quando a diferença entre a chegada e a medição está abaixo de um limite configurável. Dados atrasados vão para o histórico e para os agregados, mas não disparam ações.
- **Período desconectado:** quem avalia regras é a borda, com a regra local (RF-EDG-03). Os alarmes e eventos gerados lá chegam à central com o horário em que ocorreram (RF-PRO-05).

## Alternativas consideradas

- **Recalcular agregados num processo noturno.** Simples, mas os painéis ficam errados até lá.
- **Agregar na ingestão, com contadores.** Cada dado atrasado exige correção manual dos contadores.
- **Avaliar regras em todos os dados.** Uma medição de três dias atrás dispararia alarme agora.

## Consequências

- Painéis e consultas ficam corretos logo depois da sincronização.
- Uma reconexão depois de 72 h provoca um recálculo grande, com consumo de CPU na central.
- O limite de "dado atual" precisa ser configurável por regra ou por perfil, porque sensores que enviam de hora em hora e sensores que enviam a cada segundo têm atrasos normais diferentes.
- Os continuous aggregates estão na Timescale License (ADR-0007).
