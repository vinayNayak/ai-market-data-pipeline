"""Ingest AI papers from a JSON export into PostgreSQL with schema setup and deduplication."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from apply_schema import apply_schema
from db_connection import connect
from flatten_paper import FLAT_COLUMNS, flatten_paper

BATCH_SIZE = 500

UPSERT_SQL = f"""
INSERT INTO ai_papers ({", ".join(FLAT_COLUMNS)})
VALUES ({", ".join(f"%({col})s" for col in FLAT_COLUMNS)})
ON CONFLICT (openalex_id) DO UPDATE SET
{", ".join(f"  {col} = EXCLUDED.{col}" for col in FLAT_COLUMNS if col != "openalex_id")}
"""

INGEST_RUN_SQL = """
INSERT INTO paper_ingest_runs (fetched_at, from_date, to_date, subfield_id, paper_count)
VALUES (%(fetched_at)s, %(from_date)s, %(to_date)s, %(subfield_id)s, %(paper_count)s)
RETURNING id
"""


@dataclass
class IngestResult:
    json_path: Path
    ingest_run_id: int
    upserted: int
    skipped_invalid: int
    duplicates_in_file: int
    migrations_applied: list[str]


def load_payload(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"JSON file not found: {path}")

    with path.open(encoding="utf-8") as file:
        return json.load(file)


def prepare_rows(papers: list[dict]) -> tuple[list[dict], int, int]:
    """Flatten papers, skip invalid rows, and deduplicate by openalex_id within the file."""
    rows: list[dict] = []
    seen_ids: set[str] = set()
    skipped_invalid = 0
    duplicates_in_file = 0

    for paper in papers:
        try:
            row = flatten_paper(paper)
        except ValueError as exc:
            skipped_invalid += 1
            print(f"Skipping invalid paper: {exc}", file=sys.stderr)
            continue

        openalex_id = row["openalex_id"]
        if openalex_id in seen_ids:
            duplicates_in_file += 1
            continue

        seen_ids.add(openalex_id)
        rows.append(row)

    return rows, skipped_invalid, duplicates_in_file


def upsert_rows(conn, rows: list[dict]) -> int:
    """Upsert flattened rows into ai_papers, deduplicating on openalex_id."""
    if not rows:
        return 0

    with conn.cursor() as cur:
        for offset in range(0, len(rows), BATCH_SIZE):
            batch = rows[offset : offset + BATCH_SIZE]
            cur.executemany(UPSERT_SQL, batch)

    return len(rows)


def record_ingest_run(conn, payload: dict, paper_count: int) -> int:
    date_range = payload.get("date_range") or {}
    subfield = payload.get("subfield") or {}

    with conn.cursor() as cur:
        cur.execute(
            INGEST_RUN_SQL,
            {
                "fetched_at": payload.get("fetched_at"),
                "from_date": date_range.get("from"),
                "to_date": date_range.get("to"),
                "subfield_id": subfield.get("id"),
                "paper_count": paper_count,
            },
        )
        return cur.fetchone()[0]


def ingest_from_json(json_path: Path) -> IngestResult:
    """Ensure schema, connect, flatten, deduplicate, and upsert AI papers."""
    json_path = json_path.resolve()
    migrations_applied = apply_schema()
    payload = load_payload(json_path)
    papers = payload.get("papers") or []

    rows, skipped_invalid, duplicates_in_file = prepare_rows(papers)

    with connect() as conn:
        upserted = upsert_rows(conn, rows)
        ingest_run_id = record_ingest_run(conn, payload, len(papers))
        conn.commit()

    return IngestResult(
        json_path=json_path,
        ingest_run_id=ingest_run_id,
        upserted=upserted,
        skipped_invalid=skipped_invalid,
        duplicates_in_file=duplicates_in_file,
        migrations_applied=migrations_applied,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest AI papers from an OpenAlex JSON export into PostgreSQL. "
            "Creates ai_papers when needed and deduplicates on openalex_id."
        )
    )
    parser.add_argument(
        "json_path",
        type=Path,
        help="Path to ai_papers export JSON file",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        result = ingest_from_json(args.json_path)
    except Exception as exc:
        print(f"Ingest failed: {exc}", file=sys.stderr)
        return 1

    if result.migrations_applied:
        print("Applied migrations:")
        for migration_id in result.migrations_applied:
            print(f"  - {migration_id}")
    else:
        print("Schema already up to date.")

    print(f"Source: {result.json_path}")
    print(f"Ingest run id: {result.ingest_run_id}")
    print(f"Upserted {result.upserted} papers")
    if result.duplicates_in_file:
        print(f"Deduplicated {result.duplicates_in_file} duplicate(s) in JSON file")
    if result.skipped_invalid:
        print(f"Skipped {result.skipped_invalid} invalid paper(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
