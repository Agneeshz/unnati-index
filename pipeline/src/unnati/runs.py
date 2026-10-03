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
