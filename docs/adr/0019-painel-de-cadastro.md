# ADR-0019: Documentação interativa da API como painel de cadastro

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-DIS-01, RF-CEN-01, RF-APP-01

## Contexto

O critério do RF-DIS-01 diz que um dispositivo cadastrado "pela API e pelo painel" aparece com todos os atributos, e o RF-CEN-01 aceita criar domínios "pela API ou painel". O planejamento não prevê uma interface web de cadastro. O RF-APP-01 já exige documentação interativa gerada a partir do contrato.

## Decisão

Usar a documentação interativa da API (Swagger UI), servida pelo `servico-core` a partir de `contratos/openapi.yaml`, como painel de cadastro. Pelo navegador, ela permite cadastrar domínios, perfis, locais, áreas e dispositivos e consultar o resultado. O Grafana continua sendo o painel de leitura (séries, último estado e alarmes).

## Alternativas consideradas

- **Página web de cadastro própria.** Mais amigável, mas é uma interface a mais para construir num prazo de um dia.
- **Cadastro pelo Grafana.** O Grafana é feito para leitura, não para formulários de cadastro.

## Consequências

- O critério é atendido de forma simplificada: o "painel" é técnico, voltado a integradores e gestores.
- Sem código extra, porque a documentação interativa já é exigida pelo RF-APP-01.
- **Evolução:** uma interface web responsiva (RF-APP-06, RNF-16) consumindo a mesma API.
