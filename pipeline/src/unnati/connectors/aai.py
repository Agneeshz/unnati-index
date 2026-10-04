"""Airports Authority of India monthly traffic report: air passengers per 100 people, by state.

AAI's traffic news page links a PDF per annexure each month (e.g. traffic-news/Aug2k26Annex3.pdf).
Annexure III C gives total passengers (domestic + international) at every airport for the month
and for the fiscal year to date. Airports map to states through `reference/aai_airports.csv`;
a state's value is its airports' passengers in the fiscal year to date, scaled to a year and
divided by its mid-year population. A big hub serves people from neighbouring states and
tourists (Delhi, Goa), so this measures air traffic handled, not residents' flying."""

from __future__ import annotations

import calendar
import csv
import io
import re
from datetime import date
from functools import cache
from importlib.resources import files

import pdfplumber

from unnati.core.http import PoliteClient
from unnati.core.periods import span
from unnati.observations import Observation
from unnati.reference import Population

PAGE = "https://www.aai.aero/en/business-opportunities/aai-traffic-news"
BASE = "https://www.aai.aero/sites/default/files/"
_LINK = re.compile(r"traffic-news/([A-Za-z]{3})[a-z]*2k(\d{2})Annex3\.pdf")
_MONTHS = {m.lower()[:3]: i for i, m in enumerate(calendar.month_name) if m}
_ROW = re.compile(r"^\d+\s+.*?([A-Z][A-Z .()\-/&]+?)\s+(\d+)\s+(\d+)\s+(?:-?[\d.]+%|-)\s+(\d+)\s+(\d+)\s")


@cache
def airport_states() -> dict[str, str]:
    path = files("unnati.reference").joinpath("aai_airports.csv")
    with path.open(encoding="utf-8", newline="") as fh:
        return {row["airport"]: row["state_slug"] for row in csv.DictReader(fh)}


def latest_report(http: PoliteClient) -> tuple[date, str]:
    """(last day of the latest report month, URL of its Annexure III)."""
    links = {}
    for match in _LINK.finditer(http.get(PAGE).text):
        when = date(2000 + int(match.group(2)), _MONTHS[match.group(1).lower()[:3]], 1)
        links[when] = BASE + match.group(0)
    if not links:
        raise RuntimeError("AAI: no Annexure III link on the traffic news page")
    month = max(links)
    end = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
    return end, links[month]


def passengers(pdf_bytes: bytes) -> dict[str, int]:
    """Airport -> total passengers (domestic + international) in the fiscal year to date."""
    out: dict[str, int] = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        in_total = False
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "ANNEXURE-III C" in text:
                in_total = True
            if not in_total:
                continue
            for line in text.split("\n"):
                match = _ROW.match(line.strip())
                if match:
                    out[match.group(1).strip()] = int(match.group(4))
    return out


def observations(
    by_airport: dict[str, int], month_end: date, population: dict[tuple[str, int], Population]
) -> tuple[list[Observation], list[str]]:
    states = airport_states()
    fy_start = month_end.year if month_end.month >= 4 else month_end.year - 1
    months = (month_end.year - fy_start) * 12 + month_end.month - 3
    label = f"Apr–{month_end:%b %Y} (FY {fy_start}-{(fy_start + 1) % 100:02d} to date)"
    period = span(date(fy_start, 4, 1), month_end, label, "multi_year")
    totals: dict[str, int] = {}
    problems: list[str] = []
    for airport, count in by_airport.items():
        slug = states.get(airport)
        if slug is None:
            problems.append(f"AAI: airport {airport!r} has no state in aai_airports.csv")
            continue
        totals[slug] = totals.get(slug, 0) + count
    totals["india"] = sum(by_airport.values())
    out: list[Observation] = []
    for slug, count in totals.items():
        people = population.get((slug, fy_start))
        if people is None:
            continue
        annual = count * 12 / months
        note = f"AAI traffic report: {count:,} passengers in {label}, scaled to 12 months"
        value = round(annual / people.persons * 100, 1)
        out.append(Observation("air-passengers-per-100", slug, period, value, note=note))
    return out, sorted(set(problems))
