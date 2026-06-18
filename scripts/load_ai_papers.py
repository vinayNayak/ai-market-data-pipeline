"""Ingest AI papers from a JSON export into PostgreSQL with schema setup and deduplication."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from data_pipeline import DataPipeline


@dataclass
class IngestResult:
    json_path: Path
    ingest_run_id: int
    upserted: int
    skipped_invalid: int
    duplicates_in_file: int
    migrations_applied: list[str]


def ingest_from_json(json_path: Path) -> IngestResult:
    """Ensure schema, connect, flatten, deduplicate, and upsert AI papers."""
    pipeline = DataPipeline(fail_on_dq_errors=False)
    result = pipeline.run_from_json(json_path, run_data_quality=False)
    ingest = result.ingest
    if ingest is None:
        raise RuntimeError("Ingest did not produce a result")

    return IngestResult(
        json_path=result.json_path or json_path.resolve(),
        ingest_run_id=ingest.ingest_run_id,
        upserted=ingest.upserted,
        skipped_invalid=ingest.skipped_invalid,
        duplicates_in_file=ingest.duplicates_in_file,
        migrations_applied=result.migrations_applied,
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
