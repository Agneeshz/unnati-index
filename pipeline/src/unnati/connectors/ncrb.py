"""NCRB Crime in India: state/UT crime rates from the annual report's PDF volumes.

NCRB's own site lists its files through JavaScript, so the connector reads OpenCity's mirror
(CKAN packages `crime-in-india-<year>`, sourced from ncrb.gov.in). Every edition from 2022 on
is read, and each one contributes its own year: the State/UT tables show three years of
counts but the rate and charge-sheeting rate only for the edition's year.

The tables used share one layout: SL, State/UT, three years of cases, mid-year population (in
lakh, MoHFW projections), the rate, then the charge-sheeting rate. Long names wrap around
their numbers ("D&N Haveli and" / "31 1273 865 ..." / "Daman & Diu").

Volume 3 (court disposal: conviction rate, trial pendency) is not mirrored for recent years
(OpenCity's 2024 "Vol 3" is a copy of Vol 2), so it is downloaded by hand from ncrb.gov.in into
`pipeline/manual-downloads/ncrb_cii/<year>/` and committed; `local_volumes()` finds it."""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
import pdfplumber

from unnati.connectors.mospi import number
from unnati.core.entities import EntityResolver, UnknownEntityError
from unnati.core.http import PoliteClient
from unnati.core.periods import calendar_year
from unnati.observations import Observation

CKAN_PACKAGE = "https://data.opencity.in/api/3/action/package_show"
FIRST_EDITION = 2022


@dataclass(frozen=True)
class Column:
    indicator_id: str
    from_right: int  # 1 = last number on the row
    note: str | None = None


# table id -> (volume, columns read from it)
TABLES: dict[str, tuple[int, tuple[Column, ...]]] = {
    "1A.1": (1, (Column("chargesheeting-rate", 1),)),
    "1A.3": (1, (Column("crime-rate-total", 2),)),
    "2A.1": (1, (Column("murder-rate", 2),)),
    "3A.1": (1, (Column("crimes-against-women-rate", 2, "per lakh female population"),)),
    "4A.1": (
        1,
        (
            Column(
                "crimes-against-children-rate", 2, "per lakh children, using the 2011 Census child population"
            ),
        ),
    ),
    "9A.1": (2, (Column("cybercrime-rate", 2),)),
    "18A.2": (
        3,
        (
            Column("conviction-rate", 2, "IPC/BNS cases convicted / trials completed"),
            Column("trial-pendency", 1, "IPC/BNS cases pending trial at year end / total cases for trial"),
        ),
    ),
}
# Tables spread over several pages whose wanted columns are only on the last ("Concluded") page.
LAST_PAGE_ONLY = {"18A.2"}
MANUAL_DIR = Path(__file__).resolve().parents[3] / "manual-downloads" / "ncrb_cii"

_VOLUME = re.compile(r"(?i)\bvol(?:ume)?\.?\s*-?\s*(\d)\b")
_VALUE = re.compile(r"^(?:-?\d[\d,]*(?:\.\d+)?|-)$")
_ROW = re.compile(r"^(\d{1,2})\s+(.*)$")
_TOTAL = re.compile(r"(?i)^total\s*\(?all[- ]india\)?\s+(.*)$")


@dataclass
class Edition:
    year: int
    package: dict  # CKAN package metadata
    volumes: dict[int, str]  # volume number -> URL


def _package(http: PoliteClient, year: int) -> dict | None:
    try:
        return http.get(CKAN_PACKAGE, params={"id": f"crime-in-india-{year}"}).json()["result"]
    except httpx.HTTPStatusError as err:
        if err.response.status_code == 404:
            return None
        raise


def _volumes(package: dict) -> dict[int, str]:
    """Volume number -> PDF URL. A URL listed under two volume names is ignored (OpenCity's 2024
    "Vol 3" is a copy of Vol 2)."""
    found: dict[int, str] = {}
    urls: dict[str, int] = {}
    for resource in package["resources"]:
        match = _VOLUME.search(resource.get("name", ""))
        if not match or not resource["url"].lower().endswith(".pdf"):
            continue
        found[int(match.group(1))] = resource["url"]
        urls[resource["url"]] = urls.get(resource["url"], 0) + 1
    return {vol: url for vol, url in found.items() if urls[url] == 1}


def editions(http: PoliteClient, today: date) -> list[Edition]:
    out = []
    for year in range(FIRST_EDITION, today.year + 1):
        package = _package(http, year)
        if package is not None:
            out.append(Edition(year, package, _volumes(package)))
    if not out:
        raise RuntimeError("no Crime in India edition found on OpenCity")
    return out


def fingerprint(found: list[Edition]) -> str:
    """Cheap change check: the editions' resource metadata, without downloading the PDFs."""
    meta = {
        e.year: sorted(
            (r["id"], r["url"], r.get("last_modified") or r.get("created") or "")
            for r in e.package["resources"]
            if r["url"] in e.volumes.values()
        )
        for e in found
    }
    return hashlib.sha256(json.dumps(meta, sort_keys=True).encode()).hexdigest()


