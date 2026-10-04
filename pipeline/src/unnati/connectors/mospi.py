"""MoSPI's open API (api.mospi.gov.in), the data behind the eSankhyiki portal.

Endpoints and parameters follow MoSPI's own published Swagger specs
(github.com/nso-india/esankhyiki-mcp). The server still needs TLS legacy renegotiation, so this
connector relaxes exactly that, keeping certificate and hostname checks (see core.http).

Responses are paged (at most 200 rows per page)."""

from __future__ import annotations

import calendar
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise

from unnati.core.entities import EntityResolver, UnknownEntityError, normalize_name
from unnati.core.http import PoliteClient, legacy_renegotiation_context
from unnati.core.periods import Period, calendar_year, day, fiscal_year, month, parse_period, span
from unnati.observations import Observation

BASE_URL = "https://api.mospi.gov.in"
PAGE_SIZE = 200


def number(raw: object) -> float | None:
    """Source values like "12.5", "1,234", "(27.4)"; "*", "NA", "-" and blanks mean no value."""
    text = str(raw).replace(",", "").strip().strip("()") if raw is not None else ""
    try:
        return float(text)
    except ValueError:
        return None


def resolve_current_first(resolver: EntityResolver, name: str, period: Period, today: date):
    """For sources that report earlier years on today's boundaries where possible but still
    use names of entities that no longer exist (e.g. Daman & Diu before 2020): try today's
    boundaries first, then the boundaries of the data period. Raises UnknownEntityError."""
    try:
        return resolver.resolve(name, day(today))
    except UnknownEntityError:
        return resolver.resolve(name, period)


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


def fetch_plfs_status(http: PoliteClient) -> list[dict]:
    """Distribution of workers by broad status in employment (PLFS indicator 4, annual)."""
    return fetch_all(
        http,
        "/api/plfs/getData",
        {
            "indicator_code": 4,
            "frequency_code": 1,
            "broad_status_employment_code": "1,2,3,4,5,6",
            "Format": "JSON",
        },
    )


def plfs_status_observations(
    rows: list[dict], resolver: EntityResolver
) -> tuple[list[Observation], list[str]]:
    """regular-wage-share: share of workers (usual status, all persons, rural + urban) in regular
    wage/salaried jobs. A place's shares of self-employed, regular and casual workers must add
    up to about 100, or its row is skipped (MoSPI's All-India rows currently do not)."""
    groups: dict[tuple[str, str], dict[str, float]] = {}
    for row in rows:
        if (row.get("gender"), row.get("sector"), row.get("weekly_status")) != (
            "person",
            "rural + urban",
            "PS+SS",
        ):
            continue
        value = number(row.get("value"))
        if value is not None:
            groups.setdefault((row["state"], row["year"]), {})[
                str(row.get("broad_status_employment"))[:1]
            ] = value
    out: list[Observation] = []
    problems: list[str] = []
    for (state, year), parts in groups.items():
        regular = parts.get("4")
        if regular is None:
            continue
        total = parts.get("3", 0) + regular + parts.get("5", 0)
        if abs(total - 100) > 2:
            problems.append(f"PLFS status shares for {state} {year} add up to {total:g}, not 100; skipped")
            continue
        period = calendar_year(int(year))
        try:
            entity = resolver.resolve(state, period)
        except UnknownEntityError as err:
            problems.append(str(err))
            continue
        if entity is None:
            continue
        note = "PLFS, usual status (PS+SS), rural + urban"
        out.append(Observation("regular-wage-share", entity.slug, period, regular, note=note))
    return out, sorted(set(problems))


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


# --- National Family Health Survey (NFHS-4, NFHS-5) ------------------------------------------
#
# NFHS-6 (2023-24) is not in the API yet. Labels carry footnote numbers ("stunted
# (height-for-age)18 (%)"); they are stripped before matching this explicit table.

