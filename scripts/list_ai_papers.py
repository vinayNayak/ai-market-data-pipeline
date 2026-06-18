"""Fetch recent Artificial Intelligence papers from OpenAlex and save to JSON."""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from data_pipeline import DEFAULT_DAYS_BACK, DEFAULT_SUBFIELD_SEARCH, DataPipeline

SUBFIELD_SEARCH = DEFAULT_SUBFIELD_SEARCH
DAYS_BACK = DEFAULT_DAYS_BACK
TMP_DIR = DataPipeline().tmp_dir


def main() -> None:
    pipeline = DataPipeline(days_back=DAYS_BACK, subfield_search=SUBFIELD_SEARCH)
    fetch_result = pipeline.fetch_recent_papers()
    output_path = pipeline.save_to_json(fetch_result)

    subfield = fetch_result.subfield
    print(f"Subfield: {subfield.get('display_name')} ({subfield.get('id')})")
    print("Filters: primary_topic.subfield.id, from_publication_date, to_publication_date")
    print(f"Date range: {fetch_result.from_date} to {fetch_result.to_date}")

    duplicate_note = (
        f" ({fetch_result.duplicates_skipped} duplicates skipped)"
        if fetch_result.duplicates_skipped
        else ""
    )
    print(f"Validated {len(fetch_result.papers)} AI papers{duplicate_note} -> {output_path}")


if __name__ == "__main__":
    main()
