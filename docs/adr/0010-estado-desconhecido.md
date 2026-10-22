# ADR-0010: Estado "desconhecido" para dispositivos atrás de borda sem sincronizar

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-DIS-06, RF-EDG-06, RF-OBS-05

## Contexto

O RF-DIS-06 pede indicar online/offline usando o intervalo esperado do perfil: um sensor rural que envia de hora em hora não pode aparecer offline após 5 minutos sem dados. Quando o link de uma borda cai, a central para de receber dados de todos os dispositivos atrás dela. Se a central aplicasse só o intervalo esperado, marcaria todos como offline, embora possam estar funcionando normalmente e enviando para a borda.

## Decisão

Usar três estados:

- **online:** último dado dentro do intervalo esperado do perfil (com tolerância);
- **offline:** sem dados além do intervalo esperado, e a central tem informação atualizada sobre o dispositivo;
- **desconhecido:** o dispositivo chega pela borda (campo `via`), e a própria borda está sem contato além do limite configurado.

Quando a borda sincroniza, o estado de cada dispositivo é recalculado com os dados recebidos, usando o `timestamp` da medição. A borda calcula o estado localmente e pode enviá-lo no lote de sincronização.

## Alternativas consideradas

- **Só online e offline.** Gera falsos "offline" em massa a cada queda de link, com alarmes inúteis.
- **Herdar o estado da borda.** Equivale a marcar todos como offline, só que agrupados.

## Consequências

- Uma queda de link gera um único alerta, "borda sem sincronizar" (RF-OBS-05, Importante), em vez de um alarme por sensor.
- Painéis, regras de ausência de dados (RF-PRO-02) e a API precisam tratar o terceiro estado.
- O tempo sem sincronizar de cada borda passa a ser um dado de primeira classe, que também atende o RF-EDG-06 (Importante).