def fetch(http: PoliteClient, found: list[Edition]) -> dict[int, dict[int, bytes]]:
    """year -> volume -> PDF bytes, for the volumes the tables need."""
    needed = {volume for volume, _ in TABLES.values()}
    return {
        e.year: {vol: http.get(url).content for vol, url in e.volumes.items() if vol in needed} for e in found
    }


def local_volumes() -> dict[int, dict[int, bytes]]:
    """year -> {3: PDF bytes} for hand-downloaded Volume 3 files."""
    found: dict[int, dict[int, bytes]] = {}
    for path in sorted(MANUAL_DIR.glob("*/*.pdf")):
        if path.parent.name.isdigit() and re.search(r"(?i)volume[\s_-]*(iii|3)|vol[\s_-]*3", path.stem):
            found.setdefault(int(path.parent.name), {})[3] = path.read_bytes()
    return found


def table_text(pdf_bytes: bytes, table_ids: Iterable[str]) -> dict[str, str]:
    """Text of each wanted table (all its pages), found by the "TABLE <id>" first line."""
    wanted = {re.compile(rf"^TABLE\s+{re.escape(t)}\s*$"): t for t in table_ids}
    out: dict[str, list[str]] = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            first = text.lstrip().split("\n", 1)[0].strip()
            for pattern, table_id in wanted.items():
                if pattern.match(first):
                    if table_id in LAST_PAGE_ONLY and "(Concluded)" not in text[:300]:
                        continue
                    out.setdefault(table_id, []).append(text)
    return {t: "\n".join(pages) for t, pages in out.items()}


def _split(rest: str) -> tuple[str, list[str]]:
    """Name and trailing values of a row's text after the SL number."""
    tokens = rest.split()
    i = len(tokens)
    while i > 0 and _VALUE.match(tokens[i - 1]):
        i -= 1
    return " ".join(tokens[:i]), tokens[i:]


def rows(text: str) -> Iterable[tuple[str, list[str]]]:
    """(place name, values) for each State/UT row and the all-India total."""
    lines = [line.strip() for line in text.split("\n")]
    for i, line in enumerate(lines):
        total = _TOTAL.match(line)
        if total:
            name, values = _split(total.group(1))
            if values and not name:
                yield "All India", values
            continue
        match = _ROW.match(line)
        if not match:
            continue
        name, values = _split(match.group(2))
        if len(values) < 3:
            continue
        if not name:  # the name wraps around the numbers
            before = lines[i - 1] if i > 0 else ""
            after = lines[i + 1] if i + 1 < len(lines) else ""
            name = f"{before} {after}".strip()
        yield name, values


def observations(
    pdfs: dict[int, dict[int, bytes]], resolver: EntityResolver
) -> tuple[list[Observation], list[str]]:
    out: list[Observation] = []
    problems: list[str] = []
    for year, volumes in sorted(pdfs.items()):
        period = calendar_year(year)
        for volume, pdf in sorted(volumes.items()):
            wanted = [t for t, (vol, _) in TABLES.items() if vol == volume]
            texts = table_text(pdf, wanted)
            for table_id in wanted:
                if table_id not in texts:
                    problems.append(f"{year} vol {volume}: table {table_id} not found")
                    continue
                columns = TABLES[table_id][1]
                seen: set[str] = set()
                for name, values in rows(texts[table_id]):
                    try:
                        entity = resolver.resolve(name, period)
                    except UnknownEntityError as err:
                        problems.append(f"{year} table {table_id}: {err}")
                        continue
                    if entity is None or entity.slug in seen:
                        continue
                    seen.add(entity.slug)
                    for column in columns:
                        value = number(values[-column.from_right])
                        if value is None:
                            continue
                        note = f"Crime in India {year}, table {table_id}"
                        if column.note:
                            note += f"; {column.note}"
                        out.append(Observation(column.indicator_id, entity.slug, period, value, note=note))
                if len(seen) < 37:
                    problems.append(f"{year} table {table_id}: only {len(seen)} rows read")
    return out, problems


# --- Metropolitan cities (Volume 1) ---------------------------------------------------------
# Tables 1B.3 (total IPC/BNS + SLL crime), 2B.1 (murder) and 3B.1 (crime against women) list the
# 19 cities over 2 million people: SL, city (its state in brackets on the next line), cases in
# the last three years, population in lakh (Census 2011; women only for 3B.1), the latest
# year's rate and charge-sheeting rate. Earlier years' rates use the same 2011 population.

CITY_TABLES = {
    "1B.3": ("crime-rate-total", "chargesheeting-rate"),
    "2B.1": ("murder-rate", None),
    "3B.1": ("crimes-against-women-rate", None),
}
CITY_NOTE = (
    "rate on the city's 2011 Census population, as NCRB publishes it, so it overstates crime "
    "where the city has grown since"
)
_CITY_ROW = re.compile(r"^(\d{1,2})\s+(.*)$")