NFHS_ROUNDS = {
    "nfhs-4": span(date(2015, 1, 20), date(2016, 12, 4), "NFHS-4 (2015-16)", "survey_round"),
    "nfhs-5": span(date(2019, 6, 17), date(2021, 4, 30), "NFHS-5 (2019-21)", "survey_round"),
}
NFHS_INDICATORS = {
    "Households using clean fuel for cooking (%)": "clean-cooking-fuel",
    "Population living in households that use an improved sanitation facility (%)": "improved-sanitation",
    "Population living in households with electricity (%)": "households-with-electricity",
    "Women age 20-24 years married before age 18 years (%)": "child-marriage",
    "Sex ratio at birth for children born in the last five years (females per 1,000 males)": (
        "sex-ratio-at-birth-nfhs"
    ),
    "Institutional births (in the 5 years before the survey) (%)": "institutional-births",
    "Children age 12-23 months fully vaccinated based on information from either vaccination card"
    " or mother's recall (%)": "full-immunisation",
    # NFHS-4 wording for the same basic schedule (BCG, measles, 3 doses each of polio and DPT)
    "Children age 12-23 months fully immunized (BCG; measles; and 3 doses each of polio and DPT) (%)": (
        "full-immunisation"
    ),
    "Children under 5 years who are stunted (height-for-age) (%)": "stunting-under5",
    "All women age 15-49 years who are anaemic (%)": "anaemia-women",
    "Children age 6-59 months who are anaemic (<11.0 g/dl) (%)": "anaemia-children",
    "Women (age 15-49 years) having a bank or savings account that they themselves use (%)": (
        "women-bank-account"
    ),
}
NFHS_SECTIONS = (1, 3, 9, 10, 12, 14, 19)
_FOOTNOTE = re.compile(r"(?<=[^\d\s])\d+(?:,\s*\d+)*(?=\s*\(%\)$)")


def nfhs_label(raw: str) -> str:
    """'...stunted (height-for-age)18 (%)' -> '...stunted (height-for-age) (%)'."""
    return re.sub(r"\s+", " ", _FOOTNOTE.sub(" ", raw)).replace(" ) (%)", ") (%)").strip()


def fetch_nfhs_state(http: PoliteClient) -> list[dict]:
    rows: list[dict] = []
    for code in NFHS_SECTIONS:
        rows += fetch_all(http, "/api/nfhs/getNfhsRecords", {"indicator_code": code, "Format": "JSON"})
    return rows


def nfhs_observations(rows: list[dict], resolver: EntityResolver) -> tuple[list[Observation], list[str]]:
    observations: list[Observation] = []
    problems: list[str] = []
    for row in rows:
        indicator_id = NFHS_INDICATORS.get(nfhs_label(row["sub_indicator"]))
        period = NFHS_ROUNDS.get(row.get("survey", "").lower())
        if not indicator_id or period is None or row.get("sector") != "Rural + Urban (Combined)":
            continue
        if row.get("value") in (None, "", "NA", "-", "*"):
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
                indicator_id=indicator_id,
                entity_slug=entity.slug,
                period=period,
                value=float(str(row["value"]).strip("()")),
                note=f"{period.label}; values in brackets in the source rest on few cases",
            )
        )
    return observations, sorted(set(problems))


# --- UDISE+: school education (academic years from 2018-19) ----------------------------------


@dataclass(frozen=True)
class UdiseSeries:
    indicator_code: int
    server: tuple[tuple[str, object], ...]  # filters sent to the API
    row: tuple[tuple[str, str], ...]  # what each accepted row must say
    indicator_id: str


UDISE_SERIES = (
    UdiseSeries(
        31,
        (("gender_code", 3),),
        (("gender", "Total"), ("level_of_education", "Secondary (9-10)"), ("social_group", "All")),
        "ger-secondary",
    ),
    UdiseSeries(
        41,
        (("gender_code", 3),),
        (("gender", "Total"), ("level_of_education", "Secondary (9-10)")),
        "dropout-secondary",
    ),
    UdiseSeries(23, (), (("level_of_education", "Secondary"),), "ptr-secondary"),
    UdiseSeries(
        48,
        (("type_of_management_code", 1),),
        (
            ("type_of_management", "All Management"),
            ("sub_indicator", "Percentage of Schools with functional Desktop/PCs availability"),
        ),
        "schools-with-computers",
    ),
    UdiseSeries(
        47,
        (("type_of_management_code", 1),),
        (
            ("type_of_management", "All Management"),
            ("sub_indicator", "Percentage of schools having functional electricity"),
        ),
        "schools-with-electricity",
    ),
    UdiseSeries(
        47,
        (("type_of_management_code", 1),),
        (
            ("type_of_management", "All Management"),
            ("sub_indicator", "Percentage of schools having functional girls toilets"),
        ),
        "schools-with-girls-toilets",
    ),
)


