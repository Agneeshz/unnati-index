"""Projected population, 2011-2036, from the MoHFW Technical Group report (July 2020).

"Population Projections for India and States 2011-2036" is the official denominator until
Census 2027 results arrive; NCRB, MoSPI and others use it. Table 11 gives the projected total
population by sex as on 1 July (mid-year) for India and every state/UT, in thousands.

The report is a one-off publication, so its numbers are committed as reference data
(`reference/population.csv`, built with `unnati population build`) and connectors read them
offline when they need a per-capita denominator.

The pages lay each state out as a column triple (persons, male, female) under a header name
that often wraps over two lines, and the PDF's text stream does not keep the columns in
order. Parsing therefore uses word positions: names and numbers belong to the triple whose
header columns they sit over, and to the year row they are vertically closest to."""

from __future__ import annotations

import io
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

import pdfplumber

REPORT_URL = "https://nhm.gov.in/New_Updates_2018/Report_Population_Projection_2019.pdf"
TABLE = "11"  # projected total population as on 1st July

# The report's own names (pre-2020 UTs are listed separately; Andhra Pradesh means the
# residual state for every year, Telangana is listed from 2011).
NAMES = {
    "INDIA": "india",
    "JAMMU & KASHMIR (UT)": "jammu-and-kashmir",
    "HIMACHAL PRADESH": "himachal-pradesh",
    "PUNJAB": "punjab",
    "HARYANA": "haryana",
    "NCT OF DELHI": "delhi",
    "RAJASTHAN": "rajasthan",
    "UTTAR PRADESH": "uttar-pradesh",
    "BIHAR": "bihar",
    "ASSAM": "assam",
    "WEST BENGAL": "west-bengal",
    "JHARKHAND": "jharkhand",
    "ODISHA": "odisha",
    "CHHATTISGARH": "chhattisgarh",
    "MADHYA PRADESH": "madhya-pradesh",
    "GUJARAT": "gujarat",
    "MAHARASHTRA": "maharashtra",
    "ANDHRA PRADESH": "andhra-pradesh",
    "KARNATAKA": "karnataka",
    "KERALA": "keralam",
    "TAMIL NADU": "tamil-nadu",
    "CHANDIGARH": "chandigarh",
    "UTTARAKHAND": "uttarakhand",
    "SIKKIM": "sikkim",
    "ARUNACHAL PRADESH": "arunachal-pradesh",
    "NAGALAND": "nagaland",
    "MANIPUR": "manipur",
    "MIZORAM": "mizoram",
    "TRIPURA": "tripura",
    "MEGHALAYA": "meghalaya",
    "DAMAN & DIU": "daman-and-diu",
    "DADRA & NAGAR HAVELI": "dadra-and-nagar-haveli",
    "GOA": "goa",
    "ANDAMAN & NICOBAR ISLANDS": "andaman-and-nicobar-islands",
    "LAKSHADWEEP": "lakshadweep",
    "PUDUCHERRY": "puducherry",
    "TELANGANA": "telangana",
    "LADAKH": "ladakh",
}

# Entities whose boundaries the report does not list directly: the sum of their parts.
COMPONENTS = {
    "andhra-pradesh-undivided": ("andhra-pradesh", "telangana"),
    "jammu-and-kashmir-state": ("jammu-and-kashmir", "ladakh"),
    "dadra-and-nagar-haveli-and-daman-and-diu": ("dadra-and-nagar-haveli", "daman-and-diu"),
}

_NAME_WORD = re.compile(r"[A-Z&()]+\*?")
_NUMBER = re.compile(r"^\d{1,3}(?:,\d{2,3})*$")
_YEAR = re.compile(r"^20[1-3]\d$")


@dataclass(frozen=True)
class Projection:
    persons: int  # thousands, as published
    male: int
    female: int


def _value(text: str) -> int:
    return int(text.replace(",", ""))


def _table_pages(pdf) -> Iterable:
    for page in pdf.pages:
        first = (page.extract_text() or "").lstrip().split("\n", 1)[0]
        if re.match(rf"^TABLE\s*[-–]\s*{TABLE}\b", first):
            yield page


