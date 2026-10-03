"""MoRTH Road Accidents in India: road accident deaths per lakh population, by state/UT.

The report's state-wise fatalities table is published as CSV on OpenCity (CKAN packages
`road-accidents-in-india-<year>`, sourced from morth.gov.in). The latest edition carries five
years of deaths, which supersede earlier editions' figures. The rate uses the MoHFW mid-year
population projections (`reference/population.csv`), the same denominators NCRB uses.

Jammu & Kashmir's 2020 figure includes Ladakh, so that one value is skipped."""

from __future__ import annotations

import csv
import io
import re
from datetime import date

import httpx

from unnati.connectors.mospi import number
from unnati.core.entities import EntityResolver, UnknownEntityError
from unnati.core.http import PoliteClient
from unnati.core.periods import calendar_year
from unnati.observations import Observation
from unnati.reference import Population

CKAN_PACKAGE = "https://data.opencity.in/api/3/action/package_show"
FIRST_EDITION = 2024  # earlier editions' CSVs use other layouts; 2024 covers 2020 onwards

_YEAR_KILLED = re.compile(r"^(\d{4}) Killed$")
_FOOTNOTE = re.compile(r"\s*[#*]+\s*$")


def latest(http: PoliteClient, today: date) -> tuple[int, dict]:
    """The newest edition's year and its state-wise fatalities CSV resource."""
    for year in range(today.year, FIRST_EDITION - 1, -1):
        try:
            response = http.get(CKAN_PACKAGE, params={"id": f"road-accidents-in-india-{year}"})
        except httpx.HTTPStatusError as err:
            if err.response.status_code == 404:
                continue
            raise
        for resource in response.json()["result"]["resources"]:
            if re.search(r"(?i)state-?wise road fatalities", resource.get("name", "")):
                return year, resource
        raise RuntimeError(f"road-accidents-in-india-{year} has no state-wise fatalities CSV")
    raise RuntimeError("no Road Accidents in India edition found on OpenCity")


def observations(
    text: str, edition: int, resolver: EntityResolver, population: dict[tuple[str, int], Population]
) -> tuple[list[Observation], list[str]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    years = {
        int(m.group(1)): column
        for column in reader.fieldnames or []
        if (m := _YEAR_KILLED.match(column.strip()))
    }
    if not years:
        raise ValueError(f"no '<year> Killed' columns in {reader.fieldnames}")
    out: list[Observation] = []
    problems: list[str] = []
    for row in reader:
        raw_name = (row.get("State") or "").strip()
        if not raw_name:
            continue
        footnoted = bool(_FOOTNOTE.search(raw_name))
        name = _FOOTNOTE.sub("", raw_name)
        for year, column in sorted(years.items()):
            killed = number(row[column])
            if killed is None:
                continue
            period = calendar_year(year)
            try:
                entity = resolver.resolve(name, period)
            except UnknownEntityError as err:
                problems.append(f"{year}: {err}")
                continue
            if entity is None:
                continue
            if footnoted and entity.slug == "jammu-and-kashmir" and year < 2021:
                continue  # "# includes Ladakh for 2020"
            people = population.get((entity.slug, year))
            if people is None:
                problems.append(f"{entity.slug} {year}: no population projection")
                continue
            out.append(
                Observation(
                    "road-deaths-per-lakh",
                    entity.slug,
                    period,
                    round(killed / people.persons * 100_000, 2),
                    note=f"Road Accidents in India {edition}: {int(killed):,} deaths;"
                    " MoHFW projected population",
                )
            )
    return out, problems
