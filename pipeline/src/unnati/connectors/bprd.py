"""BPR&D Data on Police Organisations (DoPO): police vacancy rate by state, as on 1 January.

The yearly PDF is linked from bprd.nic.in's DoPO page. Table 3.1.1 (continued) gives the total
sanctioned and actual strength of state police (civil + district armed reserve + armed + IRB);
the vacancy rate is (sanctioned - actual) / sanctioned. A negative rate means more personnel
than sanctioned posts."""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote, urljoin

import pdfplumber

from unnati.connectors.mospi import number
from unnati.core.entities import EntityResolver, UnknownEntityError
from unnati.core.http import PoliteClient
from unnati.core.periods import Period, day
from unnati.observations import Observation

# bprd.nic.in often times out from outside India (GitHub's runners): the newest DoPO PDF saved here
# (named with its year, e.g. "Data on Police Organizations (2024).pdf") is used instead.
MANUAL_DIR = Path(__file__).resolve().parents[3] / "manual-downloads" / "bprd"
SITE = "https://bprd.nic.in/"
PAGE = f"{SITE}page/data_on_police_organization_dopo"

_LINK = re.compile(r'href="([^"]*Data on Police Organi[sz]ations \((\d{4})\)[^"]*\.pdf)"', re.I)
_TABLE = re.compile(r"TABLE 3\.1\.1 -- \(CONTINUED")
_VALUE = re.compile(r"^(?:\d{1,3}(?:,\d{2,3})*|-|NA|NP)$")
_ROW = re.compile(r"^(\d{1,2})\s+(.+)$")


def latest(http: PoliteClient) -> tuple[int, str]:
    """(year of the "as on 1 January" data, PDF URL)."""
    page = http.get(PAGE).text
    # Links are relative to the site root (the page sets <base href="https://bprd.nic.in/">).
    found = [(int(year), urljoin(SITE, quote(path, safe="/:()"))) for path, year in _LINK.findall(page)]
    if not found:
        raise RuntimeError("BPR&D: no Data on Police Organizations PDF linked")
    return max(found)


def local_latest() -> tuple[int, Path] | None:
    """(year, path) of the newest DoPO PDF saved by hand, if any."""
    found = []
    for path in MANUAL_DIR.glob("*.pdf"):
        year = re.search(r"(20\d{2})", path.name)
        if year:
            found.append((int(year.group(1)), path))
    return max(found) if found else None


def _split(text: str) -> tuple[str, list[str]]:
    tokens = text.split()
    i = len(tokens)
    while i > 0 and _VALUE.match(tokens[i - 1]):
        i -= 1
    return " ".join(tokens[:i]), tokens[i:]


def rows(text: str) -> list[tuple[str, int, int]]:
    """(place, total sanctioned, total actual) from the continued Table 3.1.1."""
    lines = [line.strip() for line in text.split("\n")]
    out = []
    for i, line in enumerate(lines):
        if line.startswith("All India"):
            name, values = _split(line)
        elif match := _ROW.match(line):
            name, values = _split(match.group(2))
            following = lines[i + 1] if i + 1 < len(lines) else ""
            if following.startswith("and "):  # "Dadra and Nagar Haveli" / "and Daman and Diu"
                name = f"{name} {following}"
        else:
            continue
        if len(values) < 6:
            continue
        sanctioned, actual = number(values[-4]), number(values[-3])
        if sanctioned and actual is not None:
            out.append((name, int(sanctioned), int(actual)))
    return out


def observations(
    pdf_bytes: bytes, year: int, resolver: EntityResolver
) -> tuple[list[Observation], list[str]]:
    period: Period = day(date(year, 1, 1))
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = next((t for p in pdf.pages if _TABLE.search(t := p.extract_text() or "")), None)
    if text is None:
        return [], [f"DoPO {year}: Table 3.1.1 (continued) not found"]
    out: list[Observation] = []
    problems: list[str] = []
    for name, sanctioned, actual in rows(text):
        try:
            entity = resolver.resolve(name, period)
        except UnknownEntityError as err:
            problems.append(f"DoPO {year}: {err}")
            continue
        if entity is None:
            continue
        out.append(
            Observation(
                "police-vacancy",
                entity.slug,
                period,
                round((sanctioned - actual) / sanctioned * 100, 2),
                note=f"DoPO {year}: {actual:,} in post against {sanctioned:,} sanctioned (state police)",
            )
        )
    if len(out) < 37:
        problems.append(f"DoPO {year}: only {len(out)} rows read")
    return out, problems