def fetch_udise_state(http: PoliteClient) -> dict[tuple[int, tuple], list[dict]]:
    found: dict[tuple[int, tuple], list[dict]] = {}
    for series in UDISE_SERIES:
        key = (series.indicator_code, series.server)
        if key not in found:
            found[key] = fetch_all(
                http,
                "/api/udise/getUdiseRecords",
                {"indicator_code": series.indicator_code, **dict(series.server), "Format": "JSON"},
            )
    return found


# HCES survey years run August to July ("2023-24" = Aug 2023 - Jul 2024).
HCES_GINI = {"Rural": "consumption-gini-rural", "Urban": "consumption-gini-urban"}


def fetch_hces_gini(http: PoliteClient) -> list[dict]:
    return fetch_all(http, "/api/hces/getHcesRecords", {"indicator_code": 9, "Format": "JSON"})


def hces_observations(rows: list[dict], resolver: EntityResolver) -> tuple[list[Observation], list[str]]:
    """Rural and urban Gini (MoSPI's headline series, without imputed free items), plus their
    unweighted mean as consumption-gini."""
    observations: list[Observation] = []
    problems: list[str] = []
    found: dict[tuple[str, str], dict[str, float]] = {}
    periods: dict[str, Period] = {}
    for row in rows:
        indicator_id = HCES_GINI.get(row.get("sector", ""))
        value = number(row.get("value"))
        if indicator_id is None or value is None or row.get("imputation_type") != "Without Imputation":
            continue
        first = int(row["year"][:4])
        period = periods.setdefault(
            row["year"],
            span(date(first, 8, 1), date(first + 1, 7, 31), f"HCES {row['year']}", "survey_round"),
        )
        try:
            entity = resolver.resolve(row["state"], period)
        except UnknownEntityError as err:
            problems.append(str(err))
            continue
        if entity is None:
            continue
        note = "HCES, without imputed values of free items"
        observations.append(Observation(indicator_id, entity.slug, period, value, note=note))
        found.setdefault((entity.slug, row["year"]), {})[indicator_id] = value
    for (slug, year), values in found.items():
        if len(values) == 2:
            observations.append(
                Observation(
                    "consumption-gini",
                    slug,
                    periods[year],
                    round(sum(values.values()) / 2, 4),
                    note="Mean of the rural and urban Gini (HCES, without imputed values of free items)",
                )
            )
    return observations, sorted(set(problems))


# EnviStats (MoSPI "Compendium of Environment Statistics"), /api/env/getEnvStatsRecords.
ENV_AIR = 25  # Ambient Air Quality in cities under NAMP & CAAQMS (Integrated)
ENV_WASTE = 80  # Municipal Solid Waste Generation in India (state-wise, TPD)
ENV_VEHICLES = 112  # Status of registered Motor Vehicles (state-wise, transport / non-transport)

# MoSPI's API labels table 25's pollutant columns with fertiliser names. Checked against table 26
# (correctly labelled, 7 metros): the CAAQMS values match SO2, NO2 and PM10 exactly, so the
# columns are CPCB's usual order and the one labelled "SO2" is PM2.5.
ENV_AIR_COLUMNS = {"Nitrogen": "SO2", "Phosphorous": "NO2", "Potash (Potassium)": "PM10", "SO2": "PM2.5"}


# EnviStats still lists DNH and Daman & Diu separately after their 26 Jan 2020 merger; here (and
# only here, since other sources must fail loudly on stale names) their rows are added together.
ENV_COMBINED_NAME = normalize_name("Daman and Diu and Dadra Nagar Haveli")
ENV_MERGED_NAMES = {
    normalize_name("Dadra and Nagar Haveli"), normalize_name("Daman and Diu"),
    ENV_COMBINED_NAME,
}
ENV_MERGED_FROM = date(2020, 1, 26)
ENV_MERGED_SLUG = "dadra-and-nagar-haveli-and-daman-and-diu"


def fetch_envstats(http: PoliteClient) -> dict[int, list[dict]]:
    return {
        code: fetch_all(http, "/api/env/getEnvStatsRecords", {"indicator_code": code, "Format": "JSON"})
        for code in (ENV_AIR, ENV_WASTE, ENV_VEHICLES)
    }


