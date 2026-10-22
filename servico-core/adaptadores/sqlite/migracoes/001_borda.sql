-- Esquema do nó de borda: o mesmo da central (migrações 001 a 003 do PostgreSQL) em tipos SQLite,
-- mais a fila de sincronização. Tipos declarados (TIMESTAMPTZ, JSONB, UUID, BOOLEAN) são convertidos
-- pelo adaptador (adaptadores/sqlite/conexao.py).

CREATE TABLE inquilinos (
    id        TEXT PRIMARY KEY,
    nome      TEXT NOT NULL,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now'))
);

CREATE TABLE chaves_api (
    id           TEXT PRIMARY KEY,
    inquilino_id TEXT REFERENCES inquilinos (id),
    papel        TEXT NOT NULL,
    hash         TEXT NOT NULL UNIQUE,
    descricao    TEXT,
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now')),
    revogado_em  TIMESTAMPTZ
);

CREATE TABLE dominios (
    inquilino_id TEXT NOT NULL REFERENCES inquilinos (id),
    id           TEXT NOT NULL,
    nome         TEXT NOT NULL,
    descricao    TEXT,
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now')),
    PRIMARY KEY (inquilino_id, id)
);

CREATE TABLE perfis (
    inquilino_id      TEXT NOT NULL REFERENCES inquilinos (id),
    id                TEXT NOT NULL,
    nome              TEXT NOT NULL,
    grandezas         JSONB NOT NULL,
    intervalo_envio_s INTEGER NOT NULL CHECK (intervalo_envio_s > 0),
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now')),
    PRIMARY KEY (inquilino_id, id)
);

CREATE TABLE sites (
    inquilino_id TEXT NOT NULL REFERENCES inquilinos (id),
    id           TEXT NOT NULL,
    nome         TEXT NOT NULL,
    geo          JSONB,
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now')),
    PRIMARY KEY (inquilino_id, id)
);

CREATE TABLE areas (
    inquilino_id TEXT NOT NULL,
    site_id      TEXT NOT NULL,
    id           TEXT NOT NULL,
    nome         TEXT NOT NULL,
    geo          JSONB,
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now')),
    PRIMARY KEY (inquilino_id, site_id, id),
    FOREIGN KEY (inquilino_id, site_id) REFERENCES sites (inquilino_id, id)
);

CREATE TABLE dispositivos (
    inquilino_id TEXT NOT NULL,
    id           TEXT NOT NULL,
    perfil_id    TEXT NOT NULL,
    dominio_id   TEXT NOT NULL,
    site_id      TEXT NOT NULL,
    area_id      TEXT,
    fabricante   TEXT,
    firmware     TEXT,
    token_hash   TEXT UNIQUE,
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now')),
    revogado_em  TIMESTAMPTZ,
    PRIMARY KEY (inquilino_id, id),
    FOREIGN KEY (inquilino_id, perfil_id) REFERENCES perfis (inquilino_id, id),
    FOREIGN KEY (inquilino_id, dominio_id) REFERENCES dominios (inquilino_id, id),
    FOREIGN KEY (inquilino_id, site_id) REFERENCES sites (inquilino_id, id),
    FOREIGN KEY (inquilino_id, site_id, area_id) REFERENCES areas (inquilino_id, site_id, id)
);

-- Deduplicação também na borda: o mesmo dispositivo pode reenviar enquanto o link está fora.
CREATE TABLE mensagens_recebidas (
    id_mensagem  UUID PRIMARY KEY,
    inquilino_id TEXT NOT NULL,
    recebido_em  TIMESTAMPTZ NOT NULL
);
CREATE INDEX mensagens_recebidas_recebido_em ON mensagens_recebidas (recebido_em);

CREATE TABLE medicoes (
    medido_em        TIMESTAMPTZ NOT NULL,
    inquilino_id     TEXT NOT NULL,
    dispositivo_id   TEXT NOT NULL,
    grandeza         TEXT NOT NULL,
    valor            REAL,
    valor_texto      TEXT,
    unidade          TEXT,
    suspeita         BOOLEAN NOT NULL DEFAULT 0,
    id_mensagem      UUID NOT NULL,
    dominio_id       TEXT,
    site_id          TEXT,
    area_id          TEXT,
    via              TEXT,
    origem_timestamp TEXT NOT NULL,
    recebido_em      TIMESTAMPTZ NOT NULL,
    persistido_em    TIMESTAMPTZ NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now'))
);
CREATE INDEX medicoes_dispositivo ON medicoes (inquilino_id, dispositivo_id, grandeza, medido_em DESC);

