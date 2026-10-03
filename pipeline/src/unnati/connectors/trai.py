"""TRAI quarterly Performance Indicators Report: internet subscribers per 100 population, by state.

The report (one PDF a quarter, listed on trai.gov.in) has a State/UT table of internet
subscribers and "tele-density" (subscribers per 100 people) at the end of the quarter, which
spares us TRAI's usual telecom-circle geography. The newest reports are read so there is a
short trend. Subscriptions are counted where they are registered, so states with many
visitors and migrants (Delhi, Goa) read high."""

from __future__ import annotations

import hashlib
import io
import json
import re

import pdfplumber

from unnati.connectors.mospi import number
from unnati.core.entities import EntityResolver, UnknownEntityError
from unnati.core.http import PoliteClient
from unnati.core.periods import Period, month
from unnati.observations import Observation

BASE = "https://www.trai.gov.in"
LISTING = f"{BASE}/release-publication/reports/performance-indicators-reports"
REPORTS = 4  # newest quarterly reports read

_LINK = re.compile(r'href="(/sites/default/files/[^"]*QPIR_[^"]*\.pdf)"', re.I)
_TABLE = re.compile(r"(?i)State/UT wise number of Internet Subscribers per 100 population")
_AS_AT = re.compile(r"(?i)at the end of ([A-Z][a-z]{2})-(\d{2})")
_ROW = re.compile(r"^(\d{1,2})\s*(.*?)((?:\s+(?:\d+(?:\.\d+)?|-)){6})\s*$")
_MONTHS = {
    m: i
    for i, m in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1
    )
}


def report_urls(http: PoliteClient) -> list[str]:
    """The newest quarterly reports, newest first (the listing is in date order)."""
    page = http.get(LISTING).text
    urls = list(dict.fromkeys(BASE + path for path in _LINK.findall(page)))
    if not urls:
        raise RuntimeError("TRAI: no quarterly Performance Indicators Reports listed")
    return urls[:REPORTS]


def fingerprint(urls: list[str]) -> str:
    return hashlib.sha256(json.dumps(urls).encode()).hexdigest()


def _clean(name: str) -> str:
    if re.search(r"(?i)\bdaman\b", name):  # not "Andaman"
        return "Dadra & Nagar Haveli and Daman & Diu"
    name = re.sub(r"\s*\([^)]*\)", "", name)  # "(UPE+UPW)"
    return re.sub(r"(?i)\s+incl\..*$", "", name).strip()  # "incl. Chennai"


def table(text: str) -> tuple[Period, list[tuple[str, float]]] | None:
    """(quarter-end month, [(place, subscribers per 100)]) from the State/UT table page."""
    if not _TABLE.search(text):
        return None
    as_at = _AS_AT.search(text)
    if not as_at:
        raise ValueError("TRAI table: no 'at the end of <Mon>-<yy>'")
    period = month(2000 + int(as_at.group(2)), _MONTHS[as_at.group(1)])
    lines = [line.strip() for line in text.split("\n")]
    out = []
    for i, line in enumerate(lines):
        total = re.match(r"^Total((?:\s+(?:\d+(?:\.\d+)?|-)){6})\s*$", line)
        if total:
            out.append(("All India", number(total.group(1).split()[-1])))
            continue
        match = _ROW.match(line)
        if not match:
            continue
        name = match.group(2).strip()
        if not name:  # wrapped: "Uttar Pradesh" / "26 71.50 ..." / "(UPE+UPW)"
            name = f"{lines[i - 1]} {lines[i + 1] if i + 1 < len(lines) else ''}"
        out.append((_clean(name), number(match.group(3).split()[-1])))
    return period, out


def observations(pdfs: list[bytes], resolver: EntityResolver) -> tuple[list[Observation], list[str]]:
    found: list[Observation] = []
    problems: list[str] = []
    for pdf_bytes in pdfs:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            parsed = next(filter(None, (table(p.extract_text() or "") for p in pdf.pages)), None)
        if parsed is None:
            problems.append("TRAI report: State/UT internet table not found")
            continue
        period, rows = parsed
        seen: set[str] = set()
        for name, value in rows:
            try:
                entity = resolver.resolve(name, period)
            except UnknownEntityError as err:
                problems.append(f"TRAI {period.label}: {err}")
                continue
            if entity is None or value is None or entity.slug in seen:
                continue
            seen.add(entity.slug)
            found.append(
                Observation(
                    "internet-subscribers-per-100",
                    entity.slug,
                    period,
                    value,
                    note=f"TRAI Performance Indicators Report, end of {period.label}",
                )
            )
        if len(seen) < 37:
            problems.append(f"TRAI {period.label}: only {len(seen)} rows read")
    return found, sorted(set(problems))
