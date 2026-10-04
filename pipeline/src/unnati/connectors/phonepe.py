"""PhonePe Pulse: digital payment transactions per person, by state.

PhonePe publishes quarterly state totals on GitHub (github.com/PhonePe/pulse, CDLA-Permissive-2.0).
One file per quarter (`data/map/transaction/hover/country/india/<year>/<q>.json`) holds every
state's transaction count. Values are transactions per person per year: each complete calendar
year, plus the latest four quarters, divided by the MoHFW mid-year population projection.
PhonePe is one app among several and its share varies by state, so this is a proxy (the
indicator's caveat says so)."""

from __future__ import annotations

from datetime import date

import httpx

from unnati.connectors.mospi import resolve_current_first
from unnati.core.entities import EntityResolver, UnknownEntityError
from unnati.core.http import PoliteClient
from unnati.core.periods import Period, calendar_year, span
from unnati.observations import Observation
from unnati.reference import Population

RAW = "https://raw.githubusercontent.com/PhonePe/pulse/main/data/map/transaction/hover/country/india/{year}/{q}.json"
FIRST_YEAR = 2018
QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def fetch(http: PoliteClient, today: date) -> dict[tuple[int, int], dict[str, float]]:
    """(year, quarter) -> {state name: transaction count}, for every published quarter."""
    out: dict[tuple[int, int], dict[str, float]] = {}
    for year in range(FIRST_YEAR, today.year + 1):
        for q in range(1, 5):
            if date(year, *QUARTER_END[q]) > today:
                break
            try:
                payload = http.get(RAW.format(year=year, q=q)).json()
            except httpx.HTTPStatusError as err:
                if err.response.status_code == 404:
                    continue
                raise
            out[(year, q)] = {
                row["name"]: sum(m["count"] for m in row["metric"] if m.get("type") == "TOTAL")
                for row in payload["data"]["hoverDataList"]
            }
    return out


def observations(
    quarters: dict[tuple[int, int], dict[str, float]],
    resolver: EntityResolver,
    population: dict[tuple[str, int], Population],
) -> tuple[list[Observation], list[str]]:
    out: list[Observation] = []
    problems: list[str] = []
    windows: list[tuple[Period, list[tuple[int, int]]]] = []
    years = sorted({y for y, _ in quarters})
    for year in years:
        qs = [(year, q) for q in range(1, 5)]
        if all(k in quarters for k in qs):
            windows.append((calendar_year(year), qs))
    ordered = sorted(quarters)
    if len(ordered) >= 4 and ordered[-1][1] != 4:  # latest four quarters, unless that is a calendar year
        last4 = ordered[-4:]
        (y0, q0), (y1, q1) = last4[0], last4[-1]
        start = date(y0, QUARTER_END[q0][0] - 2, 1)
        end = date(y1, *QUARTER_END[q1])
        windows.append((span(start, end, f"{start:%b %Y}–{end:%b %Y}", "multi_year"), last4))
    for period, qs in windows:
        totals: dict[str, float] = {}
        for k in qs:
            for name, count in quarters[k].items():
                totals[name] = totals.get(name, 0) + count
        for name, count in totals.items():
            try:  # PhonePe reports every year on today's boundaries (Ladakh, merged DNH & DD)
                entity = resolve_current_first(resolver, name, period, date.today())
            except UnknownEntityError as err:
                problems.append(str(err))
                continue
            if entity is None:
                continue
            people = population.get((entity.slug, period.end.year))
            if people is None:
                problems.append(f"{entity.slug} {period.end.year}: no population projection")
                continue
            note = f"PhonePe Pulse: {count / 1e7:,.1f} crore transactions in {period.label}"
            out.append(
                Observation(
                    "digital-payments-per-capita",
                    entity.slug,
                    period,
                    round(count / people.persons, 1),
                    note=note,
                )
            )
        india = sum(totals.values())
        people = population.get(("india", period.end.year))
        if people:
            note = f"PhonePe Pulse: {india / 1e7:,.1f} crore transactions in {period.label} (sum of states)"
            out.append(
                Observation(
                    "digital-payments-per-capita",
                    "india",
                    period,
                    round(india / people.persons, 1),
                    note=note,
                )
            )
    return out, sorted(set(problems))
