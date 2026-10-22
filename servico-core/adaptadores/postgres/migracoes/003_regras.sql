-- Regras, estado das regras por dispositivo e alarmes (RF-PRO-02, RF-PRO-03, RF-PRO-05).

-- definicao: a regra completa no formato do contrato (Regra em openapi.yaml).
CREATE TABLE regras (
    inquilino_id text NOT NULL REFERENCES inquilinos (id),
    id           text NOT NULL,
    nome         text NOT NULL,
    ambito       text NOT NULL,
    ativa        boolean NOT NULL DEFAULT true,
    definicao    jsonb NOT NULL,
    criado_em    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (inquilino_id, id)
);
CREATE INDEX regras_ativas ON regras (inquilino_id, ambito) WHERE ativa;

-- Dispara na transição: guarda se a condição está valendo, desde quando e se já disparou.
CREATE TABLE estado_regras (
    inquilino_id   text NOT NULL,
    regra_id       text NOT NULL,
    dispositivo_id text NOT NULL,
    condicao_ativa boolean NOT NULL,
    desde          timestamptz,
    disparada      boolean NOT NULL,
    atualizado_em  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (inquilino_id, regra_id, dispositivo_id)
);

CREATE TABLE alarmes (
    id             uuid PRIMARY KEY,
    inquilino_id   text NOT NULL,
    regra_id       text NOT NULL,
    dispositivo_id text NOT NULL,
    severidade     text NOT NULL,
    estado         text NOT NULL,
    mensagem       text,
    origem         text NOT NULL,
    ocorrido_em    timestamptz NOT NULL,
    reconhecido_em timestamptz,
    resolvido_em   timestamptz,
    id_mensagem    uuid
);
CREATE INDEX alarmes_inquilino ON alarmes (inquilino_id, estado, ocorrido_em DESC);
-- Um alarme aberto por regra e dispositivo nas regras avaliadas aqui; os vindos da borda já chegam deduplicados.
CREATE UNIQUE INDEX alarmes_um_aberto ON alarmes (inquilino_id, regra_id, dispositivo_id)
    WHERE estado <> 'resolvido' AND origem <> 'borda';
