from datetime import date

import pytest

from unnati.connectors import wikidata_officials as wd
from unnati.db import scalar
from unnati.officials import load_wikidata_terms
from unnati.reference import load_reference
from unnati.seed import seed
from unnati.sync_officials import SyncRejected, SyncReport, load

REF = load_reference()
ENTITIES = {e.slug: e.to_entity() for e in REF.entities}
MAPPINGS = wd.load_position_map()
RANKED = [c.id for c in REF.categories if c.ranked]
TODAY = date(2026, 10, 3)


def kerala_terms():
    raw = [
        wd.RawTerm(
            "s1",
            "Q26218416",
            "Q10",
            "First CM",
            "पहले",
            date(2011, 5, 18),
            date(2016, 5, 25),
            (("Q10225", "Indian National Congress"),),
        ),
        wd.RawTerm(
            "s2",
            "Q26218416",
            "Q11",
            "Second CM",
            None,
            date(2016, 5, 25),
            None,
            (("Q1061", "Communist Party of India (Marxist)"),),
        ),
        wd.RawTerm("s3", "Q1748927", "Q12", "A Governor", None, date(2024, 12, 24), None),
    ]
    return wd.build_terms(raw, [], MAPPINGS, ENTITIES, TODAY).terms


def holders(db, start, end):
    kerala = scalar(db, "select id from entity where slug = 'kerala'")
    rows = db.run(
        "select person_name, office_type from office_holders_during(:e, :s, :t)", e=kerala, s=start, t=end
    )
    return sorted((r[0], r[1]) for r in rows)


def test_load_is_idempotent_and_hides_terms_under_review(db):
    seed(db, REF)
    terms = kerala_terms()
    first = load_wikidata_terms(db, terms, MAPPINGS, RANKED, TODAY)
    second = load_wikidata_terms(db, terms, MAPPINGS, RANKED, TODAY)
    assert first == second
    assert first["terms"] == 3 and first["needs_review"] == 1  # the long-running incumbent
    assert scalar(db, "select count(*) from office_term") == 3
    assert scalar(db, "select count(*) from office") == len(
        {(m.entity_slug, m.office_type, m.title) for m in MAPPINGS}
    )
    assert scalar(db, "select name_hi from person where wikidata_qid = 'Q10'") == "पहले"

    assert holders(db, date(2013, 1, 1), date(2013, 12, 31)) == [("First CM", "chief_minister")]
    # The 2016 term has no end date and is held for review, so it is not shown.
    assert holders(db, date(2025, 1, 1), date(2025, 12, 31)) == [("A Governor", "governor")]


def test_cm_answers_for_every_category_and_governor_for_governance(db):
    seed(db, REF)
    load_wikidata_terms(db, kerala_terms(), MAPPINGS, RANKED, TODAY)
    rows = db.run(
        """select o.office_type, count(*) from office o join office_category c on c.office_id = o.id
           join entity e on e.id = o.entity_id where e.slug = 'kerala' group by 1 order by 1"""
    )
    assert dict((r[0], r[1]) for r in rows) == {"chief_minister": len(RANKED), "governor": 1}


def test_statements_removed_upstream_are_removed(db):
    seed(db, REF)
    terms = kerala_terms()
    load_wikidata_terms(db, terms, MAPPINGS, RANKED, TODAY)
    counts = load_wikidata_terms(db, terms[:2], MAPPINGS, RANKED, TODAY)
    assert counts["removed"] == 1
    assert scalar(db, "select count(*) from office_term") == 2


def test_sync_refuses_a_suspiciously_small_result(db):
    seed(db, REF)
    load(db, SyncReport(kerala_terms(), [], []), TODAY)
    with pytest.raises(SyncRejected):
        load(db, SyncReport(kerala_terms()[:1], [], []), TODAY)
    assert scalar(db, "select count(*) from office_term") == 3
    assert scalar(db, "select status from ingestion_run order by id desc limit 1") == "rejected"


def test_abandoned_runs_are_marked_failed(db):
    seed(db, REF)
    db.run(
        """insert into ingestion_run (dataset_id, trigger, status, started_at)
           values ('wikidata_officials', 'schedule', 'running', now() - interval '3 hours')"""
    )
    load(db, SyncReport(kerala_terms(), [], []), TODAY)
    rows = db.run("select status, error from ingestion_run order by id")
    assert rows[0][0] == "failed" and rows[0][1].startswith("abandoned")
    assert rows[1][0] == "loaded"


def test_unchanged_sync_is_recorded_without_reloading(db):
    seed(db, REF)
    report = SyncReport(kerala_terms(), [], [])
    load(db, report, TODAY)
    again = SyncReport(kerala_terms(), [], [])
    load(db, again, TODAY)
    assert again.status == "unchanged"
    statuses = [r[0] for r in db.run("select status from ingestion_run order by id")]
    assert statuses == ["loaded", "unchanged"]
    assert scalar(db, "select last_checked_at is not null from dataset where id = 'wikidata_officials'")
