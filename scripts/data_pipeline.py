"""End-to-end AI papers data pipeline: fetch, migrate, load, and validate."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pyalex
from pyalex import Subfields, Works

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from apply_schema import DEFAULT_MIGRATIONS_DIR, apply_schema
from data_quality import (
    DataQualityResult,
    assert_data_quality,
    run_data_quality_checks,
)
from db_connection import PROJECT_ROOT, connect
from flatten_paper import FLAT_COLUMNS, flatten_paper

DEFAULT_SUBFIELD_SEARCH = "Artificial Intelligence"
DEFAULT_DAYS_BACK = 3
DEFAULT_BATCH_SIZE = 500
DEFAULT_TMP_DIR = PROJECT_ROOT / "tmp"

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
class FetchResult:
    papers: list[dict]
    subfield: dict
    from_date: str
    to_date: str
    duplicates_skipped: int
    fetched_at: str


@dataclass
class IngestResult:
    ingest_run_id: int
    upserted: int
    skipped_invalid: int
    duplicates_in_file: int


@dataclass
class PipelineResult:
    migrations_applied: list[str]
    fetch: FetchResult | None
    ingest: IngestResult | None
    data_quality: list[DataQualityResult]
    json_path: Path | None = None


class DataPipeline:
    """Fetch OpenAlex AI papers, ensure schema, load into PostgreSQL, and validate."""

    def __init__(
        self,
        *,
        days_back: int = DEFAULT_DAYS_BACK,
        subfield_search: str = DEFAULT_SUBFIELD_SEARCH,
        migrations_dir: Path = DEFAULT_MIGRATIONS_DIR,
        tmp_dir: Path = DEFAULT_TMP_DIR,
        batch_size: int = DEFAULT_BATCH_SIZE,
        fail_on_dq_errors: bool = True,
        fail_on_dq_warnings: bool = False,
    ) -> None:
        self.days_back = days_back
        self.subfield_search = subfield_search
        self.migrations_dir = migrations_dir
        self.tmp_dir = tmp_dir
        self.batch_size = batch_size
        self.fail_on_dq_errors = fail_on_dq_errors
        self.fail_on_dq_warnings = fail_on_dq_warnings

    def ensure_schema(self) -> list[str]:
        """Apply pending database migrations."""
        return apply_schema(self.migrations_dir)

    def configure_openalex(self) -> None:
        api_key = os.getenv("OPENALEX_API_KEY")
        if api_key:
            pyalex.config.api_key = api_key

    def publication_date_range(self) -> tuple[str, str]:
        today = date.today()
        from_date = today - timedelta(days=self.days_back)
        return from_date.isoformat(), today.isoformat()

    def find_subfield(self) -> dict:
        subfields = Subfields().search(self.subfield_search).get(per_page=25)
        if not subfields:
            raise RuntimeError(f"No OpenAlex subfields found for '{self.subfield_search}'")

        for subfield in subfields:
            if subfield.get("display_name", "").lower() == self.subfield_search.lower():
                return dict(subfield)

        raise RuntimeError(
            f"No exact OpenAlex subfield match for '{self.subfield_search}'. "
            f"Top result was '{subfields[0].get('display_name')}'."
        )

    def fetch_recent_papers(self) -> FetchResult:
        """Query OpenAlex for recent AI papers and validate subfield classification."""
        self.configure_openalex()

        subfield = self.find_subfield()
        from_date, to_date = self.publication_date_range()
        papers, duplicates_skipped = self._fetch_papers(subfield["id"], from_date, to_date)
        self._validate_papers(papers)

        return FetchResult(
            papers=papers,
            subfield=subfield,
            from_date=from_date,
            to_date=to_date,
            duplicates_skipped=duplicates_skipped,
            fetched_at=datetime.now().isoformat(timespec="seconds"),
        )

    def save_to_json(self, fetch: FetchResult) -> Path:
        """Write a fetched batch to tmp/ as a JSON export."""
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = self.tmp_dir / f"ai_papers_{timestamp}.json"

        payload = self._build_payload(fetch)
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False)
            file.write("\n")

        return output_path

    def ingest_papers(self, payload: dict) -> IngestResult:
        """Flatten, deduplicate, and upsert papers; record an ingest run."""
        papers = payload.get("papers") or []
        rows, skipped_invalid, duplicates_in_file = self._prepare_rows(papers)

        with connect() as conn:
            upserted = self._upsert_rows(conn, rows)
            ingest_run_id = self._record_ingest_run(conn, payload, len(papers))
            conn.commit()

        return IngestResult(
            ingest_run_id=ingest_run_id,
            upserted=upserted,
            skipped_invalid=skipped_invalid,
            duplicates_in_file=duplicates_in_file,
        )

    def ingest_from_json(self, json_path: Path) -> IngestResult:
        """Load papers from a JSON export file."""
        json_path = json_path.resolve()
        payload = self._load_payload(json_path)
        return self.ingest_papers(payload)

    def run_data_quality_checks(self) -> list[DataQualityResult]:
        """Execute SQL data-quality checks against ai_papers."""
        with connect() as conn:
            return run_data_quality_checks(conn)

    def run(self, *, save_json: bool = False) -> PipelineResult:
        """Run the full pipeline: schema, fetch, load, and data-quality checks."""
        migrations_applied = self.ensure_schema()
        fetch_result = self.fetch_recent_papers()

        json_path = self.save_to_json(fetch_result) if save_json else None
        ingest_result = self.ingest_papers(self._build_payload(fetch_result))
        dq_results = self.run_data_quality_checks()

        if self.fail_on_dq_errors or self.fail_on_dq_warnings:
            assert_data_quality(
                dq_results,
                fail_on_warnings=self.fail_on_dq_warnings,
            )

        return PipelineResult(
            migrations_applied=migrations_applied,
            fetch=fetch_result,
            ingest=ingest_result,
            data_quality=dq_results,
            json_path=json_path,
        )

    def run_from_json(
        self,
        json_path: Path,
        *,
        run_data_quality: bool = True,
    ) -> PipelineResult:
        """Ensure schema, ingest from JSON, and optionally run data-quality checks."""
        migrations_applied = self.ensure_schema()
        ingest_result = self.ingest_from_json(json_path)
        dq_results = self.run_data_quality_checks() if run_data_quality else []

        if run_data_quality and (self.fail_on_dq_errors or self.fail_on_dq_warnings):
            assert_data_quality(
                dq_results,
                fail_on_warnings=self.fail_on_dq_warnings,
            )

        return PipelineResult(
            migrations_applied=migrations_applied,
            fetch=None,
            ingest=ingest_result,
            data_quality=dq_results,
            json_path=json_path.resolve(),
        )

    def _fetch_papers(
        self,
        subfield_id: str,
        from_date: str,
        to_date: str,
    ) -> tuple[list[dict], int]:
        query = (
            Works()
            .filter(
                primary_topic={"subfield": {"id": subfield_id}},
                from_publication_date=from_date,
                to_publication_date=to_date,
            )
            .sort(publication_date="desc")
        )

        papers: list[dict] = []
        seen_ids: set[str] = set()
        duplicates_skipped = 0

        for page in query.paginate(per_page=200, n_max=None):
            for paper in page:
                paper_id = paper.get("id")
                if paper_id:
                    if paper_id in seen_ids:
                        duplicates_skipped += 1
                        continue
                    seen_ids.add(paper_id)
                papers.append(dict(paper))

        return papers, duplicates_skipped

    def _validate_papers(self, papers: list[dict]) -> None:
        mismatches = []
        for paper in papers:
            subfield = (paper.get("primary_topic") or {}).get("subfield") or {}
            if subfield.get("display_name", "").lower() != self.subfield_search.lower():
                mismatches.append(
                    {
                        "id": paper.get("id"),
                        "title": paper.get("title"),
                        "primary_subfield": subfield.get("display_name"),
                    }
                )

        if mismatches:
            sample = mismatches[:3]
            raise RuntimeError(
                f"{len(mismatches)} papers are not primarily classified as "
                f"{self.subfield_search!r}. Examples: {sample}"
            )

    def _build_payload(self, fetch: FetchResult) -> dict:
        return {
            "fetched_at": fetch.fetched_at,
            "filters": {
                "primary_topic.subfield.id": fetch.subfield["id"],
                "from_publication_date": fetch.from_date,
                "to_publication_date": fetch.to_date,
            },
            "subfield": fetch.subfield,
            "date_range": {"from": fetch.from_date, "to": fetch.to_date},
            "count": len(fetch.papers),
            "duplicates_skipped": fetch.duplicates_skipped,
            "papers": fetch.papers,
        }

    def _load_payload(self, path: Path) -> dict:
        if not path.is_file():
            raise FileNotFoundError(f"JSON file not found: {path}")

        with path.open(encoding="utf-8") as file:
            return json.load(file)

    def _prepare_rows(self, papers: list[dict]) -> tuple[list[dict], int, int]:
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

    def _upsert_rows(self, conn, rows: list[dict]) -> int:
        if not rows:
            return 0

        with conn.cursor() as cur:
            for offset in range(0, len(rows), self.batch_size):
                batch = rows[offset : offset + self.batch_size]
                cur.executemany(UPSERT_SQL, batch)

        return len(rows)

    def _record_ingest_run(self, conn, payload: dict, paper_count: int) -> int:
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
