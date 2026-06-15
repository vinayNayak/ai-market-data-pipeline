"""Fetch recent Artificial Intelligence papers from OpenAlex and save to JSON."""

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pyalex
from pyalex import Subfields, Works

SUBFIELD_SEARCH = "Artificial Intelligence"
DAYS_BACK = 3
TMP_DIR = Path(__file__).resolve().parent.parent / "tmp"


def configure_openalex() -> None:
    api_key = os.getenv("OPENALEX_API_KEY")
    if api_key:
        pyalex.config.api_key = api_key


def find_ai_subfield() -> dict:
    """Resolve the OpenAlex Artificial Intelligence subfield (exact name match)."""
    subfields = Subfields().search(SUBFIELD_SEARCH).get(per_page=25)
    if not subfields:
        raise RuntimeError(f"No OpenAlex subfields found for '{SUBFIELD_SEARCH}'")

    for subfield in subfields:
        if subfield.get("display_name", "").lower() == SUBFIELD_SEARCH.lower():
            return dict(subfield)

    raise RuntimeError(
        f"No exact OpenAlex subfield match for '{SUBFIELD_SEARCH}'. "
        f"Top result was '{subfields[0].get('display_name')}'."
    )


def publication_date_range(days_back: int = DAYS_BACK) -> tuple[str, str]:
    today = date.today()
    from_date = today - timedelta(days=days_back)
    return from_date.isoformat(), today.isoformat()


def fetch_recent_ai_papers(subfield_id: str, from_date: str, to_date: str) -> tuple[list[dict], int]:
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


def validate_ai_papers(papers: list[dict], expected_subfield: str) -> None:
    """Confirm every paper's primary topic is classified under Artificial Intelligence."""
    mismatches = []
    for paper in papers:
        subfield = (paper.get("primary_topic") or {}).get("subfield") or {}
        if subfield.get("display_name", "").lower() != expected_subfield.lower():
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
            f"{expected_subfield!r}. Examples: {sample}"
        )


def save_papers(
    papers: list[dict],
    subfield: dict,
    from_date: str,
    to_date: str,
    duplicates_skipped: int = 0,
) -> Path:
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = TMP_DIR / f"ai_papers_{timestamp}.json"

    payload = {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "filters": {
            "primary_topic.subfield.id": subfield["id"],
            "from_publication_date": from_date,
            "to_publication_date": to_date,
        },
        "subfield": subfield,
        "date_range": {"from": from_date, "to": to_date},
        "count": len(papers),
        "duplicates_skipped": duplicates_skipped,
        "papers": papers,
    }

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)
        file.write("\n")

    return output_path


def main() -> None:
    configure_openalex()

    subfield = find_ai_subfield()
    subfield_id = subfield["id"]
    from_date, to_date = publication_date_range()

    print(f"Subfield: {subfield.get('display_name')} ({subfield_id})")
    print(f"Filters: primary_topic.subfield.id, from_publication_date, to_publication_date")
    print(f"Date range: {from_date} to {to_date}")

    papers, duplicates_skipped = fetch_recent_ai_papers(subfield_id, from_date, to_date)
    validate_ai_papers(papers, SUBFIELD_SEARCH)
    output_path = save_papers(
        papers, subfield, from_date, to_date, duplicates_skipped=duplicates_skipped
    )

    duplicate_note = f" ({duplicates_skipped} duplicates skipped)" if duplicates_skipped else ""
    print(f"Validated {len(papers)} AI papers{duplicate_note} -> {output_path}")


if __name__ == "__main__":
    main()
