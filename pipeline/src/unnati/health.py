"""Source health: which datasets are failing or have gone quiet, for alerts and the sources page.

- failing: the latest run failed or was rejected (or never finished: a run still "running" after
  ABANDONED_AFTER died without recording a result). Reported with the error and since when.
- stale: no new data for 1.5x the dataset's normal release interval (an annual source quiet for
  18 months, a monthly one for 45 days). Sources can stop publishing without erroring.

Only datasets that the daily ingest runs (`ingest.INGESTERS`) are checked; office-holders have
their own weekly job. The daily workflow calls `unnati health --issues` after scoring: it opens
or updates one GitHub issue per problem and closes those whose source has recovered."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from unnati.db import Connection

# Typical days between releases; None = no regular schedule (never "stale").
CADENCE_DAYS = {
    "hourly": 1,
    "daily": 2,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 92,
    "annual": 365,
    "biennial": 730,
    "irregular": None,
}
STALE_FACTOR = 1.5
ABANDONED_AFTER = timedelta(hours=2)
LABEL = "data-source"
TITLES = {"failing": "Data source failing: {id}", "stale": "Data source stale: {id}"}


@dataclass(frozen=True)
class Problem:
    dataset: str
    title: str
    kind: str  # failing | stale
    since: str  # ISO date
    detail: str


def problems(conn: Connection, dataset_ids: list[str], now: datetime | None = None) -> list[Problem]:
    now = now or datetime.now(UTC)
    rows = conn.run(
        """select d.id, d.title, d.cadence, d.last_changed_at,
                  r.status, r.started_at, r.error, r.validation::text,
                  (select min(f.started_at) from ingestion_run f
                   where f.dataset_id = d.id and f.status in ('failed', 'rejected', 'running')
                     and f.id > coalesce((select max(ok.id) from ingestion_run ok
                                          where ok.dataset_id = d.id
                                            and ok.status in ('loaded', 'unchanged')), 0))
           from dataset d
           left join lateral (select * from ingestion_run x where x.dataset_id = d.id
                              order by x.id desc limit 1) r on true
           where d.status <> 'paused' and d.id = any(cast(:ids as text[]))
           order by d.id""",
        ids=dataset_ids,
    )
    out: list[Problem] = []
    for dataset, title, cadence, changed, status, started, error, validation, first_failure in rows:
        abandoned = status == "running" and started and now - started > ABANDONED_AFTER
        if status in ("failed", "rejected") or abandoned:
            if status == "rejected":
                hard = json.loads(validation or "{}").get("hard", [])
                detail = "Rejected by validation: " + "; ".join(hard[:5])
            elif abandoned:
                detail = "The run stopped without recording a result (killed or lost its connection)."
            else:
                detail = error or "Failed without an error message."
            since = (first_failure or started).date().isoformat()
            out.append(Problem(dataset, title, "failing", since, detail))
            continue
        days = CADENCE_DAYS.get(cadence)
        if days is None:
            continue
        limit = timedelta(days=days * STALE_FACTOR)
        if changed is None:
            out.append(Problem(dataset, title, "stale", "", "No data has been loaded from this source yet."))
        elif now - changed > limit:
            detail = (
                f"No new data since {changed.date().isoformat()}; it usually releases {cadence} "
                f"(alert after {limit.days} days). Check the source for a new release or a moved file."
            )
            out.append(Problem(dataset, title, "stale", changed.date().isoformat(), detail))
    return out


def as_json(found: list[Problem]) -> str:
    return json.dumps([asdict(p) for p in found], indent=2)


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def sync_issues(found: list[Problem], dataset_ids: list[str], run_url: str) -> list[str]:
    """Open or update one issue per problem; close the managed issues that no longer apply.
    Only titles in TITLES for known datasets are managed, so other data-source issues are left alone."""
    actions: list[str] = []
    listed = _gh("issue", "list", "--state", "open", "--label", LABEL, "--json", "number,title")
    open_issues = json.loads(listed)
    by_title = {i["title"]: i["number"] for i in open_issues}
    wanted = {TITLES[p.kind].format(id=p.dataset): p for p in found}
    for title, p in wanted.items():
        body = (
            f"**{p.title}** (`{p.dataset}`) is {p.kind}"
            + (f" since {p.since}" if p.since else "")
            + f".\n\n{p.detail}\n\nLatest check: {run_url}\n\n"
            "This issue closes itself when the source recovers."
        )
        if title in by_title:
            comment = f"Still {p.kind}: {p.detail}\n\n{run_url}"
            _gh("issue", "comment", str(by_title[title]), "--body", comment)
            actions.append(f"updated #{by_title[title]} {title}")
        else:
            _gh("issue", "create", "--title", title, "--label", LABEL, "--body", body)
            actions.append(f"opened {title}")
    managed = {TITLES[k].format(id=d) for k in TITLES for d in dataset_ids}
    for title, number in by_title.items():
        if title in managed and title not in wanted:
            comment = f"Recovered: the source is healthy again.\n\n{run_url}"
            _gh("issue", "close", str(number), "--comment", comment)
            actions.append(f"closed #{number} {title}")
    return actions
