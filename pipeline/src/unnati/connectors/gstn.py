"""GSTN monthly GST revenue report: state GST revenue per person and its growth.

GSTN publishes a PDF each month (linked from the GST portal's news feed, whose file names vary
month to month). Its Table 2 gives, for every state/UT, SGST plus the SGST share of IGST
settled to it ("post-settlement SGST") from April to the report month, for this fiscal year
and the last. From it:

- gst-collection-per-capita: post-settlement SGST in the fiscal year to date, per person
  (MoHFW mid-year population for the fiscal year's first calendar year);
- gst-collection-growth: the same against the same months of the previous fiscal year.
"""

from __future__ import annotations

import calendar
import io
import re
from datetime import date

import pdfplumber

from unnati.connectors.mospi import number
from unnati.core.entities import EntityResolver, UnknownEntityError
from unnati.core.http import PoliteClient
from unnati.core.periods import Period, span
from unnati.observations import Observation
from unnati.reference import Population

NEWS = "https://www.gst.gov.in/fomessage/newsupdates"
_REPORT = re.compile(r"https?://tutorial\.gst\.gov\.in/downloads/news/[\w\-]*gst_revenue[\w\-]*\.pdf", re.I)
_TABLE2 = re.compile(r"Table-?\s*2:.*?till\s+([A-Za-z]+),?\s+(\d{4})", re.I)
_NUM = r"-?[\d,]+(?:\.\d+)?"
_ROW = re.compile(rf"^(.*?)\s+({_NUM})\s+({_NUM})\s+(-?\d+)%\s+({_NUM})\s+({_NUM})\s+(-?\d+)%\s*$")
_MONTHS = {m.lower()[:3]: i for i, m in enumerate(calendar.month_name) if m}  # 'jun' or 'june'


def report_urls(http: PoliteClient) -> list[str]:
    return sorted(set(_REPORT.findall(http.get(NEWS).text)))


def table2(pdf_bytes: bytes) -> tuple[Period, list[tuple[str, float, float]]] | None:
    """(fiscal year to date, [(place, post-settlement SGST last year, this year)]) in Rs crore."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = next((t for p in pdf.pages if _TABLE2.search(t := p.extract_text() or "")), None)
    if text is None:
        return None
    month_name, year = _TABLE2.search(text).groups()
    month, year = _MONTHS[month_name.lower()[:3]], int(year)
    fy_start = year if month >= 4 else year - 1
    end = date(year, month, calendar.monthrange(year, month)[1])
    label = f"Apr–{end:%b %Y} (FY {fy_start}-{(fy_start + 1) % 100:02d} to date)"
    period = span(date(fy_start, 4, 1), end, label, "multi_year")
    rows, pending = [], ""
    for line in text.split("\n")[1:]:
        match = _ROW.match(line.strip())
        if not match:
            # Long names wrap ("Dadra and Nagar Haveli and" / "Daman and Diu 101 ..."); keep the start.
            pending = line.strip() if line.strip() and not re.search(r"\d", line) else ""
            continue
        name = f"{pending} {match.group(1)}".strip() if pending else match.group(1).strip()
        pending = ""
        last, this = number(match.group(5)), number(match.group(6))
        if last is not None and this is not None:
            rows.append((name, last, this))
    return period, rows


def observations(
    reports: list[bytes], resolver: EntityResolver, population: dict[tuple[str, int], Population]
) -> tuple[list[Observation], list[str]]:
    out: list[Observation] = []
    problems: list[str] = []
    for pdf in reports:
        parsed = table2(pdf)
        if parsed is None:
            problems.append("GST report: Table 2 not found")
            continue
        period, rows = parsed
        seen = set()
        for name, last, this in rows:
            if re.search(r"(?i)^other territory", name):
                continue  # Centre Jurisdiction / other territory: not a state
            place = "All India" if re.search(r"(?i)grand total", name) else name
            try:
                entity = resolver.resolve(place, period)
            except UnknownEntityError as err:
                problems.append(f"GST report: {err}")
                continue
            if entity is None or entity.slug in seen:
                continue
            seen.add(entity.slug)
            people = population.get((entity.slug, period.start.year))
            note = f"GSTN monthly report, Table 2: post-settlement SGST Rs {this:,.0f} crore ({period.label})"
            if people:
                out.append(
                    Observation(
                        "gst-collection-per-capita",
                        entity.slug,
                        period,
                        round(this * 1e7 / people.persons),
                        note=note,
                    )
                )
            if last > 0:
                growth = round((this / last - 1) * 100, 1)
                out.append(Observation("gst-collection-growth", entity.slug, period, growth, note=note))
        if len(seen) < 36:
            problems.append(f"GST report {period.label}: only {len(seen)} places read")
    return out, sorted(set(problems))
