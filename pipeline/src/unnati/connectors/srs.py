"""Sample Registration System (SRS) Statistical Report: infant and under-5 mortality, fertility and
sex ratio at birth, by state.

The Registrar General's report is mirrored on OpenCity (CKAN package
`sample-registration-system-statistical-reports`, one PDF per edition). Read from the newest
edition:

- Table 14: IMR, bigger states/UTs, six annual estimates (e.g. 2019-2024).
- Table 15: TFR, bigger states/UTs, six annual estimates.
- Table 16: sex ratio at birth, bigger states/UTs, five three-year periods (e.g. 2018-20).
- Statement 46: IMR for the smaller states and UTs, which SRS publishes only as a three-year
  average (e.g. 2022-24) because their samples are small.
- Statement 53: U5MR, bigger states/UTs, edition year.

Each table's first block of columns is the Total (then Male/Female or Rural/Urban)."""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Iterable
from datetime import date

import pdfplumber

from unnati.connectors.mospi import number
from unnati.core.entities import EntityResolver, UnknownEntityError
from unnati.core.http import PoliteClient
from unnati.core.periods import Period, calendar_year, span
from unnati.observations import Observation

CKAN_PACKAGE = "https://data.opencity.in/api/3/action/package_show"
PACKAGE_ID = "sample-registration-system-statistical-reports"

_EDITION = re.compile(r"(?i)statistical report\s*(\d{4})")
_ROW = re.compile(r"^([A-Za-z][A-Za-z&*().,' -]*?)\s+((?:\d+(?:\.\d+)?)(?:\s+\d+(?:\.\d+)?)*)(?:\s+\D.*)?$")
_YEAR = re.compile(r"^(?:19|20)\d\d$")
_THREE_YEAR = re.compile(r"^((?:19|20)\d\d)-(\d\d)$")


def latest_resource(http: PoliteClient) -> tuple[int, dict]:
    package = http.get(CKAN_PACKAGE, params={"id": PACKAGE_ID}).json()["result"]
    editions = []
    for resource in package["resources"]:
        match = _EDITION.search(resource.get("name", ""))
        if match and resource["url"].lower().endswith(".pdf"):
            editions.append((int(match.group(1)), resource))
    if not editions:
        raise RuntimeError(f"{PACKAGE_ID}: no Statistical Report PDF")
    return max(editions, key=lambda e: e[0])


def fingerprint(edition: int, resource: dict) -> str:
    meta = [
        edition,
        resource["id"],
        resource["url"],
        resource.get("last_modified") or resource.get("created"),
    ]
    return hashlib.sha256(json.dumps(meta).encode()).hexdigest()


def pages(pdf_bytes: bytes) -> list[str]:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def find(texts: list[str], heading: str) -> str:
    """The page whose text starts with (Table) or contains on its own line (Statement) a heading."""
    pattern = re.compile(rf"(?m)^{re.escape(heading)}(?::|\s*$)")
    for text in texts:
        if pattern.search(text):
            return text
    raise ValueError(f"SRS report: {heading!r} not found")


def rows(text: str) -> Iterable[tuple[str, list[str]]]:
    for line in text.split("\n"):
        match = _ROW.match(line.strip())
        if match:
            yield match.group(1).rstrip("* ").strip(), match.group(2).split()


def column_periods(text: str) -> list[Period]:
    """Periods of the Total block, read from the header line ("2019 2020 ... 2024 2019 ...")."""
    for line in text.split("\n"):
        tokens = line.split()
        periods: list[Period] = []
        for token in tokens:
            if _YEAR.match(token):
                period = calendar_year(int(token))
            elif m := _THREE_YEAR.match(token):
                first = int(m.group(1))
                period = span(date(first, 1, 1), date(first + 2, 12, 31), token)
            else:
                continue
            if periods and period.label == periods[0].label:
                return periods  # the next block (Male/Rural) starts again
            periods.append(period)
        if len(periods) >= 3:  # the title line names only the first and last periods
            return periods
    raise ValueError("SRS table: no period header")


class _Collector:
    def __init__(self, resolver: EntityResolver) -> None:
        self.resolver = resolver
        self.out: list[Observation] = []
        self.problems: list[str] = []

    def add(self, indicator_id: str, name: str, period: Period, raw: str, note: str) -> bool:
        try:
            entity = self.resolver.resolve(name, period)
        except UnknownEntityError as err:
            self.problems.append(f"{note}: {err}")
            return False
        value = number(raw)
        if entity is None or value is None:
            return False
        self.out.append(Observation(indicator_id, entity.slug, period, value, note=note))
        return True


def _annual_table(c: _Collector, text: str, indicator_id: str, note: str) -> int:
    periods = column_periods(text)
    count = 0
    for name, values in rows(text):
        if len(values) < len(periods):
            continue
        for period, raw in zip(periods, values, strict=False):
            c.add(indicator_id, name, period, raw, note)
        count += 1
    return count


def observations(
    pdf_bytes: bytes, edition: int, resolver: EntityResolver
) -> tuple[list[Observation], list[str]]:
    texts = pages(pdf_bytes)
    c = _Collector(resolver)
    source = f"SRS Statistical Report {edition}"
    for heading, indicator_id in (
        ("Table 14", "infant-mortality-rate"),
        ("Table 15", "total-fertility-rate"),
        ("Table 16", "sex-ratio-at-birth"),
    ):
        read = _annual_table(c, find(texts, heading), indicator_id, f"{source}, {heading.lower()}")
        if read < 22:  # India and 21+ bigger states/UTs
            c.problems.append(f"{source} {heading}: only {read} rows read")

    # Smaller states and UTs: three-year average IMR, after the "Smaller States" heading.
    text = find(texts, "Statement 46")
    pooled = span(date(edition - 2, 1, 1), date(edition, 12, 31), f"{edition - 2}-{edition % 100:02d}")
    smaller = text.split("Smaller States", 1)[1] if "Smaller States" in text else ""
    read = sum(
        c.add(
            "infant-mortality-rate",
            name,
            pooled,
            values[0],
            f"{source}, statement 46; three-year average for a smaller state/UT",
        )
        for name, values in rows(smaller)
    )
    if read < 12:
        c.problems.append(f"{source} statement 46: only {read} smaller states/UTs read")

    text = find(texts, "Statement 53")
    read = sum(
        c.add("under5-mortality-rate", name, calendar_year(edition), values[0], f"{source}, statement 53")
        for name, values in rows(text)
        if len(values) >= 9
    )
    if read < 22:
        c.problems.append(f"{source} statement 53: only {read} rows read")
    return c.out, sorted(set(c.problems))
