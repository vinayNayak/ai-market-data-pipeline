"""Display titles of 5 AI-related papers from OpenAlex."""

import os

import pyalex
from pyalex import Works

PAPER_COUNT = 5
SEARCH_QUERY = "artificial intelligence"


def configure_openalex() -> None:
    api_key = os.getenv("OPENALEX_API_KEY")
    if api_key:
        pyalex.config.api_key = api_key


def fetch_ai_paper_titles(limit: int = PAPER_COUNT) -> list[str]:
    papers = Works().search(SEARCH_QUERY).get(per_page=limit)
    return [paper.get("title") or "Untitled" for paper in papers]


def main() -> None:
    configure_openalex()
    titles = fetch_ai_paper_titles()

    if not titles:
        print("No AI papers found.")
        return

    for index, title in enumerate(titles, start=1):
        print(f"{index}. {title}")


if __name__ == "__main__":
    main()
