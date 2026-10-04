"""CPCB's daily National Air Quality Index bulletin: city AQI (24-hour average at 4 PM), rolled
up to a daily state average.

cpcb.nic.in publishes one PDF a day at a dated URL, without an API key. Its table lists each
city with the AQI category, the index value, the prominent pollutant and how many of its
stations reported. Cities map to states through `reference/cpcb_cities.csv` (seeded from CPCB's
own city list in MoSPI EnviStats, the rest checked by hand); a new city name is reported as a
problem until it is added there. A state's daily value is the mean over its reporting cities.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, timedelta
from functools import cache
from importlib.resources import files

import httpx
import pdfplumber

from unnati.core.entities import normalize_name
from unnati.core.http import PoliteClient
from unnati.core.periods import day
from unnati.observations import Observation

URL = "https://cpcb.nic.in/upload/Downloads/AQI_Bulletin_{day:%Y%m%d}.pdf"
WINDOW_DAYS = 7  # the daily run re-reads the last week, so a missed day is picked up


@dataclass(frozen=True)
class CityReading:
    city: str
    aqi: int
    category: str
    pollutant: str
    stations: str  # "reporting/total"


@cache
def city_states() -> dict[str, str]:
    path = files("unnati.reference").joinpath("cpcb_cities.csv")
    with path.open(encoding="utf-8", newline="") as fh:
        # Keyed by normalised name: older bulletins write cities in lower case.
        return {normalize_name(row["city"]): row["state_slug"] for row in csv.DictReader(fh)}


def parse(pdf_bytes: bytes) -> list[CityReading]:
    out = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    if not row or len(row) < 6 or not str(row[0] or "").strip().isdigit():
                        continue
                    value = str(row[3] or "").strip()
                    if not value.isdigit():
                        continue
                    pollutant = re.sub(r"\s+", " ", str(row[4] or "")).strip()
                    out.append(
                        CityReading(
                            city=re.sub(r"\s+", " ", str(row[1])).strip(),
                            aqi=int(value),
                            category=str(row[2] or "").strip(),
                            pollutant=pollutant,
                            stations=str(row[5] or "").strip(),
                        )
                    )
    return out


def fetch(http: PoliteClient, today: date, days: int = WINDOW_DAYS) -> dict[date, bytes]:
    """Bulletins for the last `days` days (today's appears in the evening, so it starts at
    yesterday); days without a bulletin are skipped."""
    out = {}
    for back in range(1, days + 1):
        when = today - timedelta(days=back)
        try:
            out[when] = http.get(URL.format(day=when)).content
        except httpx.HTTPStatusError as err:
            if err.response.status_code != 404:
                raise
    return out


def observations(bulletins: dict[date, bytes]) -> tuple[list[Observation], list[str]]:
    states = city_states()
    out: list[Observation] = []
    problems: list[str] = []
    for when, pdf in sorted(bulletins.items()):
        readings = parse(pdf)
        if not readings:
            problems.append(f"CPCB bulletin {when}: no city rows read")
            continue
        by_state: dict[str, list[CityReading]] = {}
        for r in readings:
            slug = states.get(normalize_name(r.city))
            if slug is None:
                problems.append(f"CPCB bulletin: city {r.city!r} has no state in cpcb_cities.csv")
                continue
            by_state.setdefault(slug, []).append(r)
        everyone = [r.aqi for r in readings]
        for slug, rows in [*by_state.items(), ("india", None)]:
            values = [r.aqi for r in rows] if rows else everyone
            worst = max(rows, key=lambda r: r.aqi) if rows else None
            note = f"CPCB AQI bulletin: mean of {len(values)} cit{'y' if len(values) == 1 else 'ies'}"
            if worst:
                note += f"; highest {worst.city} {worst.aqi} ({worst.category})"
            out.append(
                Observation("aqi-daily-mean", slug, day(when), round(sum(values) / len(values), 1), note=note)
            )
    return out, sorted(set(problems))
