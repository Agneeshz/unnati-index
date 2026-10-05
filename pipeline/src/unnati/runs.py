"""Bookkeeping for ingestion runs: every fetch is recorded, and datasets remember when they were
last checked and last changed. This is what the site's sources page and the freshness monitor
read."""

from __future__ import annotations

import json
import os
from typing import Any

from unnati.db import Connection, scalar

ABANDONED_AFTER = "2 hours"


def start_run(conn: Connection, dataset_id: str, trigger: str = "manual") -> int:
    # A run whose process died (lost connection, killed job) never recorded its outcome.
    conn.run(
        """update ingestion_run set status = 'failed', finished_at = now(),
               error = 'abandoned: the run stopped without recording a result'
           where dataset_id = :dataset and status = 'running'
             and started_at < now() - cast(:after as interval)""",
        dataset=dataset_id,
        after=ABANDONED_AFTER,
    )
    return scalar(
        conn,
        """insert into ingestion_run (dataset_id, trigger, status, git_sha)
           values (:dataset, :trigger, 'running', :git_sha) returning id""",
        dataset=dataset_id,
        trigger=trigger,
        git_sha=os.environ.get("GITHUB_SHA"),
    )


def finish_run(
    conn: Connection,
    run_id: int,
    status: str,
    *,
    rows_loaded: int | None = None,
    fingerprint: str | None = None,
    source_url: str | None = None,
    validation: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    conn.run(
        """update ingestion_run set status = :status, finished_at = now(), rows_loaded = :rows,
               fingerprint = :fingerprint, source_url = :source_url,
               validation = cast(:validation as jsonb), error = :error
           where id = :id""",
        id=run_id,
        status=status,
        rows=rows_loaded,
        fingerprint=fingerprint,
        source_url=source_url,
        validation=None if validation is None else json.dumps(validation, default=str),
        error=error,
    )


def last_fingerprint(conn: Connection, dataset_id: str) -> str | None:
    return scalar(conn, "select last_fingerprint from dataset where id = :id", id=dataset_id)


def mark_checked(conn: Connection, dataset_id: str, fingerprint: str, changed: bool) -> None:
    conn.run(
        """update dataset set last_checked_at = now(), last_fingerprint = :fingerprint,
               last_changed_at = case when :changed then now() else last_changed_at end
           where id = :id""",
        id=dataset_id,
        fingerprint=fingerprint,
        changed=changed,
    )


def record_release(conn: Connection, run_id: int) -> int | None:
    """Write the release event for a loaded run: which indicators and periods got new or revised
    figures. Feeds the site's updates page and RSS. Runs that changed nothing get no event."""
    stats = conn.run(
        """select count(*),
                  count(*) filter (where exists (
                      select 1 from observation p
                      where p.indicator_id = o.indicator_id and p.entity_id = o.entity_id
                        and p.period_start = o.period_start and p.period_end = o.period_end
                        and p.run_id < o.run_id)),
                  array_agg(distinct o.indicator_id order by o.indicator_id)
           from observation o where o.run_id = :run""",
        run=run_id,
    )[0]
    total, revised, indicators = stats
    if not total:
        return None
    periods = [
        row[0]
        for row in conn.run(
            """select period_label from observation where run_id = :run
               group by period_label order by max(period_end) desc limit 6""",
            run=run_id,
        )
    ]
    new = total - revised
    parts = [f"{new:,} new" if new else "", f"{revised:,} revised" if revised else ""]
    noun = "indicator" if len(indicators) == 1 else "indicators"
    summary = f"{' and '.join(p for p in parts if p)} figures across {len(indicators)} {noun}"
    return scalar(
        conn,
        """insert into release_event (dataset_id, run_id, happened_at, title, summary, indicators, periods)
           select r.dataset_id, r.id, coalesce(r.finished_at, now()), d.title, :summary, :indicators, :periods
           from ingestion_run r join dataset d on d.id = r.dataset_id
           where r.id = :run
             and not exists (select 1 from release_event e where e.run_id = r.id)
           returning id""",
        run=run_id,
        summary=summary,
        indicators=indicators,
        periods=periods,
    )


def backfill_releases(conn: Connection) -> int:
    """Release events for loaded runs from before events were recorded."""
    runs = conn.run(
        """select r.id from ingestion_run r
           where r.status = 'loaded'
             and not exists (select 1 from release_event e where e.run_id = r.id)
           order by r.id"""
    )
    return sum(1 for (run_id,) in runs if record_release(conn, run_id) is not None)
