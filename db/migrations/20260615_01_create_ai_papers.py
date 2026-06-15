"""Create dashboard tables for flattened OpenAlex AI papers."""

from yoyo import step

APPLY = """
CREATE TABLE IF NOT EXISTS paper_ingest_runs (
    id              SERIAL PRIMARY KEY,
    fetched_at      TIMESTAMPTZ NOT NULL,
    from_date       DATE NOT NULL,
    to_date         DATE NOT NULL,
    subfield_id     TEXT NOT NULL,
    paper_count     INTEGER NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_papers (
    openalex_id             TEXT PRIMARY KEY,
    doi                     TEXT,
    title                   TEXT NOT NULL,
    landing_page_url        TEXT,
    oa_url                  TEXT,

    publication_date        DATE NOT NULL,
    publication_year        SMALLINT NOT NULL,

    work_type               TEXT,
    language                TEXT,
    is_oa                   BOOLEAN NOT NULL DEFAULT FALSE,
    oa_status               TEXT,
    is_retracted            BOOLEAN NOT NULL DEFAULT FALSE,
    has_fulltext            BOOLEAN NOT NULL DEFAULT FALSE,

    primary_topic_id        TEXT,
    primary_topic_name      TEXT,
    primary_topic_score     NUMERIC(6, 5),
    subfield_id             TEXT,
    subfield_name           TEXT,
    field_name              TEXT,
    domain_name             TEXT,

    source_id               TEXT,
    source_name             TEXT,
    source_type             TEXT,
    host_organization       TEXT,
    is_core_source          BOOLEAN,

    cited_by_count          INTEGER NOT NULL DEFAULT 0,
    fwci                    NUMERIC(8, 4),
    citation_percentile     NUMERIC(8, 6),
    is_top_1_percent        BOOLEAN,
    is_top_10_percent       BOOLEAN,
    referenced_works_count  INTEGER NOT NULL DEFAULT 0,
    author_count            SMALLINT NOT NULL DEFAULT 0,
    countries_count         SMALLINT NOT NULL DEFAULT 0,
    institutions_count      SMALLINT NOT NULL DEFAULT 0,
    locations_count         SMALLINT NOT NULL DEFAULT 0,

    country_codes           TEXT[],

    openalex_updated_at     TIMESTAMPTZ,
    ingested_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_papers_pub_date ON ai_papers (publication_date);
CREATE INDEX IF NOT EXISTS idx_ai_papers_subfield ON ai_papers (subfield_name);
CREATE INDEX IF NOT EXISTS idx_ai_papers_topic ON ai_papers (primary_topic_name);
CREATE INDEX IF NOT EXISTS idx_ai_papers_oa_status ON ai_papers (oa_status);
"""

ROLLBACK = """
DROP INDEX IF EXISTS idx_ai_papers_oa_status;
DROP INDEX IF EXISTS idx_ai_papers_topic;
DROP INDEX IF EXISTS idx_ai_papers_subfield;
DROP INDEX IF EXISTS idx_ai_papers_pub_date;
DROP TABLE IF EXISTS ai_papers;
DROP TABLE IF EXISTS paper_ingest_runs;
"""

steps = [step(APPLY, ROLLBACK)]
