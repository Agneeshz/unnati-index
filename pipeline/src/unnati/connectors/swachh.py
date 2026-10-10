"""Swachh Survekshan (MoHUA's annual urban cleanliness survey): city scores from the official
2024-25 report, mirrored on OpenCity.

The report ranks every city of 3 lakh people or more by total score out of 12,500: the survey's
own assessment (10,000), the garbage-free city star rating and ODF certification. Totals are
taken as published (a few, such as Ludhiana's, are not the sum of their parts in the report).
Rows look like "9 ANDHRA PRADESH 11636 9336 1100 1200"; a long body name wraps onto the lines
above and below ("GVMC" / "VISAKHAPATNAM").

Cities that ranked in the top three in the last three years and stayed in their category's top
20% form the Super Swachh League: they are assessed separately and given no score, so they are
recorded as members instead (value 1). Where a city has two municipal corporations (Jaipur
Greater and Heritage; Jodhpur and Kota North and South), its score is their mean."""

from __future__ import annotations

import io
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import date

import pdfplumber

from unnati.core.entities import EntityResolver, UnknownEntityError, normalize_name
from unnati.core.http import PoliteClient
from unnati.core.periods import calendar_year, span
from unnati.observations import Observation

CKAN_PACKAGE = "https://data.opencity.in/api/3/action/package_show?id=swachh-survekshan-ss-results"
REPORT_NAME = re.compile(r"(?i)swachh survekshan 2024-25 report")
ROUND = span(date(2024, 4, 1), date(2025, 7, 17), "SS 2024-25", "survey_round")

_RANKING = re.compile(r"(?i)ranking of (million plus|big) cities based on total score")
_ROW = re.compile(r"^(\d+)\s+(.+?)\s+(\d+)\s+(-?\d+)\s+(\d+)\s+(\d+)$")
_HEADER = re.compile(r"(?i)rank|score|ranking|population|©|report|ulb name|state/ ?ut")
_INCOMPLETE = re.compile(r"(?:\bOF|\(M\.?|[-+(])$", re.I)
_SSL_LINE = re.compile(r"([A-Z][a-z]+(?: [A-Z][a-z]+)*):\s*([^:]+)$")
# A city split between two municipal corporations: the body's name -> the city's name.
SPLIT_BODIES = {
    "jaipur greater": "Jaipur",
    "jaipur heritage": "Jaipur",
    "jodhpur north": "Jodhpur",
    "jodhpur south": "Jodhpur",
    "kota north": "Kota",
    "kota south": "Kota",
}


def report_resource(http: PoliteClient) -> dict:
    """The report's OpenCity resource record (its URL and last-modified time)."""
    resources = http.get(CKAN_PACKAGE).json()["result"]["resources"]
    for resource in resources:
        if REPORT_NAME.search(resource.get("name", "")):
            return resource
    raise RuntimeError("Swachh Survekshan: the 2024-25 report is no longer listed on OpenCity")


def fingerprint(resource: dict) -> dict:
    """Cheap change check from the resource metadata, without downloading the 6 MB report."""
    return {
        "id": resource.get("id"),
        "url": resource["url"],
        "modified": resource.get("last_modified") or resource.get("created"),
    }


def _split_state(text: str, resolver: EntityResolver) -> tuple[str | None, str]:
    """("ANDHRA PRADESH GVMC") -> ("andhra-pradesh", "GVMC"): the longest leading state name."""
    words = text.split()
    for k in range(min(5, len(words)), 0, -1):
        try:
            entity = resolver.resolve(" ".join(words[:k]), calendar_year(2025))
        except UnknownEntityError:
            continue
        if entity:
            return entity.slug, " ".join(words[k:])
    return None, text