def city_rows(text: str) -> Iterable[tuple[str, list[str]]]:
    """(city name, [cases y-2, y-1, y, population lakh, rate, charge-sheeting rate])."""
    lines = [line.strip() for line in text.split("\n")]
    for i, line in enumerate(lines):
        match = _CITY_ROW.match(line)
        if not match:
            continue
        name, values = _split(match.group(2))
        if len(values) != 6:
            continue
        yield (name or (lines[i - 1] if i else "")).strip(), values


def city_observations(pdfs: dict[int, dict[int, bytes]]) -> tuple[list[Observation], list[str]]:
    from unnati.core.entities import normalize_name
    from unnati.reference import city_names

    slugs = city_names("ncrb")
    by_key: dict[tuple[str, str, int], Observation] = {}
    problems: list[str] = []
    for year, volumes in sorted(pdfs.items()):
        if 1 not in volumes:
            continue
        texts = table_text(volumes[1], CITY_TABLES)
        for table_id, (indicator_id, chargesheet_id) in CITY_TABLES.items():
            if table_id not in texts:
                problems.append(f"{year} vol 1: city table {table_id} not found")
                continue
            seen = set()
            for name, values in city_rows(texts[table_id]):
                slug = slugs.get(normalize_name(name))
                if slug is None:
                    problems.append(f"{year} table {table_id}: unknown city {name!r}")
                    continue
                seen.add(slug)
                cases, population = [number(v) for v in values[:3]], number(values[3])
                note = f"Crime in India {year}, table {table_id}; {CITY_NOTE}"
                rate = number(values[4])
                if rate is not None:
                    by_key[(indicator_id, slug, year)] = Observation(
                        indicator_id, slug, calendar_year(year), rate, note=note
                    )
                # Earlier years from this edition fill gaps only; their own edition wins.
                for back, count in zip((2, 1), cases[:2], strict=True):
                    if count is not None and population:
                        key = (indicator_id, slug, year - back)
                        by_key.setdefault(
                            key,
                            Observation(
                                indicator_id,
                                slug,
                                calendar_year(year - back),
                                round(count / population, 1),  # population in lakh
                                note=note,
                            ),
                        )
                if chargesheet_id and number(values[5]) is not None:
                    by_key[(chargesheet_id, slug, year)] = Observation(
                        chargesheet_id,
                        slug,
                        calendar_year(year),
                        number(values[5]),
                        note=f"Crime in India {year}, table {table_id}",
                    )
            if len(seen) < len(set(slugs.values())):
                problems.append(f"{year} table {table_id}: only {len(seen)} cities read")
    return list(by_key.values()), problems


# --- Accidental Deaths & Suicides in India (ADSI) ---------------------------------------------
# Table 2.2, "Incidence and Rate of Suicides (State/UT-wise)", is published as its own PDF from
# the 2023 edition on (2022 is only in the full report). Rows run SL, State/UT, suicides, share
# of the total, mid-year population (lakh), rate; city rows follow the all-India total.

ADSI_PACKAGE = "accidental-deaths-and-suicides-in-india-{year}"
ADSI_FIRST_EDITION = 2023
_ADSI_TABLE = re.compile(r"(?i)^(suicide incidence & rate|incidence and rate of suicides - \d{4} \(state)")


def adsi_tables(http: PoliteClient, today: date) -> dict[int, dict]:
    """year -> the CKAN resource for its Table 2.2."""
    out = {}
    for year in range(ADSI_FIRST_EDITION, today.year + 1):
        try:
            package = http.get(CKAN_PACKAGE, params={"id": ADSI_PACKAGE.format(year=year)}).json()["result"]
        except httpx.HTTPStatusError as err:
            if err.response.status_code == 404:
                continue
            raise
        matches = [r for r in package["resources"] if _ADSI_TABLE.match(r.get("name", "").strip())]
        if not matches:
            raise RuntimeError(f"ADSI {year}: no suicide incidence-and-rate table")
        out[year] = matches[0]
    if not out:
        raise RuntimeError("no ADSI edition found on OpenCity")
    return out


def adsi_observations(
    pdfs: dict[int, bytes], resolver: EntityResolver
) -> tuple[list[Observation], list[str]]:
    out: list[Observation] = []
    problems: list[str] = []
    for year, pdf_bytes in sorted(pdfs.items()):
        period = calendar_year(year)
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        if f"Incidence and Rate of Suicides – {year}" not in text.replace("-", "–"):
            problems.append(f"ADSI {year}: table title not found")
        states, _, _ = text.partition("TOTAL (ALL INDIA)")
        all_india = text[len(states) :].split("\n", 1)[0]
        seen: set[str] = set()
        for name, values in rows(states + "\n" + all_india):
            try:
                entity = resolver.resolve(name, period)
            except UnknownEntityError as err:
                problems.append(f"ADSI {year}: {err}")
                continue
            if entity is None or entity.slug in seen:
                continue
            seen.add(entity.slug)
            value = number(values[-1])
            if value is not None:
                out.append(
                    Observation("suicide-rate", entity.slug, period, value, note=f"ADSI {year}, table 2.2")
                )
        if len(seen) < 37:
            problems.append(f"ADSI {year}: only {len(seen)} rows read")
    return out, problems
