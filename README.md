# AI Market Data Pipeline

A Python pipeline that fetches recent Artificial Intelligence research papers from [OpenAlex](https://openalex.org/), stores flattened records in PostgreSQL, and prepares data for a tracking dashboard.

## Overview

The pipeline is orchestrated by the `DataPipeline` class in [`scripts/data_pipeline.py`](scripts/data_pipeline.py). It runs four stages end to end:

1. **Fetch** — Query OpenAlex for recent AI papers by subfield and publication date range.
2. **Migrate** — Ensure PostgreSQL tables exist via versioned yoyo migrations.
3. **Load** — Flatten nested OpenAlex work objects, deduplicate, and upsert into `ai_papers`.
4. **Validate** — Run SQL data-quality checks against `ai_papers` and fail on errors.

```mermaid
flowchart LR
    A[OpenAlex API] -->|DataPipeline.fetch| B[flatten_paper]
    E[apply_schema.py] -->|yoyo migrations| D[(PostgreSQL)]
    B -->|DataPipeline.ingest| D
    D -->|DataPipeline.run_dq| G[data_quality checks]
    A -.->|optional --save-json| C[JSON export in tmp/]
    C -.->|run_from_json| B
    D -->|Query| F[Streamlit Dashboard]
```

You can run all four stages with a single command via [`scripts/run_pipeline.py`](scripts/run_pipeline.py), or use the individual scripts (`list_ai_papers.py`, `load_ai_papers.py`, `apply_schema.py`) for step-by-step workflows.

## Features

- End-to-end pipeline via `DataPipeline` and `run_pipeline.py`
- Fetch recent AI papers from OpenAlex by subfield and publication date range
- Flatten nested OpenAlex JSON into a dashboard-friendly PostgreSQL schema
- Automatic schema setup on ingest (only applies pending migrations)
- SQL data-quality checks after load (uniqueness, format, consistency, domain rules)
- Two-layer deduplication: within each batch and on `openalex_id` in the database
- Idempotent re-runs via `ON CONFLICT DO UPDATE`
- Ingest run history tracked in `paper_ingest_runs`

## Tech Stack

| Layer        | Technology                          |
| ------------ | ----------------------------------- |
| Data source  | OpenAlex API (`pyalex`)             |
| Database     | PostgreSQL (Neon or other managed)  |
| Migrations   | yoyo-migrations                     |
| DB driver    | psycopg 3                           |
| Pipeline     | Python 3.9+                         |
| Dashboard    | Streamlit                           |

## Project Structure

```
ai-market-data-pipeline/
├── README.md
├── requirements.txt
├── yoyo.ini                         # yoyo migration config
├── db/
│   └── migrations/
│       └── 20260615_01_create_ai_papers.py
├── scripts/
│   ├── run_pipeline.py              # Full pipeline CLI (fetch → load → DQ)
│   ├── dashboard.py                 # Streamlit insights dashboard
│   ├── data_pipeline.py             # DataPipeline orchestration class
│   ├── data_quality.py              # SQL data-quality checks
│   ├── list_ai_papers.py            # Fetch papers from OpenAlex → JSON
│   ├── load_ai_papers.py            # Ingest JSON → PostgreSQL
│   ├── apply_schema.py              # Apply pending DB migrations
│   ├── flatten_paper.py             # OpenAlex work → flat row mapper
│   └── db_connection.py             # PostgreSQL connection helpers
└── tmp/                             # JSON exports (gitignored)
```

## Prerequisites

- **Python 3.9+**
- **PostgreSQL database** (e.g. Neon, Supabase, RDS)
- **OpenAlex API key** (optional, but recommended for higher rate limits)

## Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd ai-market-data-pipeline
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Always use the project venv at `.venv/` for pipeline commands.

### 3. Configure environment variables

Create a `.env` file in the project root:

| Variable           | Description                                           |
| ------------------ | ----------------------------------------------------- |
| `DATABASE_URL`     | Full PostgreSQL connection string (preferred)          |
| `DB_PASSWORD`      | Database password (if `DATABASE_URL` is not set)     |
| `DB_HOST`          | Database host (optional, has Neon default)           |
| `DB_USER`          | Database user (optional, has default)                |
| `DB_NAME`          | Database name (optional, has default)                |
| `OPENALEX_API_KEY` | OpenAlex API key (optional, improves rate limits)    |

Never commit `.env` or real credentials to version control.

### 4. Initialize the database

Apply migrations to create `ai_papers` and `paper_ingest_runs`:

```bash
.venv/bin/python scripts/apply_schema.py
```

Check migration status:

```bash
.venv/bin/python scripts/apply_schema.py --list
```

You do not need to run this manually before every ingest — `DataPipeline` and `load_ai_papers.py` call `apply_schema()` automatically and only apply pending migrations.

## Usage

### Run the full pipeline (recommended)

Fetch from OpenAlex, apply schema, load into PostgreSQL, and run data-quality checks:

```bash
.venv/bin/python scripts/run_pipeline.py
```

Fetch papers published today only:

```bash
.venv/bin/python scripts/run_pipeline.py --days-back 0
```

Also save a JSON export to `tmp/`:

```bash
.venv/bin/python scripts/run_pipeline.py --save-json
```

Load an existing JSON file and run data-quality checks (skip the OpenAlex fetch):

```bash
.venv/bin/python scripts/run_pipeline.py --json-path tmp/ai_papers_20260614_192257.json
```

| Flag | Description |
| ---- | ----------- |
| `--days-back N` | Publication date window (default: 3 days, use `0` for today only) |
| `--save-json` | Write the fetched batch to `tmp/` as JSON |
| `--json-path PATH` | Ingest from an existing export instead of fetching |
| `--skip-dq` | Skip data-quality checks (only with `--json-path`) |
| `--fail-on-warnings` | Treat warning-severity DQ checks as failures |

Example output:

```
Schema already up to date.
Fetched 6 papers (2026-06-18 to 2026-06-18)
Ingest run id: 3
Upserted 6 papers
Data quality checks:
  [PASS] (ERROR) duplicate_openalex_id: 0 violation(s)
  [PASS] (ERROR) openalex_id_format: 0 violation(s)
  ...
```

Error-severity checks cause a non-zero exit code. Warning-severity checks are reported but do not fail the run unless `--fail-on-warnings` is set.

### Streamlit dashboard

Launch the publications dashboard (connects to Neon via `db_connection`):

```bash
.venv/bin/streamlit run scripts/dashboard.py
```

The dashboard shows:

- Summary metrics (publication count, open-access rate, citations, topics)
- Publication trends over time (daily volume + 7-day rolling average)
- Breakdowns by topic, open-access status, venue, and country
- Filterable publications table with OpenAlex links
- Recent ingest run history

Use read-only database credentials for the dashboard when possible.

### Step-by-step workflow

Use these scripts when you want to inspect or archive the JSON export between fetch and load.

#### Step 1: Fetch papers from OpenAlex

Fetches recent Artificial Intelligence papers and writes a timestamped JSON file to `tmp/`:

```bash
.venv/bin/python scripts/list_ai_papers.py
```

Output example: `tmp/ai_papers_20260614_192257.json`

The JSON payload includes metadata (`fetched_at`, `date_range`, `subfield`) and a `papers` array of raw OpenAlex work objects.

#### Step 2: Load papers into PostgreSQL

Ingest a JSON export into the `ai_papers` table:

```bash
.venv/bin/python scripts/load_ai_papers.py tmp/ai_papers_20260614_192257.json
```

This script:

1. Calls `apply_schema()` to create tables if required
2. Connects to PostgreSQL via `db_connection.connect()`
3. Flattens each paper with `flatten_paper()`
4. Deduplicates records within the JSON file by `openalex_id`
5. Upserts rows into `ai_papers` using `ON CONFLICT (openalex_id) DO UPDATE`
6. Records the run in `paper_ingest_runs`

Example output:

```
Schema already up to date.
Source: tmp/ai_papers_20260614_192257.json
Ingest run id: 1
Upserted 2084 papers
```

Re-running the same file is safe: existing rows are updated, not duplicated.

### Programmatic usage

Run the full pipeline:

```python
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
from data_pipeline import DataPipeline

result = DataPipeline(days_back=0).run()
print(result.ingest.upserted, result.data_quality)
```

Or ingest from a JSON export:

```python
from pathlib import Path
from load_ai_papers import ingest_from_json

result = ingest_from_json(Path("tmp/ai_papers_20260614_192257.json"))
print(result.upserted, result.duplicates_in_file, result.skipped_invalid)
```

## Data Quality

Checks are defined in [`scripts/data_quality.py`](scripts/data_quality.py) and run automatically at the end of `run_pipeline.py`. Each check is a SQL query that returns violating rows; an empty result means pass.

| Check | Severity | What it validates |
| ----- | -------- | ----------------- |
| `duplicate_openalex_id` | error | No duplicate primary keys |
| `openalex_id_format` | error | IDs match `W[0-9]+` pattern |
| `publication_year_matches_date` | error | Year column matches `publication_date` |
| `ai_subfield` | error | `subfield_name` is Artificial Intelligence |
| `publication_date_sanity` | error | Dates are not in the future or before 1990 |
| `oa_flag_status_consistency` | error | `is_oa` and `oa_status` agree |
| `citation_percentile_hierarchy` | error | Top 1% papers are also top 10% |
| `non_negative_metrics` | error | Counts and scores are in valid ranges |
| `countries_count_matches_array` | error | `countries_count` matches `country_codes` length |
| `missing_topic_hierarchy` | warning | Topic hierarchy fields are populated |
| `ingest_count_reconciliation` | warning | Latest ingest count matches rows in date window |

## Database Schema

### `ai_papers`

Flattened paper records for dashboard queries. Key columns:

| Column               | Purpose                                      |
| -------------------- | -------------------------------------------- |
| `openalex_id`        | Primary key (deduplication key)              |
| `title`, `doi`       | Display and linking                          |
| `publication_date`   | Time-series charts                           |
| `primary_topic_name` | Topic breakdown                              |
| `subfield_name`      | AI subfield filter                           |
| `oa_status`, `is_oa` | Open-access analysis                         |
| `cited_by_count`     | Citation metrics                             |
| `source_name`        | Venue / publisher breakdown                  |

### `paper_ingest_runs`

Audit log of each JSON ingest (source date range, subfield, paper count).

### Migrations

Schema changes live in `db/migrations/` as yoyo migration files. To add a new migration, create a file such as:

```
db/migrations/20260620_02_add_column.py
```

Each file defines `steps = [step(apply_sql, rollback_sql)]`.

## Deduplication

| Layer              | Where                         | Behaviour                                      |
| ------------------ | ----------------------------- | ---------------------------------------------- |
| Within batch       | `DataPipeline._prepare_rows`  | Skips duplicate `openalex_id` in the same batch |
| Database           | `ai_papers` primary key       | `ON CONFLICT DO UPDATE` on re-ingest           |

## Security Notes

- Store database credentials in a secrets manager or platform env vars, not in source code.
- Use read-only database credentials for the Streamlit dashboard when possible.
- Prefer TLS-enabled PostgreSQL connections (`sslmode=require` in the connection string).
- Do not commit `.env` files containing passwords.

## License

Add your license here (e.g. MIT, Apache 2.0).
