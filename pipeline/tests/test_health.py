from datetime import UTC, datetime, timedelta

from unnati import health
from unnati.reference import load_reference
from unnati.seed import seed

NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)


def _run(db, dataset, status, started, error=None, validation=None):
    db.run(
        """insert into ingestion_run (dataset_id, trigger, status, started_at, finished_at, error, validation)
           values (:d, 'schedule', :s, :t, :t, :e, cast(:v as jsonb))""",
        d=dataset,
        s=status,
        t=started,
        e=error,
        v=validation,
    )


def _changed(db, dataset, when):
    db.run("update dataset set last_changed_at = :w where id = :d", w=when, d=dataset)


def test_failing_stale_and_abandoned_sources_are_reported(db):
    seed(db, load_reference())
    # Healthy: loaded yesterday.
    _changed(db, "cpcb_aqi_bulletin", NOW - timedelta(days=1))
    _run(db, "cpcb_aqi_bulletin", "loaded", NOW - timedelta(days=1))
    # Failing for three days, after an earlier success.
    _changed(db, "bprd_dopo", NOW - timedelta(days=10))
    _run(db, "bprd_dopo", "unchanged", NOW - timedelta(days=4))
    for days in (3, 2, 1):
        _run(db, "bprd_dopo", "failed", NOW - timedelta(days=days), error="ConnectTimeout: timed out")
    # Died mid-run (still "running" after five hours).
    _changed(db, "rbi_hsis", NOW - timedelta(days=5))
    _run(db, "rbi_hsis", "running", NOW - timedelta(hours=5))
    # Rejected by validation.
    _changed(db, "aai_traffic", NOW - timedelta(days=5))
    _run(db, "aai_traffic", "rejected", NOW - timedelta(hours=3), validation='{"hard": ["unknown place"]}')
    # A monthly source quiet for 60 days (alert after 45).
    _changed(db, "gstn_state_collections", NOW - timedelta(days=60))
    _run(db, "gstn_state_collections", "unchanged", NOW - timedelta(days=1))
    # An irregular source is never stale.
    _changed(db, "parakh", NOW - timedelta(days=900))
    _run(db, "parakh", "unchanged", NOW - timedelta(days=1))

    ids = ["cpcb_aqi_bulletin", "bprd_dopo", "rbi_hsis", "aai_traffic", "gstn_state_collections", "parakh"]
    found = {p.dataset: p for p in health.problems(db, ids, NOW)}
    assert set(found) == {"bprd_dopo", "rbi_hsis", "aai_traffic", "gstn_state_collections"}
    assert found["bprd_dopo"].kind == "failing"
    assert found["bprd_dopo"].since == (NOW - timedelta(days=3)).date().isoformat()  # first of the streak
    assert "ConnectTimeout" in found["bprd_dopo"].detail
    assert "without recording a result" in found["rbi_hsis"].detail
    assert found["aai_traffic"].detail == "Rejected by validation: unknown place"
    assert found["gstn_state_collections"].kind == "stale"
    assert "after 45 days" in found["gstn_state_collections"].detail


def test_issues_are_opened_updated_and_closed(monkeypatch):
    calls = []

    def fake_gh(*args):
        calls.append(args)
        if args[:2] == ("issue", "list"):
            return (
                '[{"number": 1, "title": "Data source failing: bprd_dopo"},'
                ' {"number": 2, "title": "Data source stale: aai_traffic"},'
                ' {"number": 3, "title": "Scoring failed"}]'
            )
        return ""

    monkeypatch.setattr(health, "_gh", fake_gh)
    found = [health.Problem("gstn_state_collections", "GST", "stale", "2026-08-11", "quiet")]
    actions = health.sync_issues(found, ["bprd_dopo", "aai_traffic", "gstn_state_collections"], "run")
    assert actions == [
        "opened Data source stale: gstn_state_collections",
        "closed #1 Data source failing: bprd_dopo",
        "closed #2 Data source stale: aai_traffic",
    ]  # "Scoring failed" is not a dataset issue, so it is left alone
