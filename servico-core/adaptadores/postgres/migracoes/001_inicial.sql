-- Esquema inicial da instância central (ADR-0007, ADR-0008, ADR-0011, ADR-0017).
-- Nenhuma tabela é de cenário: domínios, perfis, locais e áreas são linhas (ADR-0003).

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE inquilinos (
    id          text PRIMARY KEY,
    nome        text NOT NULL,
    criado_em   timestamptz NOT NULL DEFAULT now()
);

-- Chaves de API: inquilino nulo e papel administrador = administrador da plataforma (ADR-0018).
CREATE TABLE chaves_api (
    id           text PRIMARY KEY,
    inquilino_id text REFERENCES inquilinos (id),
    papel        text NOT NULL,
    hash         text NOT NULL UNIQUE,
    descricao    text,
    criado_em    timestamptz NOT NULL DEFAULT now(),
    revogado_em  timestamptz
);

CREATE TABLE dominios (
    inquilino_id text NOT NULL REFERENCES inquilinos (id),
    id           text NOT NULL,
    nome         text NOT NULL,
    descricao    text,
    criado_em    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (inquilino_id, id)
);

-- grandezas: [{"grandeza", "unidade", "minimo", "maximo"}] (RF-CEN-02).
CREATE TABLE perfis (
    inquilino_id      text NOT NULL REFERENCES inquilinos (id),
    id                text NOT NULL,
    nome              text NOT NULL,
    grandezas         jsonb NOT NULL,
    intervalo_envio_s integer NOT NULL CHECK (intervalo_envio_s > 0),
    criado_em         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (inquilino_id, id)
);

CREATE TABLE sites (
    inquilino_id text NOT NULL REFERENCES inquilinos (id),
    id           text NOT NULL,
    nome         text NOT NULL,
    geo          jsonb,
    criado_em    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (inquilino_id, id)
);

CREATE TABLE areas (
    inquilino_id text NOT NULL,
    site_id      text NOT NULL,
    id           text NOT NULL,
    nome         text NOT NULL,
    geo          jsonb,
    criado_em    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (inquilino_id, site_id, id),
    FOREIGN KEY (inquilino_id, site_id) REFERENCES sites (inquilino_id, id)
);

CREATE TABLE dispositivos (
    inquilino_id text NOT NULL,
    id           text NOT NULL,
    perfil_id    text NOT NULL,
    dominio_id   text NOT NULL,
    site_id      text NOT NULL,
    area_id      text,
    fabricante   text,
    firmware     text,
    token_hash   text UNIQUE,
    criado_em    timestamptz NOT NULL DEFAULT now(),
    revogado_em  timestamptz,
    PRIMARY KEY (inquilino_id, id),
    FOREIGN KEY (inquilino_id, perfil_id) REFERENCES perfis (inquilino_id, id),
    FOREIGN KEY (inquilino_id, dominio_id) REFERENCES dominios (inquilino_id, id),
    FOREIGN KEY (inquilino_id, site_id) REFERENCES sites (inquilino_id, id),
    FOREIGN KEY (inquilino_id, site_id, area_id) REFERENCES areas (inquilino_id, site_id, id)
);

-- Deduplicação (ADR-0011). Tabela comum: uma hypertable não aceita chave única só no id_mensagem.
-- Linhas com mais de 7 dias são apagadas periodicamente.
CREATE TABLE mensagens_recebidas (
    id_mensagem  uuid PRIMARY KEY,
    inquilino_id text NOT NULL,
    recebido_em  timestamptz NOT NULL
);
CREATE INDEX mensagens_recebidas_recebido_em ON mensagens_recebidas (recebido_em);

-- Séries temporais pelo horário da medição (RF-ING-04, RF-DAD-01). recebido_em e persistido_em
-- permitem medir a latência no Grafana sem servidor Prometheus (ADR-0007).
CREATE TABLE medicoes (
    medido_em        timestamptz NOT NULL,
    inquilino_id     text NOT NULL,
    dispositivo_id   text NOT NULL,
    grandeza         text NOT NULL,
    valor            double precision,
    valor_texto      text,
    unidade          text,
    suspeita         boolean NOT NULL DEFAULT false,
    id_mensagem      uuid NOT NULL,
    dominio_id       text,
    site_id          text,
    area_id          text,
    via              text,
    origem_timestamp text NOT NULL,
    recebido_em      timestamptz NOT NULL,
    persistido_em    timestamptz NOT NULL DEFAULT clock_timestamp()
);
SELECT create_hypertable('medicoes', by_range('medido_em'));
CREATE INDEX medicoes_dispositivo ON medicoes (inquilino_id, dispositivo_id, grandeza, medido_em DESC);

-- Último estado (RF-DAD-02, ADR-0017).
CREATE TABLE ultimo_estado (
    inquilino_id   text NOT NULL,
    dispositivo_id text NOT NULL,
    grandeza       text NOT NULL,
    valor          double precision,
    valor_texto    text,
    unidade        text,
    suspeita       boolean NOT NULL DEFAULT false,
    medido_em      timestamptz NOT NULL,
    id_mensagem    uuid NOT NULL,
    PRIMARY KEY (inquilino_id, dispositivo_id, grandeza)
);

-- Eventos e estados relatados.
CREATE TABLE eventos (
    ocorrido_em    timestamptz NOT NULL,
    inquilino_id   text NOT NULL,
    dispositivo_id text NOT NULL,
    tipo           text NOT NULL,
    nome           text,
    severidade     text,
    dados          jsonb,
    id_mensagem    uuid NOT NULL,
    via            text,
    recebido_em    timestamptz NOT NULL
);
SELECT create_hypertable('eventos', by_range('ocorrido_em'));
CREATE INDEX eventos_dispositivo ON eventos (inquilino_id, dispositivo_id, ocorrido_em DESC);

-- Fila de mensagens inválidas (Dead Letter Channel).
CREATE TABLE rejeitadas (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recebido_em  timestamptz NOT NULL,
    inquilino_id text,
    etapa        text NOT NULL,
    motivo       text NOT NULL,
    erros        jsonb NOT NULL DEFAULT '[]',
    carga        jsonb,
    carga_texto  text,
    origem       text
);
CREATE INDEX rejeitadas_inquilino ON rejeitadas (inquilino_id, recebido_em DESC);
