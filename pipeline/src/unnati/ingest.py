"""Run a dataset's connector end to end: fetch, convert, validate, load, record.

Each ingester returns observations plus non-fatal problems (e.g. an unknown place name) and a
fingerprint of the raw fetch; this module does the rest identically for every source."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from unnati import observations as obs
from unnati.db import Connection
from unnati.reference import load_reference
from unnati.runs import finish_run, last_fingerprint, mark_checked, start_run


@dataclass
class Fetched:
    observations: list[obs.Observation]
    problems: list[str]
    fingerprint: str
    source_url: str


@dataclass
class IngestReport:
    dataset_id: str
    fetched: Fetched
    validation: obs.Validation
    status: str = "dry-run"
    counts: dict[str, int] = field(default_factory=dict)


def fingerprint_of(raw: object) -> str:
    return hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()


def _mospi_nas_state(today: date) -> Fetched:
    from unnati.connectors import mospi

    with mospi.client() as http:
        rows = mospi.fetch_nas_state(http)
    observations, problems = mospi.nas_observations(rows, load_reference().resolver(), today)
    return Fetched(observations, problems, fingerprint_of(rows), f"{mospi.BASE_URL}/api/nas/getNASData")


def _mospi_plfs_state(today: date) -> Fetched:
    from unnati.connectors import mospi

    with mospi.client() as http:
        rows = mospi.fetch_plfs_state(http)
    observations, problems = mospi.plfs_observations(rows, load_reference().resolver())
    return Fetched(observations, problems, fingerprint_of(rows), f"{mospi.BASE_URL}/api/plfs/getData")


def _mospi_cpi_state(today: date) -> Fetched:
    from unnati.connectors import mospi

    with mospi.client() as http:
        rows = mospi.fetch_cpi_state(http)
    observations, problems = mospi.cpi_observations(rows, load_reference().resolver())
    return Fetched(observations, problems, fingerprint_of(rows), f"{mospi.BASE_URL}/api/cpi/getCPIIndex")


def _mospi_nfhs(today: date) -> Fetched:
    from unnati.connectors import mospi

    with mospi.client() as http:
        rows = mospi.fetch_nfhs_state(http)
    observations, problems = mospi.nfhs_observations(rows, load_reference().resolver())
    return Fetched(observations, problems, fingerprint_of(rows), f"{mospi.BASE_URL}/api/nfhs/getNfhsRecords")


def _udise_plus(today: date) -> Fetched:
    from unnati.connectors import mospi

    with mospi.client() as http:
        rows = mospi.fetch_udise_state(http)
    observations, problems = mospi.udise_observations(rows, load_reference().resolver(), today)
    raw = {f"{code}:{filters}": value for (code, filters), value in rows.items()}
    return Fetched(observations, problems, fingerprint_of(raw), f"{mospi.BASE_URL}/api/udise/getUdiseRecords")


def _aishe(today: date) -> Fetched:
    from unnati.connectors import mospi

    with mospi.client() as http:
        rows = mospi.fetch_aishe_ger(http)
    observations, problems = mospi.aishe_observations(rows, load_reference().resolver(), today)
    return Fetched(
        observations, problems, fingerprint_of(rows), f"{mospi.BASE_URL}/api/aishe/getAisheRecords"
    )


def _nfhs_factsheets(today: date) -> Fetched:
    from unnati.connectors import nfhs_factsheets as nf
    from unnati.core.http import PoliteClient

    with PoliteClient(timeout=300) as http:
        pdf, csvs = nf.fetch(http)
    observations, problems = nf.observations(pdf, csvs, load_reference().resolver())
    raw = {"pdf": hashlib.sha256(pdf).hexdigest(), "csvs": csvs}
    return Fetched(observations, problems, fingerprint_of(raw), nf.PDF_URL)


def _ncrb_probe(today: date) -> str:
    from unnati.connectors import ncrb
    from unnati.core.http import PoliteClient

    with PoliteClient() as http:
        return ncrb.fingerprint(ncrb.editions(http, today))


def _ncrb_cii(today: date) -> Fetched:
    from unnati.connectors import ncrb
    from unnati.core.http import PoliteClient

    with PoliteClient(timeout=300) as http:
        found = ncrb.editions(http, today)
        pdfs = ncrb.fetch(http, found)
    observations, problems = ncrb.observations(pdfs, load_reference().resolver())
    latest = found[-1]
    return Fetched(observations, problems, ncrb.fingerprint(found), latest.volumes.get(1, ncrb.CKAN_PACKAGE))


def _ncrb_adsi(today: date) -> Fetched:
    from unnati.connectors import ncrb
    from unnati.core.http import PoliteClient

    with PoliteClient(timeout=120) as http:
        tables = ncrb.adsi_tables(http, today)
        pdfs = {year: http.get(resource["url"]).content for year, resource in tables.items()}
    observations, problems = ncrb.adsi_observations(pdfs, load_reference().resolver())
    raw = {year: hashlib.sha256(pdf).hexdigest() for year, pdf in pdfs.items()}
    return Fetched(observations, problems, fingerprint_of(raw), tables[max(tables)]["url"])


def _morth_road_accidents(today: date) -> Fetched:
    from unnati.connectors import morth
    from unnati.core.http import PoliteClient
    from unnati.reference import population

    with PoliteClient(timeout=120) as http:
        edition, resource = morth.latest(http, today)
        text = http.get(resource["url"]).text
    observations, problems = morth.observations(text, edition, load_reference().resolver(), population())
    return Fetched(observations, problems, fingerprint_of({"edition": edition, "csv": text}), resource["url"])


def _population_projections(today: date) -> Fetched:
    from unnati.connectors import population_projections as pp
    from unnati.core.periods import calendar_year
    from unnati.reference import population

    # Projections run to 2036; only years up to now are loaded, so "latest" means this year.
    rows = {key: value for key, value in population().items() if key[1] <= today.year}
    observations = [
        obs.Observation(
            "population", slug, calendar_year(year), value.persons, note="Projected population as on 1 July"
        )
        for (slug, year), value in sorted(rows.items())
    ]
    raw = {f"{slug}:{year}": value.persons for (slug, year), value in rows.items()}
    return Fetched(observations, [], fingerprint_of(raw), pp.REPORT_URL)  # changes each new year


INGESTERS: dict[str, Callable[[date], Fetched]] = {
    "mospi_nas_state": _mospi_nas_state,
    "mospi_plfs_state": _mospi_plfs_state,
    "mospi_cpi_state": _mospi_cpi_state,
    "mospi_nfhs": _mospi_nfhs,
    "udise_plus": _udise_plus,
    "aishe": _aishe,
    "nfhs": _nfhs_factsheets,  # on demand: a 49 MB one-off release, not on the daily schedule
    "ncrb_cii": _ncrb_cii,
    "ncrb_adsi": _ncrb_adsi,
    "morth_road_accidents": _morth_road_accidents,
    "population_projections": _population_projections,
}

# Cheap change checks for sources that are expensive to download: when the probe's fingerprint
# matches the last load, the run stops before fetching. The ingester must report the same
# fingerprint as its probe.
PROBES: dict[str, Callable[[date], str]] = {
    "ncrb_cii": _ncrb_probe,
}


def check(dataset_id: str, today: date) -> IngestReport:
    """Fetch and validate without touching the database."""
    if dataset_id not in INGESTERS:
        raise KeyError(f"no ingester for {dataset_id!r}; available: {', '.join(sorted(INGESTERS))}")
    fetched = INGESTERS[dataset_id](today)
    ref = load_reference()
    current = [e for e in ref.entities if e.type in ("state", "ut") and e.valid_to is None]
    validation = obs.validate(
        fetched.observations,
        {i.id: i for i in ref.indicators},
        current_places=len(current),
        entity_types={e.slug: e.type for e in ref.entities},
    )
    return IngestReport(dataset_id, fetched, validation)


def run(
    conn: Connection, dataset_id: str, today: date, trigger: str = "manual", force: bool = False
) -> IngestReport:
    run_id = start_run(conn, dataset_id, trigger)
    try:
        if dataset_id in PROBES and not force:
            probed = PROBES[dataset_id](today)
            if probed == last_fingerprint(conn, dataset_id):
                mark_checked(conn, dataset_id, probed, changed=False)
                finish_run(conn, run_id, "unchanged", fingerprint=probed)
                return IngestReport(dataset_id, Fetched([], [], probed, ""), obs.Validation(), "unchanged")
        report = check(dataset_id, today)
        details = {**report.validation.as_dict(), "problems": report.fetched.problems}
        if not report.validation.ok:
            report.status = "rejected"
            finish_run(conn, run_id, "rejected", validation=details, source_url=report.fetched.source_url)
            return report
        fingerprint = report.fetched.fingerprint
        if fingerprint == last_fingerprint(conn, dataset_id) and not force:
            mark_checked(conn, dataset_id, fingerprint, changed=False)
            finish_run(
                conn, run_id, "unchanged", fingerprint=fingerprint, source_url=report.fetched.source_url
            )
            report.status = "unchanged"
            return report
        report.counts = obs.load(conn, report.fetched.observations, run_id)
        mark_checked(conn, dataset_id, fingerprint, changed=True)
        finish_run(
            conn,
            run_id,
            "loaded",
            rows_loaded=report.counts["new"] + report.counts["revised"],
            fingerprint=fingerprint,
            source_url=report.fetched.source_url,
            validation=details,
        )
        report.status = "loaded"
        return report
    except Exception as err:
        finish_run(conn, run_id, "failed", error=str(err))
        raise
