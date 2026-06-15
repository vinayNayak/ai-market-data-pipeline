"""Flatten nested OpenAlex work objects into dashboard-ready rows."""

from __future__ import annotations

from typing import Any


def openalex_id(value: str | None) -> str | None:
    """Return the short OpenAlex ID (e.g. W7130905140) from a full URL."""
    if not value:
        return None
    return value.rsplit("/", 1)[-1]


def flatten_paper(paper: dict[str, Any]) -> dict[str, Any]:
    """Map a nested OpenAlex work dict to a flat row for ai_papers."""
    oa = paper.get("open_access") or {}
    location = paper.get("primary_location") or {}
    source = location.get("source") or {}
    topic = paper.get("primary_topic") or {}
    percentile = paper.get("citation_normalized_percentile") or {}

    countries = sorted(
        {
            country
            for authorship in paper.get("authorships") or []
            for country in authorship.get("countries") or []
        }
    )

    work_id = openalex_id(paper.get("id"))
    if not work_id:
        raise ValueError("Paper is missing a valid OpenAlex id")

    title = paper.get("title") or paper.get("display_name")
    if not title:
        raise ValueError(f"Paper {work_id} is missing title and display_name")

    publication_date = paper.get("publication_date")
    publication_year = paper.get("publication_year")
    if not publication_date or publication_year is None:
        raise ValueError(f"Paper {work_id} is missing publication_date or publication_year")

    return {
        "openalex_id": work_id,
        "doi": paper.get("doi"),
        "title": title,
        "landing_page_url": location.get("landing_page_url"),
        "oa_url": oa.get("oa_url"),
        "publication_date": publication_date,
        "publication_year": publication_year,
        "work_type": paper.get("type"),
        "language": paper.get("language"),
        "is_oa": bool(oa.get("is_oa")),
        "oa_status": oa.get("oa_status"),
        "is_retracted": bool(paper.get("is_retracted")),
        "has_fulltext": bool(paper.get("has_fulltext")),
        "primary_topic_id": openalex_id(topic.get("id")),
        "primary_topic_name": topic.get("display_name"),
        "primary_topic_score": topic.get("score"),
        "subfield_id": openalex_id((topic.get("subfield") or {}).get("id")),
        "subfield_name": (topic.get("subfield") or {}).get("display_name"),
        "field_name": (topic.get("field") or {}).get("display_name"),
        "domain_name": (topic.get("domain") or {}).get("display_name"),
        "source_id": openalex_id(source.get("id")),
        "source_name": source.get("display_name"),
        "source_type": source.get("type"),
        "host_organization": source.get("host_organization_name"),
        "is_core_source": source.get("is_core"),
        "cited_by_count": paper.get("cited_by_count") or 0,
        "fwci": paper.get("fwci"),
        "citation_percentile": percentile.get("value"),
        "is_top_1_percent": percentile.get("is_in_top_1_percent"),
        "is_top_10_percent": percentile.get("is_in_top_10_percent"),
        "referenced_works_count": paper.get("referenced_works_count") or 0,
        "author_count": len(paper.get("authorships") or []),
        "countries_count": paper.get("countries_distinct_count") or 0,
        "institutions_count": paper.get("institutions_distinct_count") or 0,
        "locations_count": paper.get("locations_count") or 0,
        "country_codes": countries or None,
        "openalex_updated_at": paper.get("updated_date"),
    }


FLAT_COLUMNS: tuple[str, ...] = (
    "openalex_id",
    "doi",
    "title",
    "landing_page_url",
    "oa_url",
    "publication_date",
    "publication_year",
    "work_type",
    "language",
    "is_oa",
    "oa_status",
    "is_retracted",
    "has_fulltext",
    "primary_topic_id",
    "primary_topic_name",
    "primary_topic_score",
    "subfield_id",
    "subfield_name",
    "field_name",
    "domain_name",
    "source_id",
    "source_name",
    "source_type",
    "host_organization",
    "is_core_source",
    "cited_by_count",
    "fwci",
    "citation_percentile",
    "is_top_1_percent",
    "is_top_10_percent",
    "referenced_works_count",
    "author_count",
    "countries_count",
    "institutions_count",
    "locations_count",
    "country_codes",
    "openalex_updated_at",
)
