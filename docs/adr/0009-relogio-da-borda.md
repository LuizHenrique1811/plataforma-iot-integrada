# ADR-0009: Relógio da borda

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-ING-04, RF-EDG-02, RF-PRO-05

## Contexto

O `timestamp` da mensagem canônica é o momento da medição, em UTC (seção 4.4). A plataforma ordena por ele (RF-ING-04), a sincronização entrega os dados ordenados por ele (RF-EDG-02) e um alarme gerado na borda precisa aparecer com o horário em que ocorreu (RF-PRO-05). Porém, muitos dispositivos não têm relógio de tempo real e voltam a 1970 depois de um reinício, e a borda pode passar horas sem internet, portanto sem NTP.

## Decisão

- O `timestamp` vem do dispositivo quando ele envia um valor plausível.
- Se o dispositivo não envia `timestamp`, ou envia um valor implausível (antes de uma data mínima ou além de uma tolerância no futuro), a borda grava a hora de recepção como `timestamp` e registra que o carimbo veio da borda. O contrato ainda não tem campo para essa origem: propor um campo opcional na versão 1.x da mensagem canônica, o que não quebra compatibilidade.
- A borda mantém a hora por NTP quando tem link e por GPS quando houver módulo. O estado de sincronização do relógio entra nas métricas da borda.
- O carimbo é feito uma única vez, na recepção, e gravado na fila. Os reenvios carregam o mesmo valor, o que mantém a deduplicação consistente (ADR-0011).
- O relógio é uma porta do domínio (ADR-0005), para que os testes controlem o tempo.

## Alternativas consideradas

- **Sempre usar a hora da borda.** Simples, mas perde a hora real das medições que o dispositivo guardou antes de enviar.
- **Sempre usar a hora do dispositivo.** Dispositivos sem relógio enviam datas inválidas depois de reiniciar.
- **Carimbar na central.** Errado para dados atrasados: depois de 72 h de desconexão, todos teriam a hora da sincronização.

## Consequências

- Nenhuma medição é persistida sem horário.
- O carimbo da borda carrega o atraso entre medição e recepção: normalmente segundos, mas pode ser grande se o dispositivo acumular leituras.
- Uma borda muito tempo sem NTP e sem GPS acumula deriva. O Raspberry Pi 5 tem relógio de tempo real com conector para bateria; recomenda-se instalar a bateria.