def ranked_rows(pdf_bytes: bytes, resolver: EntityResolver) -> Iterable[tuple[str, str, float]]:
    """(state slug, body name, total score) for the million-plus and 3-10 lakh rankings."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if _RANKING.search(text):
                yield from page_rows(text, resolver)


def page_rows(text: str, resolver: EntityResolver) -> Iterable[tuple[str, str, float]]:
    """The ranking rows of one page's text."""
    lines = [line.strip() for line in text.split("\n")]
    for i, line in enumerate(lines):
        row = _ROW.match(line)
        if not row:
            continue
        state, body = _split_state(row.group(2), resolver)
        previous = lines[i - 1] if i else ""
        before = "" if _ROW.match(previous) or _HEADER.search(previous) else previous
        after = lines[i + 1] if i + 1 < len(lines) and not _ROW.match(lines[i + 1]) else ""
        after = "" if _HEADER.search(after) else after
        if not body or _INCOMPLETE.search(body):
            # The name wrapped around the numbers: "GVMC" / row / "VISAKHAPATNAM".
            body = " ".join(p for p in (before, body, after) if p)
        elif re.fullmatch(r"[A-Z]{1,3}", after):
            body += after  # one word split across lines: "THIRUVANANTHAPUR" + "AM"
        if state:
            yield state, body, float(row.group(3))


def super_league(pdf_bytes: bytes) -> list[tuple[str, str]]:
    """(state or "Union Territory", body name) for the Super Swachh League cities."""
    out = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "Super Swachh League Cities" not in text or "List of the Cities" not in text:
                continue
            for line in text.split("\n"):
                match = _SSL_LINE.search(line.strip())
                if match:
                    for body in re.split(r",\s*", match.group(2)):
                        out.append((match.group(1), body.strip()))
    return out


def _clean(body: str) -> str:
    """A body's name as a city name: "AGRA (M. Corp)" -> "agra", "MATHURA- VRINDAVAN" ->
    "mathura-vrindavan", "CHANDRAPUR_M" -> "chandrapur", "THIRUVANANTHAPUR AM" -> one word."""
    body = re.sub(r"\s*\(.*$|_m$", "", body.strip(), flags=re.I)
    body = re.sub(r"(\w{6,}) (\w{1,2})$", r"\1\2", body)  # a word broken by the line wrap
    return normalize_name(re.sub(r"\s*-\s*", "-", body))


def observations(
    pdf_bytes: bytes, resolver: EntityResolver, lookup: dict[tuple[str, str], str]
) -> tuple[list[Observation], list[str]]:
    scores: dict[str, list[tuple[str, float]]] = defaultdict(list)
    problems: list[str] = []
    rows = list(ranked_rows(pdf_bytes, resolver))
    if len(rows) < 100:
        problems.append(f"Swachh Survekshan: only {len(rows)} ranked rows read")
    for state, body, score in rows:
        name = _clean(body)
        name = normalize_name(SPLIT_BODIES.get(name, name))
        city = lookup.get((state, name))
        if city:
            # For the note: "JAIPUR GREATER (MC)" -> "Jaipur Greater".
            scores[city].append((re.sub(r"\s*\(.*$", "", body).title(), score))
    out = []
    for city, bodies in scores.items():
        mean = sum(s for _, s in bodies) / len(bodies)
        note = "Swachh Survekshan 2024-25 report, total score out of 12,500"
        if len(bodies) > 1:
            parts = " and ".join(f"{b} ({s:,.0f})" for b, s in bodies)
            note += f"; mean of the city's municipal corporations, {parts}"
        out.append(Observation("swachh-survekshan-score", city, ROUND, round(mean), note=note))
    by_name: dict[str, list[str]] = defaultdict(list)
    for (_, name), city in lookup.items():
        by_name[name].append(city)
    league = super_league(pdf_bytes)
    if len(league) < 20:
        problems.append(f"Swachh Survekshan: only {len(league)} Super Swachh League cities read")
    for state, body in league:
        name = _clean(body)
        try:
            entity = resolver.resolve(state, calendar_year(2025))
        except UnknownEntityError:
            entity = None
        city = lookup.get((entity.slug, name)) if entity else None
        if city is None and len(set(by_name.get(name, []))) == 1:  # "Union Territory: Chandigarh"
            city = by_name[name][0]
        if city:
            note = "Swachh Survekshan 2024-25 report: Super Swachh League (assessed separately, not scored)"
            out.append(Observation("swachh-super-league", city, ROUND, 1, note=note))
    return out, problems
