"""Jal Jeevan Mission: share of rural households with a tap water connection, by state.

The JJM dashboard (ejalshakti.gov.in/jjmreport/JJMIndia.aspx) loads its figures in the
browser, so its "Status of households with tap water connection" table is exported to PDF
by hand into `pipeline/manual-downloads/jjm/` and committed. Each export is one snapshot,
dated by its "Printed on" line. JJM covers rural households only, so Delhi and Chandigarh
have no figure."""

from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path

import pdfplumber

from unnati.core.entities import EntityResolver, UnknownEntityError
from unnati.core.periods import day
from unnati.observations import Observation

MANUAL_DIR = Path(__file__).resolve().parents[3] / "manual-downloads" / "jjm"

_ROW = re.compile(r"^([A-Za-z][A-Za-z&. ]*?)\s+([\d,]+)\s+([\d,]+)\s+(\d{1,3}\.\d{2})$")
_PRINTED = re.compile(r"Printed on\s*:\s*(\d{1,2} [A-Za-z]{3} \d{4})")


def parse(pdf_bytes: bytes) -> tuple[datetime | None, list[tuple[str, float, int]]]:
    """(as-of date, [(place, % of rural households with a tap, total households)])."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    printed = _PRINTED.search(text)
    when = datetime.strptime(printed.group(1), "%d %b %Y") if printed else None
    rows = []
    for line in text.split("\n"):
        match = _ROW.match(line.strip())
        if match:
            rows.append((match.group(1).strip(), float(match.group(4)), int(match.group(2).replace(",", ""))))
    return when, rows


def observations(files: dict[str, bytes], resolver: EntityResolver) -> tuple[list[Observation], list[str]]:
    out: list[Observation] = []
    problems: list[str] = []
    for name, pdf in sorted(files.items()):
        when, rows = parse(pdf)
        if when is None:
            problems.append(f"{name}: no 'Printed on' date")
            continue
        period = day(when.date())
        seen = set()
        for place, share, households in rows:
            target = "All India" if place.lower() == "total" else place
            try:
                entity = resolver.resolve(target, period)
            except UnknownEntityError as err:
                problems.append(f"{name}: {err}")
                continue
            if entity is None or entity.slug in seen:
                continue
            seen.add(entity.slug)
            note = f"Jal Jeevan Mission dashboard, {households:,} rural households (as on {when:%d %b %Y})"
            out.append(Observation("tap-water-households", entity.slug, period, share, note=note))
        if len(seen) < 30:
            problems.append(f"{name}: only {len(seen)} places read")
    return out, sorted(set(problems))
