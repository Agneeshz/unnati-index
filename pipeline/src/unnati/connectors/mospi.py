"""MoSPI's open API (api.mospi.gov.in), the data behind the eSankhyiki portal.

Endpoints and parameters follow MoSPI's own published Swagger specs
(github.com/nso-india/esankhyiki-mcp). The server still needs TLS legacy renegotiation, so this
connector relaxes exactly that, keeping certificate and hostname checks (see core.http).

Responses are paged (at most 200 rows per page)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from unnati.core.entities import EntityResolver, UnknownEntityError
from unnati.core.http import PoliteClient, legacy_renegotiation_context
from unnati.core.periods import day, parse_period
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