def _page(page) -> dict[tuple[str, int], Projection]:
    words = page.extract_words()
    persons = sorted((w for w in words if w["text"] in ("Persons", "Person")), key=lambda w: w["x0"])
    if not persons:
        raise ValueError(f"page {page.page_number}: no Persons header")
    header_top = persons[0]["top"]
    columns = sorted(
        (w for w in words if abs(w["top"] - header_top) < 3 and w["text"] != "Year"),
        key=lambda w: w["x0"],
    )
    if len(columns) % 3:
        raise ValueError(f"page {page.page_number}: {len(columns)} header columns")
    triples = [columns[i : i + 3] for i in range(0, len(columns), 3)]
    spans = [(t[0]["x0"] - 25, t[2]["x1"] + 25) for t in triples]
    title_bottom = max(w["bottom"] for w in words if w["text"] == "1st")

    names: list[list[dict]] = [[] for _ in triples]
    for w in words:
        if title_bottom < w["top"] < header_top and _NAME_WORD.fullmatch(w["text"]):
            centre = (w["x0"] + w["x1"]) / 2
            for k, (left, right) in enumerate(spans):
                if left <= centre <= right:
                    names[k].append(w)
    slugs = []
    for k, parts in enumerate(names):
        label = " ".join(
            w["text"].rstrip("*") for w in sorted(parts, key=lambda w: (round(w["top"]), w["x0"]))
        )
        if label not in NAMES:
            raise ValueError(f"page {page.page_number}: unknown column {k + 1} name {label!r}")
        slugs.append(NAMES[label])

    years = [
        w
        for w in words
        if _YEAR.match(w["text"]) and w["top"] > header_top and w["x0"] < columns[0]["x0"] - 5
    ]
    # Below the header sits a row of column numbers ("1 2 3 ..."); data starts near the first year.
    data_top = min(y["top"] for y in years) - 8
    data_bottom = max(y["top"] for y in years) + 8  # the page number sits below the table
    cells: dict[tuple[int, int], list[int]] = {}
    for w in words:
        if not data_top <= w["top"] <= data_bottom or not _NUMBER.match(w["text"]) or w in years:
            continue
        row = min(years, key=lambda y: abs(y["top"] - w["top"]))
        centre = (w["x0"] + w["x1"]) / 2
        col = min(range(len(columns)), key=lambda c: abs((columns[c]["x0"] + columns[c]["x1"]) / 2 - centre))
        cells.setdefault((int(row["text"]), col), []).append(_value(w["text"]))

    out: dict[tuple[str, int], Projection] = {}
    for year in sorted({int(y["text"]) for y in years}):
        for k, slug in enumerate(slugs):
            got = [cells.get((year, 3 * k + j), []) for j in range(3)]
            if any(len(g) != 1 for g in got):
                raise ValueError(f"page {page.page_number}: {slug} {year} has cells {got}")
            p, m, f = (g[0] for g in got)
            if abs(p - m - f) > 2:  # published figures are rounded
                raise ValueError(f"{slug} {year}: persons {p} != male {m} + female {f}")
            out[(slug, year)] = Projection(p, m, f)
    return out


def parse(pdf_bytes: bytes) -> dict[tuple[str, int], Projection]:
    """(report slug, year) -> projection as on 1 July of that year."""
    out: dict[tuple[str, int], Projection] = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in _table_pages(pdf):
            out.update(_page(page))
    missing = set(NAMES.values()) - {slug for slug, _ in out}
    if missing:
        raise ValueError(f"no projections for {', '.join(sorted(missing))}")
    return out


def rows(parsed: dict[tuple[str, int], Projection], entities) -> list[dict[str, object]]:
    """One row per entity valid on 1 July of each year, summing parts where needed."""
    years = sorted({year for _, year in parsed})
    out = []
    for year in years:
        on = date(year, 7, 1)
        for entity in (e.to_entity() for e in entities):
            if entity.type not in ("country", "state", "ut") or not entity.valid_on(on):
                continue
            parts = COMPONENTS.get(entity.slug, (entity.slug,))
            values = [parsed[(part, year)] for part in parts]
            out.append(
                {
                    "entity_slug": entity.slug,
                    "year": year,
                    "persons_000": sum(v.persons for v in values),
                    "male_000": sum(v.male for v in values),
                    "female_000": sum(v.female for v in values),
                }
            )
    return out