def envstats_observations(
    rows_by_code: Mapping[int, list[dict]], resolver: EntityResolver, population=None
) -> tuple[list[Observation], list[str]]:
    """pm25-annual: per city, the continuous monitors' (CAAQMS) annual PM2.5 where the city has
    them, else the manual (NAMP) stations'; a state's value is the mean over its monitored
    cities. waste-processed: municipal solid waste treated / generated (tonnes per day).
    Rows are grouped by resolved place, so the pre-2020 names of DNH and Daman & Diu, which
    the source still uses, add up into the merged UT."""
    out: list[Observation] = []
    problems: list[str] = []
    resolved: dict[tuple[str, Period], str | None] = {}

    def slug_of(state: str, period: Period) -> str | None:
        if (state, period) not in resolved:
            try:
                entity = resolver.resolve(state, period)
                resolved[(state, period)] = entity.slug if entity else None
            except UnknownEntityError as err:
                if normalize_name(state) in ENV_MERGED_NAMES and period.end >= ENV_MERGED_FROM:
                    resolved[(state, period)] = ENV_MERGED_SLUG
                elif normalize_name(state) == ENV_COMBINED_NAME:
                    # The vehicle table back-fills the merged name for years before the merger,
                    # when no single place (or population) matches it: skip those years.
                    resolved[(state, period)] = None
                else:
                    problems.append(str(err))
                    resolved[(state, period)] = None
        return resolved[(state, period)]

    labels = {r.get("emission_source") for r in rows_by_code.get(ENV_AIR, [])}
    if labels and labels != set(ENV_AIR_COLUMNS):
        problems.append(f"EnviStats air table: unexpected column labels {sorted(labels)}; not read")
    else:
        cities: dict[tuple[Period, str, str], dict[str, float]] = {}
        for row in rows_by_code.get(ENV_AIR, []):
            value = number(row.get("value"))
            if value is None or ENV_AIR_COLUMNS[row["emission_source"]] != "PM2.5":
                continue
            period = calendar_year(int(row["year"]))
            slug = slug_of(row["state"], period)
            if slug is None:
                continue
            network = "CAAQMS" if row["sub_indicator"].startswith("CAAQMS") else "NAMP"
            cities.setdefault((period, slug, row["cities"]), {})[network] = value
        by_place: dict[tuple[Period, str], list[float]] = {}
        for (period, slug, _), networks in cities.items():
            by_place.setdefault((period, slug), []).append(networks.get("CAAQMS", networks.get("NAMP")))
        for (period, slug), values in by_place.items():
            note = (
                f"EnviStats (CPCB NAMP/CAAQMS): mean of {len(values)} monitored "
                f"cit{'y' if len(values) == 1 else 'ies'}; MoSPI's API mislabels this column"
            )
            out.append(
                Observation("pm25-annual", slug, period, round(sum(values) / len(values), 1), note=note)
            )

    waste: dict[tuple[Period, str], dict[str, float]] = {}
    for row in rows_by_code.get(ENV_WASTE, []):
        value = number(row.get("value"))
        if value is None:
            continue
        period = fiscal_year(int(row["year"][:4]))
        slug = slug_of(row["state"], period)
        if slug is None:
            continue
        parts = waste.setdefault((period, slug), {})
        parts[row["sub_indicator"]] = parts.get(row["sub_indicator"], 0.0) + value
    for (period, slug), parts in waste.items():
        generated, treated = parts.get("Quantity Generated (TPD)"), parts.get("Treated (TPD)")
        if not generated or treated is None:
            continue
        note = f"EnviStats (CPCB): {treated:,.0f} of {generated:,.0f} tonnes a day treated"
        out.append(
            Observation(
                "waste-processed", slug, period, round(min(treated / generated, 1) * 100, 1), note=note
            )
        )
    vehicles: dict[tuple[Period, str], float] = {}
    for row in rows_by_code.get(ENV_VEHICLES, []):
        value = number(row.get("value"))
        year = re.match(r"\d{4}", str(row.get("year", "")))
        if value is None or not year:
            continue
        period = calendar_year(int(year.group(0)))
        slug = slug_of(row["state"], period)
        if slug is not None:
            vehicles[(period, slug)] = vehicles.get((period, slug), 0.0) + value
    for (period, slug), count in vehicles.items():
        people = population.get((slug, period.start.year)) if population else None
        if people is None:
            continue
        note = f"EnviStats (MoRTH): {count:,.0f} registered motor vehicles"
        value = round(count / people.persons * 1000)
        out.append(Observation("vehicles-per-1000", slug, period, value, note=note))
    return out, sorted(set(problems))


