"""NFHS-6 (2023-24) state fact sheets, from IIPS's compendium PDF (India and every state/UT).

NFHS-6 is not in MoSPI's API yet. The compendium ("National Family Health Survey (NFHS-6),
2023-24: India and State Fact Sheets", IIPS 2026) is mirrored on OpenCity. Each state has
"<State> - Key Indicators" pages where every numbered item ends with four values: NFHS-6
urban, rural and total, then the NFHS-5 total. Only the NFHS-6 total is taken (NFHS-5 comes
from MoSPI's API).

Fieldwork ran from 28 May 2023 to 31 December 2024. NFHS-6 dropped clean cooking fuel,
sanitation and anaemia from the fact sheets, so those stay at NFHS-5 for now."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable
from datetime import date
from itertools import pairwise

import pdfplumber

from unnati.connectors.mospi import nfhs_label, number
from unnati.core.entities import EntityResolver, UnknownEntityError
from unnati.core.http import PoliteClient
from unnati.core.periods import span
from unnati.observations import Observation

PDF_URL = (
    "https://data.opencity.in/dataset/303e0d47-fe33-469d-aa85-9d645b9b03c1/resource/"
    "5e92fa00-0d10-4bee-9704-e3e97f009904/download/nfhs-6-fact-sheet.pdf"
)
ROUND = span(date(2023, 5, 28), date(2024, 12, 31), "NFHS-6 (2023-24)", "survey_round")

INDICATORS = {
    "Population living in households with electricity (%)": "households-with-electricity",
    "Women age 20-24 years married before age 18 years (%)": "child-marriage",
    "Institutional births (%)": "institutional-births",
    "Children age 12-23 months fully vaccinated based on information from either vaccination card"
    " or mother's recall (%)": "full-immunisation",
    "Children under 5 years who are stunted (height-for-age) (%)": "stunting-under5",
    "Women having a bank or savings account that they themselves use (%)": "women-bank-account",
}

# Headers sometimes come out with stray spaces ("Maharashtra - Ke y Indicators").
_HEADER = re.compile(r"^\s*(.+?)\s+-\s+K\s*e\s*y\s+Indicators\s*$", re.M)
_ITEM = re.compile(r"(?m)^(\d{1,3})\.\s")
_VALUE = re.compile(r"^(?:\(?\d+(?:\.\d+)?\)?|\*|na)$", re.I)


CKAN_PACKAGE = "https://data.opencity.in/api/3/action/package_show?id=nfhs-6-2023-24"


def fetch(http: PoliteClient) -> tuple[bytes, dict[str, str]]:
    """The compendium PDF, plus OpenCity's per-state CSV transcriptions keyed by state name.

    About half the compendium's state pages draw their text as vector outlines, which cannot
    be read without OCR; the CSVs cover several of those states."""
    pdf = http.get(PDF_URL).content
    csvs: dict[str, str] = {}
    for resource in http.get(CKAN_PACKAGE).json()["result"]["resources"]:
        if resource.get("format", "").upper() == "CSV":
            state = resource["name"].split(" - ")[0].strip()
            csvs[state] = http.get(resource["url"]).text
    return pdf, csvs


def csv_items(text: str) -> Iterable[tuple[str, list[str]]]:
    for row in csv.DictReader(io.StringIO(text)):
        yield (
            nfhs_label(row["Indicator"]),
            [row["NFHS6_Urban"], row["NFHS6_Rural"], row["NFHS6_Total"], row["NFHS5_Total"]],
        )


def state_pages(pdf_bytes: bytes) -> dict[str, str]:
    """Text of the Key Indicators pages, grouped by the state named in each page header."""
    pages: dict[str, list[str]] = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            header = _HEADER.search(text.split("\n", 1)[0])
            if header:
                pages.setdefault(header.group(1).strip(), []).append(text)
    return {state: "\n".join(texts) for state, texts in pages.items()}


def items(text: str) -> Iterable[tuple[str, list[str]]]:
    """(label, values) for every numbered item; labels may wrap around their values."""
    starts = [m.start() for m in _ITEM.finditer(text)] + [len(text)]
    for begin, end in pairwise(starts):
        tokens = text[begin:end].split()[1:]  # drop the item number
        runs, current = [], []
        for i, token in enumerate(tokens):
            if _VALUE.match(token):
                current.append(i)
            else:
                if len(current) >= 2:
                    runs.append(current)
                current = []
        if len(current) >= 2:
            runs.append(current)
        if not runs:
            continue
        run = runs[-1]
        label_tokens = [t for i, t in enumerate(tokens) if i not in set(run)]
        label = " ".join(label_tokens)
        if "(%)" in label:
            label = label[: label.index("(%)") + 3]
        yield nfhs_label(label), [tokens[i] for i in run]


def resolve_header(resolver: EntityResolver, name: str):
    """The PDF sometimes splits words ("Ha ryana"): retry with each stray space removed."""
    candidates = [name] + [name[:i] + name[i + 1 :] for i, ch in enumerate(name) if ch == " "]
    last_error: UnknownEntityError | None = None
    for candidate in candidates:
        try:
            return resolver.resolve(candidate, ROUND)
        except UnknownEntityError as err:
            last_error = err
    assert last_error is not None
    raise last_error


def observations(
    pdf_bytes: bytes, csvs: dict[str, str], resolver: EntityResolver
) -> tuple[list[Observation], list[str]]:
    sources = [(state, items(text), "compendium") for state, text in state_pages(pdf_bytes).items()]
    sources += [(state, csv_items(text), "OpenCity CSV") for state, text in csvs.items()]
    by_key: dict[tuple[str, str], Observation] = {}
    covered: dict[str, set[str]] = {}
    problems: list[str] = []
    for state, rows, origin in sources:  # CSVs come last, so they win for the same state
        try:
            entity = resolve_header(resolver, state)
        except UnknownEntityError as err:
            problems.append(str(err))
            continue
        if entity is None:
            continue
        covered.setdefault(entity.slug, set())
        seen = set()
        for label, values in rows:
            indicator_id = INDICATORS.get(label)
            if indicator_id is None or indicator_id in seen:
                continue
            seen.add(indicator_id)
            # Four values: NFHS-6 urban, rural, total, NFHS-5 total. Two: NFHS-6 and NFHS-5 totals.
            total = values[2] if len(values) >= 4 else values[0]
            value = number(total)
            if value is None:
                continue
            note = f"NFHS-6 (2023-24), {origin}"
            if str(total).startswith("("):
                note += "; based on 25-49 unweighted cases"
            by_key[(entity.slug, indicator_id)] = Observation(
                indicator_id, entity.slug, ROUND, value, note=note
            )
            covered[entity.slug].add(indicator_id)
    for slug, found in sorted(covered.items()):
        missing = set(INDICATORS.values()) - found
        if missing:
            problems.append(f"{slug}: no readable NFHS-6 value for {', '.join(sorted(missing))}")
    return list(by_key.values()), sorted(set(problems))
