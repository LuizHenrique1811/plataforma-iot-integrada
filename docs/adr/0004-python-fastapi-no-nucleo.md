# ADR-0004: Python 3.12 e FastAPI no núcleo

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RNF-01, RNF-06, RNF-15

## Contexto

O núcleo expõe uma API REST, consome MQTT, valida mensagens contra JSON Schema e executa regras. O prazo é de seis semanas, o MVP precisa sustentar 1.000 msg/s (RNF-01), o núcleo precisa de pelo menos 70% de cobertura de testes (RNF-15) e a borda roda num equipamento com 4 núcleos ARM e 4 GB de RAM (RNF-06). O documento deixa a linguagem dos serviços próprios a critério da equipe (seção 9.1).

## Decisão

Usar Python 3.12 e FastAPI no `servico-core`. O arquivo `contratos/openapi.yaml` continua sendo a fonte da verdade: a especificação que o FastAPI gera é comparada com ele no CI.

## Alternativas consideradas

- **Go.** Maior vazão e binário pequeno, bom para a borda, mas com desenvolvimento mais lento no prazo do trabalho.
- **Java com Spring.** Robusto, mas pesado em memória para rodar na borda.
- **Node.js.** Bom para I/O, mas o ecossistema Python para dados e testes (pytest, jsonschema, SQLAlchemy, clientes MQTT) é mais completo para este projeto.

## Consequências

- Desenvolvimento rápido, com ferramentas de teste maduras.
- A linguagem pode ser trocada no futuro, porque os serviços só se comunicam por contrato (ADR-0002).
- Chegar a 1.000 msg/s exige cuidado: schema pré-compilado na validação, inserts em lote e ingestão MQTT assíncrona. A meta de 10.000 msg/s fica apenas documentada.
- A imagem é maior que a de um binário compilado, o que é aceitável numa borda do porte do RNF-06 (por exemplo, um Raspberry Pi 5 com 4 GB).
