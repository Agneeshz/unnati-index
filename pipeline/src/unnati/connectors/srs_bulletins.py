"""SRS special bulletins from the Registrar General's catalogue (censusindia.gov.in NADA):
maternal mortality ratio and life expectancy at birth, by state.

- Special Bulletin on Maternal Mortality: three-year pooled MMR with a 95% confidence interval,
  for India and the larger states only (smaller states appear as "Other states").
- Abridged Life Tables: five-year life expectancy at birth for India and the bigger states/UTs
  (the state-wise statement in the analysis section).

The catalogue's search API lists every edition; the newest few are read so trends are
available. censusindia.gov.in omits its intermediate certificate, so requests use
`with_intermediates("emsign-ssl-ca-g1.pem")` (still fully verified)."""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

import pdfplumber

from unnati.core.entities import EntityResolver, UnknownEntityError
from unnati.core.http import PoliteClient, with_intermediates
from unnati.core.periods import Period, span
from unnati.observations import Observation

NADA = "https://censusindia.gov.in/nada/index.php"
EDITIONS = 4  # newest editions read per series


@dataclass(frozen=True)
class Series:
    indicator_id: str
    report: str
    search: str
    title: re.Pattern[str]  # group 1 = first year, group 2 = last year


MMR = Series(
    "maternal-mortality-ratio",
    "Special Bulletin on Maternal Mortality",
    "special bulletin on maternal mortality",
    re.compile(r"(?i)special bulletin on\s+maternal mortality in india\s+(\d{4})-(\d{2,4})\s*$"),
)
LIFE = Series(
    "life-expectancy",
    "Abridged Life Tables",
    "abridged life tables",
    re.compile(r"(?i)\(srs\)-abridged life tables\s+(\d{4})-(\d{2,4})\s*$"),
)


@dataclass(frozen=True)
class Edition:
    series: Series
    catalog_id: str
    period: Period


def client() -> PoliteClient:
    return PoliteClient(timeout=300, ssl_context=with_intermediates("emsign-ssl-ca-g1.pem"))


def _period(first: str, last: str) -> Period:
    start = int(first)
    end = int(last) if len(last) == 4 else (start // 100) * 100 + int(last)
    return span(date(start, 1, 1), date(end, 12, 31), f"{start}-{end % 100:02d}")


def editions(http: PoliteClient, series: Series) -> list[Edition]:
    rows = http.get(f"{NADA}/api/catalog/search", params={"sk": series.search, "ps": 100}).json()["result"][
        "rows"
    ]
    found = []
    for row in rows:
        match = series.title.search(row["title"].strip())
        if match:
            found.append(Edition(series, str(row["id"]), _period(match.group(1), match.group(2))))
    if not found:
        raise RuntimeError(f"NADA: no editions found for {series.search!r}")
    return sorted(found, key=lambda e: e.period.end)[-EDITIONS:]


def fingerprint(found: list[Edition]) -> str:
    return hashlib.sha256(json.dumps([(e.catalog_id, e.period.label) for e in found]).encode()).hexdigest()


def download(http: PoliteClient, edition: Edition) -> bytes:
    """The report itself. Corrigenda are skipped: the RGI re-uploads corrected reports."""
    page = http.get(f"{NADA}/catalog/{edition.catalog_id}/related-materials").text
    pattern = rf'href="({re.escape(NADA)}/catalog/{edition.catalog_id}/download/\d+)"\s*title="([^"]*)"'
    links = sorted({url for url, title in re.findall(pattern, page) if "corrigendum" not in title.lower()})
    if len(links) != 1:
        raise RuntimeError(f"NADA catalog {edition.catalog_id}: expected one report, found {len(links)}")
    return http.get(links[0]).content


def _text(pdf_bytes: bytes) -> list[str]:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


_MMR_ROW = re.compile(r"^([A-Za-z][A-Za-z &.*-]*?)\s+(\d+)\s+\(\s*(\d+)\s*,\s*(\d+)\s*\)")
_LIFE_ROW = re.compile(r"^([A-Za-z][A-Za-z &.*-]*?)\s+(\d{2}\.\d)(?:\s+\d{2}\.\d)+\b")


def mmr_rows(texts: Iterable[str]) -> Iterable[tuple[str, float, float, float]]:
    for text in texts:
        if "MMR" not in text:
            continue
        for line in text.split("\n"):
            match = _MMR_ROW.match(line.strip())
            if match and not re.search(r"(?i)subtotal|other states", match.group(1)):
                yield match.group(1).strip(), *(float(match.group(i)) for i in (2, 3, 4))


def life_rows(texts: Iterable[str]) -> Iterable[tuple[str, float]]:
    """Rows of the state-wise statement of life expectancy at birth by sex and residence."""
    for text in texts:
        if not re.search(r"(?i)expectation of life at birth by sex and residence", text):
            continue
        body = re.split(r"(?i)expectation of life at birth by sex and residence", text, maxsplit=1)[1]
        found = [m for line in body.split("\n") if (m := _LIFE_ROW.match(line.strip()))]
        for match in found:
            yield match.group(1).rstrip("* ").strip(), float(match.group(2))
        if found:  # earlier pages mention the statement without the table
            return


def observations(
    pdfs: list[tuple[Edition, bytes]], resolver: EntityResolver
) -> tuple[list[Observation], list[str]]:
    out: list[Observation] = []
    problems: list[str] = []
    for edition, pdf in pdfs:
        texts = _text(pdf)
        label = f"SRS {edition.series.search} {edition.period.label}"
        seen: set[str] = set()
        if edition.series is MMR:
            parsed = [(name, value, low, high) for name, value, low, high in mmr_rows(texts)]
        else:
            parsed = [(name, value, None, None) for name, value in life_rows(texts)]
        for name, value, low, high in parsed:
            try:
                entity = resolver.resolve(name, edition.period)
            except UnknownEntityError as err:
                problems.append(f"{label}: {err}")
                continue
            if entity is None or entity.slug in seen:
                continue
            seen.add(entity.slug)
            out.append(
                Observation(
                    edition.series.indicator_id,
                    entity.slug,
                    edition.period,
                    value,
                    ci_low=low,
                    ci_high=high,
                    note=f"SRS {edition.series.report} {edition.period.label}",
                )
            )
        expected = 19 if edition.series is MMR else 22  # India + states each bulletin covers
        if len(seen) < expected:
            problems.append(f"{label}: only {len(seen)} rows read")
    return out, problems
