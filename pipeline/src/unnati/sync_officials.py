"""`unnati officials sync`: fetch office-holders from Wikidata, check them, and load them."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from unnati.connectors import wikidata_officials as wd
from unnati.core.http import PoliteClient
from unnati.core.wikidata import SPARQL_ENDPOINT
from unnati.db import Connection, scalar
from unnati.officials import load_wikidata_terms
from unnati.reference import load_reference
from unnati.runs import finish_run, last_fingerprint, mark_checked, start_run

# Refuse to load if a fetch returns far fewer terms than are already loaded: a partial Wikidata
# response must never delete office-holders from the site.
MIN_SHARE_OF_PREVIOUS = 0.8


class SyncRejected(RuntimeError):
    pass


@dataclass
class SyncReport:
    terms: list[wd.Term]
    problems: list[str]
    unused_overrides: list[str]
    status: str = "dry-run"
    counts: dict[str, int] | None = None

    @property
    def flagged(self) -> list[wd.Term]:
        return [t for t in self.terms if t.needs_review]


def build(http: PoliteClient, today: date) -> SyncReport:
    ref = load_reference()
    entities = {e.slug: e.to_entity() for e in ref.entities}
    mappings = wd.load_position_map()
    raw_terms, memberships = wd.fetch(http, mappings)
    result = wd.build_terms(raw_terms, memberships, mappings, entities, today)
    unused = wd.apply_overrides(result.terms, wd.load_overrides())
    return SyncReport(result.terms, result.problems, unused)


def load(
    conn: Connection, report: SyncReport, today: date, trigger: str = "manual", force: bool = False
) -> None:
    ref = load_reference()
    mappings = wd.load_position_map()
    run_id = start_run(conn, wd.DATASET_ID, trigger)
    try:
        previous = scalar(conn, "select count(*) from office_term where source_type = 'wikidata'")
        if not report.terms or (
            previous and len(report.terms) < MIN_SHARE_OF_PREVIOUS * previous and not force
        ):
            raise SyncRejected(
                f"fetched {len(report.terms)} terms but {previous} are loaded; refusing to load "
                "a possibly partial result (re-run with --force if this is expected)"
            )
        fingerprint = wd.fingerprint(report.terms)
        if fingerprint == last_fingerprint(conn, wd.DATASET_ID) and not force:
            mark_checked(conn, wd.DATASET_ID, fingerprint, changed=False)
            finish_run(conn, run_id, "unchanged", fingerprint=fingerprint)
            report.status = "unchanged"
            return
        ranked = [c.id for c in ref.categories if c.ranked]
        report.counts = load_wikidata_terms(conn, report.terms, mappings, ranked, today)
        mark_checked(conn, wd.DATASET_ID, fingerprint, changed=True)
        finish_run(
            conn,
            run_id,
            "loaded",
            rows_loaded=len(report.terms),
            fingerprint=fingerprint,
            source_url=SPARQL_ENDPOINT,
            validation={
                "flagged": [{"id": t.external_id, "notes": t.notes} for t in report.flagged],
                "problems": report.problems,
                "unused_overrides": report.unused_overrides,
            },
        )
        report.status = "loaded"
    except Exception as err:
        status = "rejected" if isinstance(err, SyncRejected) else "failed"
        finish_run(conn, run_id, status, error=str(err))
        raise
