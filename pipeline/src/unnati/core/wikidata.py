"""Minimal Wikidata Query Service client."""

from __future__ import annotations

from datetime import date

from unnati.core.http import PoliteClient

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
ENTITY_PREFIX = "http://www.wikidata.org/entity/"


def sparql(http: PoliteClient, query: str) -> list[dict[str, str]]:
    """Run a SPARQL query and return rows as {variable: value} with plain string values."""
    response = http.post(
        SPARQL_ENDPOINT,
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
    )
    return parse_results(response.json())


def parse_results(payload: dict) -> list[dict[str, str]]:
    return [{k: v["value"] for k, v in row.items()} for row in payload["results"]["bindings"]]


def qid(uri: str) -> str:
    """``http://www.wikidata.org/entity/Q1186`` -> ``Q1186``."""
    return uri.removeprefix(ENTITY_PREFIX)


def to_date(value: str | None) -> date | None:
    """Wikidata time values look like ``2016-05-25T00:00:00Z``; unknown values are not dates."""
    if not value or not value[:1].isdigit():
        return None
    return date.fromisoformat(value[:10])


def values_clause(qids: list[str]) -> str:
    return " ".join(f"wd:{q}" for q in qids)
