# ADR-0001: Monorepo

- **Status:** aceito
- **Data:** 2026-10-22

## Contexto

O projeto reúne o núcleo (`servico-core`), um adaptador plugável, simuladores em três linguagens, a infraestrutura dos dois ambientes, os contratos e os testes de sistema. Todos dependem dos mesmos contratos, e a matriz de rastreabilidade usa commits como evidência.

## Decisão

Manter tudo num único repositório, `plataforma-iot-integrada`, com a estrutura descrita no README.

## Alternativas consideradas

- **Um repositório por serviço e por simulador.** Dá isolamento real e versões independentes, mas uma mudança de contrato exigiria alterações coordenadas em vários repositórios, e a matriz de rastreabilidade apontaria para lugares diferentes.

## Consequências

- Um mesmo commit pode alterar o contrato e a implementação, e o CI valida os dois juntos.
- Há uma só matriz de rastreabilidade, com evidências num só lugar.
- A independência de linguagem passa a depender de disciplina: simuladores e adaptadores plugáveis só podem usar o que está em `contratos/`, nunca importar código do `servico-core`.
- O CI precisa de filtros por caminho para não rodar todos os jobs a cada mudança.
