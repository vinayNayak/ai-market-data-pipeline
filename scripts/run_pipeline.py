"""Run the full AI papers data pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from data_pipeline import DataPipeline
from data_quality import DataQualityError


def print_pipeline_result(result) -> None:
    if result.migrations_applied:
        print("Applied migrations:")
        for migration_id in result.migrations_applied:
            print(f"  - {migration_id}")
    else:
        print("Schema already up to date.")

    if result.fetch:
        fetch = result.fetch
        duplicate_note = (
            f" ({fetch.duplicates_skipped} duplicates skipped)"
            if fetch.duplicates_skipped
            else ""
        )
        print(
            f"Fetched {len(fetch.papers)} papers "
            f"({fetch.from_date} to {fetch.to_date}){duplicate_note}"
        )

    if result.json_path:
        print(f"Saved JSON export: {result.json_path}")

    if result.ingest:
        ingest = result.ingest
        print(f"Ingest run id: {ingest.ingest_run_id}")
        print(f"Upserted {ingest.upserted} papers")
        if ingest.duplicates_in_file:
            print(f"Deduplicated {ingest.duplicates_in_file} duplicate(s) in batch")
        if ingest.skipped_invalid:
            print(f"Skipped {ingest.skipped_invalid} invalid paper(s)")

    if result.data_quality:
        print("Data quality checks:")
        for dq in result.data_quality:
            status = "PASS" if dq.violation_count == 0 else "FAIL"
            severity = dq.check.severity.upper()
            print(
                f"  [{status}] ({severity}) {dq.check.name}: "
                f"{dq.violation_count} violation(s)"
            )
            if dq.sample_rows:
                for row in dq.sample_rows:
                    print(f"    sample: {row}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the AI papers data pipeline: fetch from OpenAlex, "
            "apply schema, load into PostgreSQL, and run data-quality checks."
        )
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=3,
        help="Number of days of publication history to fetch (default: 3)",
    )
    parser.add_argument(
        "--save-json",
        action="store_true",
        help="Also write the fetched batch to tmp/ as JSON",
    )
    parser.add_argument(
        "--json-path",
        type=Path,
        help="Skip fetch; ingest from an existing JSON export instead",
    )
    parser.add_argument(
        "--skip-dq",
        action="store_true",
        help="Skip data-quality checks (only with --json-path)",
    )
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Treat warning-severity data-quality checks as failures",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pipeline = DataPipeline(
        days_back=args.days_back,
        fail_on_dq_warnings=args.fail_on_warnings,
    )

    try:
        if args.json_path:
            result = pipeline.run_from_json(
                args.json_path,
                run_data_quality=not args.skip_dq,
            )
        else:
            result = pipeline.run(save_json=args.save_json)
    except DataQualityError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 1

    print_pipeline_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
