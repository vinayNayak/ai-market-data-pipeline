"""SQL data-quality checks for the ai_papers table."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from psycopg import Connection

Severity = Literal["error", "warning"]
SAMPLE_LIMIT = 5


@dataclass(frozen=True)
class DataQualityCheck:
    name: str
    description: str
    sql: str
    severity: Severity = "error"


@dataclass
class DataQualityResult:
    check: DataQualityCheck
    violation_count: int
    sample_rows: list[tuple]


DATA_QUALITY_CHECKS: tuple[DataQualityCheck, ...] = (
    DataQualityCheck(
        name="duplicate_openalex_id",
        description="No duplicate openalex_id values",
        sql="""
            SELECT openalex_id, COUNT(*) AS cnt
            FROM ai_papers
            GROUP BY openalex_id
            HAVING COUNT(*) > 1
        """,
    ),
    DataQualityCheck(
        name="openalex_id_format",
        description="openalex_id matches W-prefixed numeric pattern",
        sql="""
            SELECT openalex_id, title
            FROM ai_papers
            WHERE openalex_id !~ '^W[0-9]+$'
        """,
    ),
    DataQualityCheck(
        name="publication_year_matches_date",
        description="publication_year matches publication_date",
        sql="""
            SELECT openalex_id, publication_date, publication_year
            FROM ai_papers
            WHERE publication_year <> EXTRACT(YEAR FROM publication_date)::SMALLINT
        """,
    ),
    DataQualityCheck(
        name="ai_subfield",
        description="subfield_name is Artificial Intelligence",
        sql="""
            SELECT openalex_id, title, subfield_name, subfield_id
            FROM ai_papers
            WHERE subfield_name IS DISTINCT FROM 'Artificial Intelligence'
        """,
    ),
    DataQualityCheck(
        name="publication_date_sanity",
        description="publication_date is not in the future and not before 1990",
        sql="""
            SELECT openalex_id, publication_date
            FROM ai_papers
            WHERE publication_date > CURRENT_DATE
               OR publication_date < DATE '1990-01-01'
        """,
    ),
    DataQualityCheck(
        name="oa_flag_status_consistency",
        description="is_oa and oa_status are consistent",
        sql="""
            SELECT openalex_id, is_oa, oa_status
            FROM ai_papers
            WHERE (is_oa = TRUE AND (oa_status IS NULL OR oa_status = 'closed'))
               OR (is_oa = FALSE AND oa_status IN ('gold', 'green', 'hybrid', 'bronze', 'diamond'))
        """,
    ),
    DataQualityCheck(
        name="citation_percentile_hierarchy",
        description="top 1% papers are also in top 10%",
        sql="""
            SELECT openalex_id, is_top_1_percent, is_top_10_percent, citation_percentile
            FROM ai_papers
            WHERE is_top_1_percent = TRUE
              AND (is_top_10_percent IS DISTINCT FROM TRUE)
        """,
    ),
    DataQualityCheck(
        name="non_negative_metrics",
        description="counts and scores are within valid ranges",
        sql="""
            SELECT openalex_id, cited_by_count, referenced_works_count, author_count,
                   fwci, citation_percentile, primary_topic_score
            FROM ai_papers
            WHERE cited_by_count < 0
               OR referenced_works_count < 0
               OR author_count < 0
               OR fwci < 0
               OR citation_percentile NOT BETWEEN 0 AND 1
               OR primary_topic_score NOT BETWEEN 0 AND 1
        """,
    ),
    DataQualityCheck(
        name="countries_count_matches_array",
        description="countries_count matches country_codes array length",
        sql="""
            SELECT openalex_id, countries_count, country_codes,
                   CARDINALITY(country_codes) AS array_len
            FROM ai_papers
            WHERE country_codes IS NOT NULL
              AND countries_count <> CARDINALITY(country_codes)
        """,
    ),
    DataQualityCheck(
        name="missing_topic_hierarchy",
        description="primary topic hierarchy fields are populated",
        severity="warning",
        sql="""
            SELECT openalex_id, title, primary_topic_name, subfield_name, field_name
            FROM ai_papers
            WHERE primary_topic_name IS NULL
               OR subfield_name IS NULL
               OR field_name IS NULL
        """,
    ),
    DataQualityCheck(
        name="ingest_count_reconciliation",
        description="latest ingest run paper_count roughly matches rows in date window",
        severity="warning",
        sql="""
            WITH latest_run AS (
                SELECT id, from_date, to_date, paper_count
                FROM paper_ingest_runs
                ORDER BY id DESC
                LIMIT 1
            ),
            loaded_in_window AS (
                SELECT COUNT(*) AS cnt
                FROM ai_papers p, latest_run r
                WHERE p.publication_date BETWEEN r.from_date AND r.to_date
            )
            SELECT r.paper_count AS expected_from_export,
                   l.cnt AS rows_in_date_window,
                   (SELECT COUNT(*) FROM ai_papers) AS total_rows
            FROM latest_run r, loaded_in_window l
            WHERE l.cnt = 0
               OR ABS(l.cnt - r.paper_count) > GREATEST(r.paper_count * 0.05, 1)
        """,
    ),
)


class DataQualityError(RuntimeError):
    """Raised when one or more error-severity data-quality checks fail."""

    def __init__(self, failures: list[DataQualityResult]) -> None:
        self.failures = failures
        lines = [
            f"{result.check.name}: {result.violation_count} violation(s)"
            for result in failures
        ]
        super().__init__("Data quality checks failed:\n" + "\n".join(lines))


def run_data_quality_checks(
    conn: Connection,
    *,
    checks: tuple[DataQualityCheck, ...] = DATA_QUALITY_CHECKS,
    sample_limit: int = SAMPLE_LIMIT,
) -> list[DataQualityResult]:
    """Run SQL checks and return results with violation counts and sample rows."""
    results: list[DataQualityResult] = []

    with conn.cursor() as cur:
        for check in checks:
            cur.execute(f"SELECT COUNT(*) FROM ({check.sql}) AS violations")
            violation_count = cur.fetchone()[0]

            sample_rows: list[tuple] = []
            if violation_count:
                cur.execute(
                    f"SELECT * FROM ({check.sql}) AS violations LIMIT %s",
                    (sample_limit,),
                )
                sample_rows = [tuple(row) for row in cur.fetchall()]

            results.append(
                DataQualityResult(
                    check=check,
                    violation_count=violation_count,
                    sample_rows=sample_rows,
                )
            )

    return results


def assert_data_quality(
    results: list[DataQualityResult],
    *,
    fail_on_warnings: bool = False,
) -> None:
    """Raise DataQualityError if any checks of the configured severity fail."""
    failures = [
        result
        for result in results
        if result.violation_count > 0
        and (result.check.severity == "error" or fail_on_warnings)
    ]
    if failures:
        raise DataQualityError(failures)
