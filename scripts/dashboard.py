"""Streamlit dashboard for AI publication insights from Neon PostgreSQL."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from dataclasses import dataclass

import pandas as pd
import streamlit as st

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from db_connection import connect

FILTER_WHERE = """
publication_date BETWEEN %(from_date)s AND %(to_date)s
AND (
    array_length(%(topics)s::text[], 1) IS NULL
    OR primary_topic_name = ANY(%(topics)s::text[])
)
AND (%(oa_only)s = FALSE OR is_oa = TRUE)
"""

PAPERS_QUERY = f"""
SELECT
    openalex_id,
    doi,
    title,
    landing_page_url,
    oa_url,
    publication_date,
    publication_year,
    work_type,
    language,
    is_oa,
    oa_status,
    is_retracted,
    has_fulltext,
    primary_topic_name,
    primary_topic_score,
    subfield_name,
    field_name,
    source_name,
    source_type,
    host_organization,
    cited_by_count,
    fwci,
    author_count,
    countries_count,
    institutions_count,
    country_codes,
    ingested_at
FROM ai_papers
WHERE {FILTER_WHERE}
ORDER BY publication_date DESC, cited_by_count DESC
"""

PUBLICATIONS_BY_DATE_QUERY = f"""
SELECT publication_date, COUNT(*) AS papers
FROM ai_papers
WHERE {FILTER_WHERE}
GROUP BY publication_date
ORDER BY publication_date
"""

TOP_TOPICS_QUERY = f"""
SELECT primary_topic_name AS topic, COUNT(*) AS papers
FROM ai_papers
WHERE {FILTER_WHERE}
  AND primary_topic_name IS NOT NULL
GROUP BY primary_topic_name
ORDER BY papers DESC
LIMIT 10
"""

OA_STATUS_QUERY = f"""
SELECT COALESCE(oa_status, 'unknown') AS oa_status, COUNT(*) AS papers
FROM ai_papers
WHERE {FILTER_WHERE}
GROUP BY COALESCE(oa_status, 'unknown')
ORDER BY papers DESC
"""

TOP_VENUES_QUERY = f"""
SELECT COALESCE(source_name, 'Unknown') AS venue, COUNT(*) AS papers
FROM ai_papers
WHERE {FILTER_WHERE}
GROUP BY COALESCE(source_name, 'Unknown')
ORDER BY papers DESC
LIMIT 10
"""

TOP_COUNTRIES_QUERY = f"""
SELECT country, COUNT(*) AS papers
FROM ai_papers,
     LATERAL UNNEST(COALESCE(country_codes, ARRAY[]::TEXT[])) AS country