def udise_observations(
    rows_by_query: Mapping[tuple[int, tuple], list[dict]], resolver: EntityResolver, today: date
) -> tuple[list[Observation], list[str]]:
    """UDISE+ academic years ("2024-25") are dated April-March. UDISE+ is a hybrid: earlier years
    use current boundaries where they can (Ladakh is listed separately from 2018-19, so its J&K
    is always the UT), but the pre-2020 UTs Dadra & Nagar Haveli and Daman & Diu still appear
    under their own names. So names resolve on current boundaries first, then as of the year."""
    observations: list[Observation] = []
    problems: list[str] = []
    for series in UDISE_SERIES:
        for row in rows_by_query.get((series.indicator_code, series.server), []):
            if any(row.get(k) != v for k, v in series.row):
                continue
            value = number(row.get("value"))
            if value is None:
                continue
            if series.indicator_id == "dropout-secondary" and value == 0:
                # UDISE+ floors its flow-based dropout formula at 0 when enrolment data are
                # inconsistent (e.g. Bihar 2023-24 and 2024-25), so 0 is not a measurement.
                problems.append(f"UDISE+ dropout of 0 for {row['state']} {row['year']} skipped as unreliable")
                continue
            period = parse_period(row["year"])
            try:
                entity = resolve_current_first(resolver, row["state"], period, today)
            except UnknownEntityError as err:
                problems.append(str(err))
                continue
            if entity is None:
                continue
            observations.append(
                Observation(
                    series.indicator_id, entity.slug, period, value, note="UDISE+, current boundaries"
                )
            )
    return observations, sorted(set(problems))


# --- AISHE: higher education (academic years 2017-18 to 2021-22) ------------------------------


def fetch_aishe_ger(http: PoliteClient) -> list[dict]:
    return fetch_all(http, "/api/aishe/getAisheRecords", {"indicator_code": 6, "Format": "JSON"})


def aishe_observations(
    rows: list[dict], resolver: EntityResolver, today: date
) -> tuple[list[Observation], list[str]]:
    """Gross enrolment ratio in higher education (age 18-23), all categories, both sexes."""
    observations: list[Observation] = []
    problems: list[str] = []
    for row in rows:
        if row.get("social_category") != "All Categories" or row.get("gender") != "Both":
            continue
        value = number(row.get("value"))
        if value is None:
            continue
        period = parse_period(row["year"])
        try:
            entity = resolve_current_first(resolver, row["state"], period, today)
        except UnknownEntityError as err:
            problems.append(str(err))
            continue
        if entity is None:
            continue
        observations.append(Observation("ger-higher-education", entity.slug, period, value, note="AISHE"))
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
    observations += three_year_growth(observations)
    return observations, sorted(set(problems))


def three_year_growth(observations: list[Observation]) -> list[Observation]:
    """gsdp-growth-real-3yr: the mean of real GSDP growth over three consecutive fiscal years,
    one value per window. Provisional if any of the three years is."""
    by_entity: dict[str, list[Observation]] = {}
    for o in observations:
        if o.indicator_id == "gsdp-growth-real":
            by_entity.setdefault(o.entity_slug, []).append(o)
    out = []
    for slug, series in by_entity.items():
        series.sort(key=lambda o: o.period.start)
        for window in zip(series, series[1:], series[2:], strict=False):
            if any(b.period.start != a.period.end + timedelta(days=1) for a, b in pairwise(window)):
                continue  # a missing year
            first, last = window[0].period, window[-1].period
            out.append(
                Observation(
                    "gsdp-growth-real-3yr",
                    slug,
                    span(first.start, last.end, f"{first.label} to {last.label}"),
                    round(sum(o.value for o in window) / 3, 2),
                    is_provisional=any(o.is_provisional for o in window),
                    note=f"Mean of real GSDP growth in {', '.join(o.period.label for o in window)}",
                )
            )
    return out
