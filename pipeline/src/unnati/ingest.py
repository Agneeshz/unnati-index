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


INGESTERS: dict[str, Callable[[date], Fetched]] = {
    "mospi_nas_state": _mospi_nas_state,
    "mospi_plfs_state": _mospi_plfs_state,
    "mospi_cpi_state": _mospi_cpi_state,
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
