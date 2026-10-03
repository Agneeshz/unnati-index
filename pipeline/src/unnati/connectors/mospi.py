"""MoSPI's open API (api.mospi.gov.in), the data behind the eSankhyiki portal.

Endpoints and parameters follow MoSPI's own published Swagger specs
(github.com/nso-india/esankhyiki-mcp). The server still needs TLS legacy renegotiation, so this
connector relaxes exactly that, keeping certificate and hostname checks (see core.http).

Responses are paged (at most 200 rows per page)."""

from __future__ import annotations

import calendar
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from unnati.core.entities import EntityResolver, UnknownEntityError
from unnati.core.http import PoliteClient, legacy_renegotiation_context
from unnati.core.periods import calendar_year, day, month, parse_period
from unnati.observations import Observation

BASE_URL = "https://api.mospi.gov.in"
PAGE_SIZE = 200


def client() -> PoliteClient:
    return PoliteClient(min_interval=0.5, timeout=120, ssl_context=legacy_renegotiation_context())


def fetch_all(http: PoliteClient, path: str, params: Mapping[str, object]) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        payload = http.get(f"{BASE_URL}{path}", params={**params, "limit": PAGE_SIZE, "page": page}).json()
        if payload.get("success") is False:
            raise RuntimeError(f"MoSPI API error for {path}: {payload.get('message')}")
        rows.extend(payload.get("data") or [])
        meta = payload.get("meta_data") or {}
        if page >= int(meta.get("totalPages") or 1):
            return rows
        page += 1


# --- Periodic Labour Force Survey (annual, calendar years from 2022) ---------------------------
#
# The API's year_type and education filters misbehave (education_code=10 matches nothing;
# year_type_code widens the result), so only the reliable filters go to the server and each
# row is checked client-side. The calendar-year series (2022 onwards, all 36 states/UTs) is
# used; the older July-June series is left out so one chart never mixes year definitions.


@dataclass(frozen=True)
class PlfsSeries:
    indicator_code: int  # 1 = LFPR, 3 = unemployment rate
    gender_code: int  # 2 = female, 3 = all persons
    age_code: int  # 1 = 15 and above, 2 = 15-29
    indicator_id: str


PLFS_SERIES = (
    PlfsSeries(3, 3, 1, "unemployment-rate"),
    PlfsSeries(3, 3, 2, "youth-unemployment-rate"),
    PlfsSeries(1, 3, 1, "lfpr"),
    PlfsSeries(1, 2, 1, "female-lfpr"),
)
# Headline annual measures: usual status (PS+SS), rural + urban, all religions/groups/education.
PLFS_FIXED = {
    "frequency_code": 1,
    "weekly_status_code": 1,
    "sector_code": 3,
    "religion_code": 1,
    "social_category_code": 1,
    "Format": "JSON",
}
PLFS_ROW = {  # what every accepted row must say, checked client-side
    "year_type": "Calendar Year",
    "sector": "rural + urban",
    "weekly_status": "PS+SS",
    "religion": "all",
    "socialGroup": "all",
    "General_Education": "all",
}


def fetch_plfs_state(http: PoliteClient) -> dict[str, list[dict]]:
    return {
        s.indicator_id: fetch_all(
            http,
            "/api/plfs/getData",
            {
                **PLFS_FIXED,
                "indicator_code": s.indicator_code,
                "gender_code": s.gender_code,
                "age_code": s.age_code,
            },
        )
        for s in PLFS_SERIES
    }


PLFS_AGE = {1: "15 years and above", 2: "15-29 years"}
PLFS_GENDER = {2: "female", 3: "person"}


def plfs_observations(
    rows_by_indicator: Mapping[str, list[dict]], resolver: EntityResolver
) -> tuple[list[Observation], list[str]]:
    """PLFS reports each year on the boundaries of that year, so names resolve by period."""
    observations: list[Observation] = []
    problems: list[str] = []
    series = {s.indicator_id: s for s in PLFS_SERIES}
    for indicator_id, rows in rows_by_indicator.items():
        expected = {
            **PLFS_ROW,
            "AgeGroup": PLFS_AGE[series[indicator_id].age_code],
            "gender": PLFS_GENDER[series[indicator_id].gender_code],
        }
        for row in rows:
            if row.get("value") in (None, "", "NA", "-"):
                continue
            if any(row.get(k) != v for k, v in expected.items()):
                continue
            period = calendar_year(int(row["year"]))
            try:
                entity = resolver.resolve(row["state"], period)
            except UnknownEntityError as err:
                problems.append(str(err))
                continue
            if entity is None:
                continue
            observations.append(
                Observation(
                    indicator_id=indicator_id,
                    entity_slug=entity.slug,
                    period=period,
                    value=float(row["value"]),
                    note="PLFS annual, usual status (PS+SS)",
                )
            )
    return observations, sorted(set(problems))


