# ADR-0003: Catálogo configurável (Type Object)

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-CEN-01, RF-CEN-02, RF-CEN-03, RNF-08, UC-06

## Contexto

O mesmo núcleo atende cenários rurais, urbanos e domínios que ainda não existem. A demonstração cria o domínio `recursos_hidricos` ao vivo, sem tocar no código (UC-06).

## Decisão

Domínios, perfis de dispositivo, locais, áreas e regras são registros do catálogo, seguindo o padrão Type Object: o "tipo" de uma coisa é um dado, não uma classe. O código conhece apenas os conceitos genéricos: inquilino, domínio, perfil, local (site), área, dispositivo, regra e medição.

- O catálogo de domínios é por inquilino (RF-CEN-01).
- O perfil define grandezas, unidades (UCUM), faixa válida e intervalo esperado de envio (RF-CEN-02).
- Os locais seguem a hierarquia inquilino → local → área → dispositivo (RF-CEN-03).

## Alternativas consideradas

- **Uma classe ou tabela por cenário** (`Talhao`, `Silo`, `Praca`). Dá tipagem forte, mas cada domínio novo exige código, migração e implantação, o que viola o RNF-08.
- **Entidade-atributo-valor sem perfis.** Flexível, mas não há como validar medições e as consultas ficam difíceis.

## Consequências

- Um domínio novo é só um cadastro pela API.
- O mesmo pipeline de ingestão e o mesmo motor de regras servem a todos os cenários.
- A conferência de uma medição contra o perfil acontece em tempo de execução. Uma medida fora da faixa do perfil é marcada como suspeita, não rejeitada (critério do RF-CEN-02). A rejeição para a DLQ fica para mensagens fora do JSON Schema.
- O intervalo esperado de envio do perfil é o que define online/offline (RF-DIS-06, ADR-0010).
- Os painéis do Grafana precisam ser parametrizados por domínio e perfil, em vez de fixos por cenário.
- Regra de revisão: nomes de cenário ("talhao", "silo", "praca") não aparecem em `servico-core/`, exceto em testes e dados de exemplo.