CREATE TABLE ultimo_estado (
    inquilino_id   TEXT NOT NULL,
    dispositivo_id TEXT NOT NULL,
    grandeza       TEXT NOT NULL,
    valor          REAL,
    valor_texto    TEXT,
    unidade        TEXT,
    suspeita       BOOLEAN NOT NULL DEFAULT 0,
    medido_em      TIMESTAMPTZ NOT NULL,
    id_mensagem    UUID NOT NULL,
    PRIMARY KEY (inquilino_id, dispositivo_id, grandeza)
);

CREATE TABLE eventos (
    ocorrido_em    TIMESTAMPTZ NOT NULL,
    inquilino_id   TEXT NOT NULL,
    dispositivo_id TEXT NOT NULL,
    tipo           TEXT NOT NULL,
    nome           TEXT,
    severidade     TEXT,
    dados          JSONB,
    id_mensagem    UUID NOT NULL,
    via            TEXT,
    recebido_em    TIMESTAMPTZ NOT NULL
);
CREATE INDEX eventos_dispositivo ON eventos (inquilino_id, dispositivo_id, ocorrido_em DESC);

CREATE TABLE rejeitadas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    recebido_em  TIMESTAMPTZ NOT NULL,
    inquilino_id TEXT,
    etapa        TEXT NOT NULL,
    motivo       TEXT NOT NULL,
    erros        JSONB NOT NULL DEFAULT '[]',
    carga        JSONB,
    carga_texto  TEXT,
    origem       TEXT
);
CREATE INDEX rejeitadas_inquilino ON rejeitadas (inquilino_id, recebido_em DESC);

CREATE TABLE ultimo_contato (
    inquilino_id   TEXT NOT NULL,
    dispositivo_id TEXT NOT NULL,
    medido_em      TIMESTAMPTZ NOT NULL,
    recebido_em    TIMESTAMPTZ NOT NULL,
    via            TEXT,
    PRIMARY KEY (inquilino_id, dispositivo_id)
);

CREATE TABLE contato_da_borda (
    inquilino_id TEXT NOT NULL,
    via          TEXT NOT NULL,
    recebido_em  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (inquilino_id, via)
);

CREATE TABLE regras (
    inquilino_id TEXT NOT NULL REFERENCES inquilinos (id),
    id           TEXT NOT NULL,
    nome         TEXT NOT NULL,
    ambito       TEXT NOT NULL,
    ativa        BOOLEAN NOT NULL DEFAULT 1,
    definicao    JSONB NOT NULL,
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now')),
    PRIMARY KEY (inquilino_id, id)
);
CREATE INDEX regras_ativas ON regras (inquilino_id, ambito) WHERE ativa;

CREATE TABLE estado_regras (
    inquilino_id   TEXT NOT NULL,
    regra_id       TEXT NOT NULL,
    dispositivo_id TEXT NOT NULL,
    condicao_ativa BOOLEAN NOT NULL,
    desde          TIMESTAMPTZ,
    disparada      BOOLEAN NOT NULL,
    atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now')),
    PRIMARY KEY (inquilino_id, regra_id, dispositivo_id)
);

CREATE TABLE alarmes (
    id             UUID PRIMARY KEY,
    inquilino_id   TEXT NOT NULL,
    regra_id       TEXT NOT NULL,
    dispositivo_id TEXT NOT NULL,
    severidade     TEXT NOT NULL,
    estado         TEXT NOT NULL,
    mensagem       TEXT,
    origem         TEXT NOT NULL,
    ocorrido_em    TIMESTAMPTZ NOT NULL,
    reconhecido_em TIMESTAMPTZ,
    resolvido_em   TIMESTAMPTZ,
    id_mensagem    UUID
);
CREATE INDEX alarmes_inquilino ON alarmes (inquilino_id, estado, ocorrido_em DESC);
CREATE UNIQUE INDEX alarmes_um_aberto ON alarmes (inquilino_id, regra_id, dispositivo_id)
    WHERE estado <> 'resolvido' AND origem <> 'borda';

-- Fila de saída para a central (store-and-forward, RF-EDG-01/02). Cada item é a mensagem canônica,
-- gravada na mesma transação da ingestão e removida só depois da confirmação da central.
-- prioridade 0 (eventos e alarmes) sai antes de 1 (telemetria rotineira), como pede o RF-EDG-05.
CREATE TABLE fila_sincronizacao (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    id_mensagem UUID NOT NULL UNIQUE,
    prioridade  INTEGER NOT NULL,
    carga       JSONB NOT NULL,
    criado_em   TIMESTAMPTZ NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f+00:00','now'))
);
CREATE INDEX fila_sincronizacao_ordem ON fila_sincronizacao (prioridade, seq);