# --- Consumer Price Index: monthly retail inflation by state ----------------------------------

CPI_PARAMS = {"base_year": "2012", "series": "Current", "sector_code": 3, "group_code": 0, "Format": "JSON"}
MONTHS = {name: i for i, name in enumerate(calendar.month_name) if name}


def fetch_cpi_state(http: PoliteClient) -> list[dict]:
    """General index, rural + urban, every state and month (base 2012)."""
    return fetch_all(http, "/api/cpi/getCPIIndex", CPI_PARAMS)


# After the January 2020 merger CPI still publishes these two areas separately. Each is only part
# of the merged UT, so neither may stand in for it.
PARTIAL_AREAS = {"dadra & nagar haveli", "daman & diu"}
MERGER = date(2020, 1, 26)


def cpi_observations(rows: list[dict], resolver: EntityResolver) -> tuple[list[Observation], list[str]]:
    observations: list[Observation] = []
    problems: list[str] = []
    partial: set[str] = set()
    for row in rows:
        if row.get("subgroup") != "General-Overall" or row.get("inflation") in (None, "", "NA", "-"):
            continue
        period = month(int(row["year"]), MONTHS[row["month"]])
        if row["state"].strip().lower() in PARTIAL_AREAS and period.start >= MERGER:
            partial.add(row["state"])
            continue
        try:
            entity = resolver.resolve(row["state"], period)
        except UnknownEntityError as err:
            problems.append(str(err))
            continue
        if entity is None:
            continue
        observations.append(
            Observation(
                indicator_id="cpi-inflation",
                entity_slug=entity.slug,
                period=period,
                value=float(row["inflation"]),
                is_provisional=row.get("status") == "P",
                note="CPI (combined), base 2012; year-on-year change",
            )
        )
    problems += [
        f"{name}: published after the 2020 merger for part of the UT only; skipped"
        for name in sorted(partial)
    ]
    return observations, sorted(set(problems))


# --- National Accounts: state domestic product -------------------------------------------------


@dataclass(frozen=True)
class NasSeries:
    indicator_code: int
    price: str  # "current_price" or "constant_price"
    indicator_id: str


# 2011-12 base series (the 2022-23 base has no state data yet).
NAS_BASE_YEAR = "2011-12"
NAS_SERIES = (
    NasSeries(23, "current_price", "gsdp-current"),
    NasSeries(23, "constant_price", "gsdp-constant"),
    NasSeries(25, "current_price", "per-capita-nsdp-current"),
    NasSeries(25, "constant_price", "per-capita-nsdp-constant"),
    NasSeries(26, "constant_price", "gsdp-growth-real"),
)


def fetch_nas_state(http: PoliteClient) -> dict[int, list[dict]]:
    codes = sorted({s.indicator_code for s in NAS_SERIES})
    return {
        code: fetch_all(
            http,
            "/api/nas/getNASData",
            {
                "base_year": NAS_BASE_YEAR,
                "series": "Current",
                "frequency_code": "Annually",
                "indicator_code": code,
                "Format": "JSON",
            },
        )
        for code in codes
    }


def nas_observations(
    rows_by_code: Mapping[int, list[dict]], resolver: EntityResolver, today: date
) -> tuple[list[Observation], list[str]]:
    """MoSPI back-casts state accounts to *current* boundaries (Telangana and today's Andhra
    Pradesh are reported separately from 2011-12), so names resolve as of today, not as of
    the data year. The two latest fiscal years are advance/quick estimates: provisional."""
    observations: list[Observation] = []
    problems: list[str] = []
    as_of = day(today)
    provisional_from = date(today.year - 1, 3, 31)
    for series in NAS_SERIES:
        for row in rows_by_code.get(series.indicator_code, []):
            raw = row.get(series.price)
            if raw in (None, "", "NA", "-"):
                continue
            period = parse_period(row["year"])
            try:
                entity = resolver.resolve(row["state"], as_of)
            except UnknownEntityError as err:
                problems.append(str(err))
                continue
            if entity is None:
                continue
            note = f"NAS base {NAS_BASE_YEAR}, back-cast to current boundaries"
            if entity.slug == "jammu-and-kashmir" and period.end < date(2019, 10, 31):
                note += "; one continuous J&K series, so years before 2019 likely include Ladakh"
            observations.append(
                Observation(
                    indicator_id=series.indicator_id,
                    entity_slug=entity.slug,
                    period=period,
                    value=float(str(raw).replace(",", "")),
                    is_provisional=period.end >= provisional_from,
                    note=note,
                )
            )
    return observations, sorted(set(problems))
