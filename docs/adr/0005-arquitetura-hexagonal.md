# ADR-0005: Arquitetura hexagonal

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-PRO-03, RNF-15

## Contexto

A mesma lógica roda na central (PostgreSQL com TimescaleDB) e na borda (SQLite cifrado). Os dados entram por MQTT, REST e lotes de sincronização. Cada ação do motor de regras precisa de teste automatizado (RF-PRO-03). O próprio documento adota portas e adaptadores em cada serviço (seção 7.1).

## Decisão

Cada serviço é organizado em três partes:

- `dominio/`: entidades, pipeline de ingestão e regras. Não importa FastAPI, cliente MQTT nem driver de banco.
- `portas/`: interfaces pelas quais o domínio fala com o mundo (repositórios, fila, publicação de eventos, relógio).
- `adaptadores/`: implementações das portas (mqtt, rest, lote, postgres, sqlite).

A ligação entre portas e adaptadores é feita na inicialização, de acordo com a configuração do ambiente.

## Alternativas consideradas

- **Camadas tradicionais com o ORM dentro do domínio.** Mais simples no começo, mas acopla as regras ao banco e impede reaproveitar o código na borda.
- **Dois códigos separados, um para a central e outro para a borda.** Duplica a lógica e deixa as duas versões divergirem.

## Consequências

- O domínio é testado com adaptadores em memória, o que deixa os testes rápidos e ajuda a atingir a cobertura de 70%.
- Trocar de banco significa escrever um novo adaptador.
- Há mais arquivos e mais indireção.
- As portas precisam ser o mínimo comum entre PostgreSQL e SQLite. Recursos específicos da central (hypertables, continuous aggregates, PostGIS) ficam atrás de portas próprias, que a borda não implementa ou implementa de forma simplificada.
- A regra de dependência pode ser verificada no CI, proibindo imports de framework, MQTT ou banco dentro de `dominio/`.
