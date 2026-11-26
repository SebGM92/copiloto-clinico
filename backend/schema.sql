CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Configuración de texto en español que además ignora tildes:
-- "hipertensión" y "hipertension" generan el mismo lexema.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'es_med') THEN
        CREATE TEXT SEARCH CONFIGURATION es_med (COPY = spanish);
        ALTER TEXT SEARCH CONFIGURATION es_med
            ALTER MAPPING FOR hword, hword_part, word WITH unaccent, spanish_stem;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS documents (
    id           SERIAL      PRIMARY KEY,
    slug         TEXT        NOT NULL UNIQUE,     -- ej: ges-dm2-2017
    title        TEXT        NOT NULL,
    publisher    TEXT        NOT NULL,            -- ej: MINSAL
    year         INTEGER     NOT NULL,            -- año de publicación o actualización
    source_url   TEXT        NOT NULL,            -- PDF original
    sha256       TEXT        NOT NULL,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id           BIGSERIAL   PRIMARY KEY,
    document_id  INTEGER     NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal      INTEGER     NOT NULL,            -- orden dentro del documento
    section      TEXT        NOT NULL,            -- ej: 2. Recomendaciones > 2.1 Tratamiento
    page_start   INTEGER     NOT NULL,
    page_end     INTEGER     NOT NULL,
    paragraphs   JSONB       NOT NULL,            -- [{"page": 12, "para": 3, "text": "...", "kind": "text"}]
    content      TEXT        NOT NULL,            -- párrafos unidos, para mostrar y buscar
    embedding    vector(1024) NOT NULL,
    tsv          tsvector GENERATED ALWAYS AS (
                     setweight(to_tsvector('es_med', section), 'A') ||
                     setweight(to_tsvector('es_med', content), 'B')
                 ) STORED,
    UNIQUE (document_id, ordinal)
);

CREATE INDEX IF NOT EXISTS ix_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS ix_chunks_tsv ON chunks USING gin (tsv);

-- Cada pregunta y su resultado, para auditar y mejorar
CREATE TABLE IF NOT EXISTS queries (
    id           BIGSERIAL   PRIMARY KEY,
    at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    question     TEXT        NOT NULL,
    status       TEXT        NOT NULL,            -- verified | retracted | abstained | no_evidence | blocked
    answer       TEXT,
    chunk_ids    BIGINT[]    NOT NULL DEFAULT '{}',
    problems     JSONB       NOT NULL DEFAULT '[]',
    latency_ms   INTEGER
);
