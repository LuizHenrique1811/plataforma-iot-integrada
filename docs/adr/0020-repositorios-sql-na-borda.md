# ADR-0020: Os mesmos repositórios SQL na central e na borda

- **Status:** aceito
- **Data:** 2026-10-22
- **Requisitos:** RF-EDG-01, RF-EDG-02, RF-EDG-03, RF-SEG-05, RNF-07

## Contexto

A borda executa o mesmo domínio que a central ([ADR-0006](0006-uma-imagem-dois-ambientes.md)): ingestão, catálogo, regras e alarmes. A central usa PostgreSQL; a borda, SQLite com a fila cifrada pelo SQLCipher ([ADR-0014](0014-chave-da-fila-da-borda.md)). Escrever um segundo conjunto de repositórios só para SQLite duplicaria centenas de linhas de SQL num prazo de um dia, e as duas versões poderiam divergir.

## Decisão

Os repositórios SQL da central rodam sem cópia na borda. O adaptador `adaptadores/sqlite/conexao.py` oferece a mesma interface que eles usam do `psycopg_pool` e trata as diferenças:

- **SQL:** troca os marcadores `%s` por `?`, `GREATEST(` por `MAX(`, `now()` pelo `strftime` do SQLite e o operador JSON do PostgreSQL por `json_extract`. As consultas que dependiam de combinar colunas no SQL (`COALESCE` entre tipos) passaram a combinar em Python, o que funciona nos dois bancos.
- **Tipos:** datas gravadas como texto ISO 8601 em UTC com largura fixa (assim a ordem do texto é a ordem do tempo), JSON como texto, UUID como texto e booleanos como 0 e 1, convertidos de volta pelos tipos declarados no esquema (`TIMESTAMPTZ`, `JSONB`, `UUID`, `BOOLEAN`).
- **Esquema:** migração própria em `adaptadores/sqlite/migracoes/`, equivalente às da central, mais a fila de sincronização.
- **Durabilidade:** modo WAL com `synchronous=FULL` ([ADR-0016](0016-energia-e-armazenamento-da-borda.md)); uma conexão compartilhada e serializada.
- **Ganchos:** o repositório de ingestão da borda é uma subclasse do da central que, na mesma transação, enfileira a mensagem para a central.

## Alternativas consideradas

- **Repositórios separados para SQLite.** Isolamento total, mas o dobro de SQL para manter e testar.
- **ORM (SQLAlchemy) com dialetos.** Resolveria as diferenças de forma geral, mas exigiria reescrever os repositórios e as migrações já prontos.
- **Banco em memória na borda.** Simples, mas perde a fila numa queda de energia (viola o RNF-07 e o RF-EDG-01).

## Consequências

- O comportamento da borda é o da central: os mesmos testes de repositório passam sobre os dois bancos (`test_postgres.py` e `test_sqlite.py`).
- A tradução de SQL é deliberadamente pequena; um recurso novo exclusivo do PostgreSQL nos repositórios compartilhados precisa de tradução ou de uma alternativa portável, e o `test_sqlite.py` acusa a falta.
- A borda serializa as gravações numa única conexão, o que é adequado ao volume de uma propriedade rural, mas não ao da central.