WHERE {FILTER_WHERE}
GROUP BY country
ORDER BY papers DESC
LIMIT 10
"""

INGEST_RUNS_QUERY = """
SELECT id, fetched_at, from_date, to_date, paper_count, created_at
FROM paper_ingest_runs
ORDER BY id DESC
LIMIT 5
"""

DATE_BOUNDS_QUERY = """
SELECT MIN(publication_date) AS min_date, MAX(publication_date) AS max_date
FROM ai_papers
"""

TOPICS_QUERY = """
SELECT DISTINCT primary_topic_name
FROM ai_papers
WHERE primary_topic_name IS NOT NULL
ORDER BY primary_topic_name
"""


@dataclass(frozen=True)
class FilterState:
    from_date: date
    to_date: date
    topics: tuple[str, ...]
    oa_only: bool

    def to_params(self) -> dict:
        return {
            "from_date": self.from_date,
            "to_date": self.to_date,
            "topics": list(self.topics),
            "oa_only": self.oa_only,
        }


def make_filters(
    from_date: date,
    to_date: date,
    topics: list[str] | None,
    oa_only: bool,
) -> FilterState:
    return FilterState(
        from_date=from_date,
        to_date=to_date,
        topics=tuple(topics or ()),
        oa_only=oa_only,
    )


@st.cache_data(ttl=300, show_spinner=False)
def load_date_bounds() -> tuple[date, date]:
    with connect() as conn:
        bounds = pd.read_sql(DATE_BOUNDS_QUERY, conn)
    if bounds.empty or bounds.iloc[0]["min_date"] is None:
        today = date.today()
        return today, today
    return bounds.iloc[0]["min_date"], bounds.iloc[0]["max_date"]


@st.cache_data(ttl=300, show_spinner=False)
def load_topics() -> list[str]:
    with connect() as conn:
        frame = pd.read_sql(TOPICS_QUERY, conn)
    return frame["primary_topic_name"].tolist()


@st.cache_data(ttl=300, show_spinner="Loading publications...")
def load_papers(filters: FilterState) -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql(PAPERS_QUERY, conn, params=filters.to_params())


@st.cache_data(ttl=300, show_spinner=False)
def load_publications_by_date(filters: FilterState) -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql(PUBLICATIONS_BY_DATE_QUERY, conn, params=filters.to_params())


@st.cache_data(ttl=300, show_spinner=False)
def load_breakdown(query: str, filters: FilterState) -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql(query, conn, params=filters.to_params())


@st.cache_data(ttl=300, show_spinner=False)
def load_ingest_runs() -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql(INGEST_RUNS_QUERY, conn)




def render_sidebar(min_date: date, max_date: date, all_topics: list[str]) -> FilterState:
    st.sidebar.header("Filters")

    date_range = st.sidebar.date_input(
        "Publication date",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        from_date, to_date = date_range
    else:
        from_date = to_date = date_range if isinstance(date_range, date) else max_date

    selected_topics = st.sidebar.multiselect(
        "Primary topic",
        options=all_topics,
        default=[],
        placeholder="All topics",
    )
    oa_only = st.sidebar.checkbox("Open access only", value=False)

    if st.sidebar.button("Refresh data"):
        st.cache_data.clear()

    return make_filters(
        from_date=from_date,
        to_date=to_date,
        topics=selected_topics,
        oa_only=oa_only,
    )


def render_metrics(papers: pd.DataFrame) -> None:
    total = len(papers)
    oa_pct = (papers["is_oa"].mean() * 100) if total else 0.0
    median_citations = papers["cited_by_count"].median() if total else 0
    unique_topics = papers["primary_topic_name"].nunique(dropna=True)
    avg_authors = papers["author_count"].mean() if total else 0.0

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Publications", f"{total:,}")
    col2.metric("Open access", f"{oa_pct:.1f}%")
    col3.metric("Median citations", f"{median_citations:.0f}")
    col4.metric("Topics", f"{unique_topics:,}")
    col5.metric("Avg authors", f"{avg_authors:.1f}")


def prepare_trend_series(
    by_date: pd.DataFrame,
    from_date: date,
    to_date: date,
) -> pd.DataFrame:
    """Build a continuous daily time series with a rolling average trend line."""
    date_index = pd.date_range(from_date, to_date, freq="D")

    if by_date.empty:
        series = pd.DataFrame({"Daily papers": 0}, index=date_index)
    else:
        daily = by_date.copy()
        daily["publication_date"] = pd.to_datetime(daily["publication_date"])
        series = (
            daily.set_index("publication_date")["papers"]
            .reindex(date_index, fill_value=0)
            .rename("Daily papers")
            .to_frame()
        )

    series["7-day average"] = (
        series["Daily papers"].rolling(window=7, min_periods=1).mean().round(1)
    )
    return series


def render_publications_chart(
    by_date: pd.DataFrame,
    from_date: date,
    to_date: date,
) -> None:
    st.subheader("Publication trends over time")
    trend = prepare_trend_series(by_date, from_date, to_date)

    if trend["Daily papers"].sum() == 0:
        st.info("No publications in the selected date range.")
        return

    total = int(trend["Daily papers"].sum())
    avg_daily = trend["Daily papers"].mean()
    peak_day = trend["Daily papers"].idxmax()
    peak_count = int(trend["Daily papers"].max())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total in range", f"{total:,}")
    col2.metric("Avg per day", f"{avg_daily:.1f}")
    col3.metric("Peak day", peak_day.strftime("%Y-%m-%d"))
    col4.metric("Peak count", f"{peak_count:,}")

    st.line_chart(trend[["Daily papers", "7-day average"]], height=340)
    st.caption(
        "Daily publication volume with a 7-day rolling average to highlight the underlying trend."
    )

    with st.expander("Daily publication breakdown", expanded=False):
        st.bar_chart(trend["Daily papers"], height=260)


def render_breakdown_charts(
    topics: pd.DataFrame,
    oa_status: pd.DataFrame,
    venues: pd.DataFrame,
    countries: pd.DataFrame,
) -> None:
    left, right = st.columns(2)

    with left:
        st.subheader("Top topics")
        if topics.empty:
            st.caption("No topic data available.")
        else:
            st.bar_chart(topics.set_index("topic")["papers"], height=320)

    with right:
        st.subheader("Open-access status")
        if oa_status.empty:
            st.caption("No open-access data available.")
        else:
            st.bar_chart(oa_status.set_index("oa_status")["papers"], height=320)

    left, right = st.columns(2)

    with left:
        st.subheader("Top venues")
        if venues.empty:
            st.caption("No venue data available.")
        else:
            st.bar_chart(venues.set_index("venue")["papers"], height=320)

    with right:
        st.subheader("Top countries")
        if countries.empty:
            st.caption("No country data available.")
        else:
            st.bar_chart(countries.set_index("country")["papers"], height=320)


def render_publications_table(papers: pd.DataFrame) -> None:
    st.subheader("Publications")
    if papers.empty:
        st.info("No publications match the current filters.")
        return

    display = papers.copy()
    display["openalex_url"] = display["openalex_id"].apply(
        lambda paper_id: f"https://openalex.org/works/{paper_id}"
    )
    display["oa"] = display["is_oa"].map({True: "Yes", False: "No"})
    display["countries"] = display["country_codes"].apply(
        lambda codes: ", ".join(codes) if isinstance(codes, list) else ""
    )

    st.dataframe(
        display[
            [
                "title",
                "openalex_url",
                "publication_date",
                "primary_topic_name",
                "source_name",
                "oa",
                "cited_by_count",
                "author_count",
                "countries",
            ]
        ],
        column_config={
            "title": st.column_config.TextColumn("Title", width="large"),
            "openalex_url": st.column_config.LinkColumn("OpenAlex", display_text="View"),
            "publication_date": st.column_config.DateColumn("Published"),
            "primary_topic_name": "Topic",
            "source_name": "Venue",
            "oa": "Open access",
            "cited_by_count": st.column_config.NumberColumn("Citations"),
            "author_count": st.column_config.NumberColumn("Authors"),
            "countries": "Countries",
        },
        hide_index=True,
        use_container_width=True,
    )


def render_ingest_runs(runs: pd.DataFrame) -> None:
    with st.expander("Recent ingest runs"):
        if runs.empty:
            st.caption("No ingest runs recorded yet.")
            return
        st.dataframe(
            runs,
            column_config={
                "fetched_at": st.column_config.DatetimeColumn("Fetched at"),
                "from_date": st.column_config.DateColumn("From"),
                "to_date": st.column_config.DateColumn("To"),
                "paper_count": st.column_config.NumberColumn("Papers"),
                "created_at": st.column_config.DatetimeColumn("Logged at"),
            },
            hide_index=True,
            use_container_width=True,
        )


def main() -> None:
    st.set_page_config(
        page_title="AI Publications Dashboard",
        page_icon="📊",
        layout="wide",
    )

    st.title("AI Publications Dashboard")
    st.caption("Insights from OpenAlex Artificial Intelligence papers stored in Neon PostgreSQL.")

    try:
        min_date, max_date = load_date_bounds()
        all_topics = load_topics()
    except Exception as exc:
        st.error(f"Could not connect to the database: {exc}")
        st.info("Set `DATABASE_URL` or `DB_PASSWORD` in your `.env` file and try again.")
        return

    filters = render_sidebar(min_date, max_date, all_topics)

    try:
        papers = load_papers(filters)
        by_date = load_publications_by_date(filters)
        topics = load_breakdown(TOP_TOPICS_QUERY, filters)
        oa_status = load_breakdown(OA_STATUS_QUERY, filters)
        venues = load_breakdown(TOP_VENUES_QUERY, filters)
        countries = load_breakdown(TOP_COUNTRIES_QUERY, filters)
        ingest_runs = load_ingest_runs()
    except Exception as exc:
        st.error(f"Failed to load dashboard data: {exc}")
        return

    render_metrics(papers)
    render_publications_chart(by_date, filters.from_date, filters.to_date)
    render_breakdown_charts(topics, oa_status, venues, countries)
    render_publications_table(papers)
    render_ingest_runs(ingest_runs)


if __name__ == "__main__":
    main()
