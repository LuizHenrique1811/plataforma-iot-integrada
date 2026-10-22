-- Último contato de cada dispositivo e de cada nó de borda, base da situação online, offline
-- ou desconhecida (RF-DIS-06, ADR-0010). Atualizados na mesma transação da ingestão.

CREATE TABLE ultimo_contato (
    inquilino_id   text NOT NULL,
    dispositivo_id text NOT NULL,
    medido_em      timestamptz NOT NULL,
    recebido_em    timestamptz NOT NULL,
    via            text,
    PRIMARY KEY (inquilino_id, dispositivo_id)
);

CREATE TABLE contato_da_borda (
    inquilino_id text NOT NULL,
    via          text NOT NULL,
    recebido_em  timestamptz NOT NULL,
    PRIMARY KEY (inquilino_id, via)
);
