from datetime import date

from unnati.db import scalar
from unnati.reference import load_reference
from unnati.seed import seed


def test_seed_loads_reference_data(db):
    counts = seed(db, load_reference())
    assert scalar(db, "select count(*) from entity") == counts["entities"]
    assert scalar(db, "select count(*) from entity where type in ('state','ut') and valid_to is null") == 36
    assert scalar(db, "select count(*) from entity where parent_id is null") == 1
    assert scalar(db, "select count(*) from indicator") == counts["indicators"]
    assert scalar(db, "select count(*) from entity_lineage") == counts["lineage"]
    enabled = sum(d.enabled for d in load_reference().registry.datasets)
    assert scalar(db, "select count(*) from dataset where status = 'active'") == enabled
    assert scalar(db, "select count(*) from dataset where status = 'paused'") == counts["datasets"] - enabled


def test_seed_is_idempotent(db):
    ref = load_reference()
    first = seed(db, ref)
    second = seed(db, ref)
    assert first == second
    assert scalar(db, "select count(*) from entity") == first["entities"]
    assert scalar(db, "select count(*) from entity_alias") == first["aliases"]


def test_reseeding_keeps_broken_status_of_enabled_datasets(db):
    ref = load_reference()
    datasets = [d.model_copy(update={"enabled": d.id == "ncrb_cii"}) for d in ref.registry.datasets]
    ref = ref.model_copy(update={"registry": ref.registry.model_copy(update={"datasets": datasets})})
    status = "select status from dataset where id = 'ncrb_cii'"

    seed(db, ref)
    assert scalar(db, status) == "active"
    db.run("update dataset set status = 'broken' where id = 'ncrb_cii'")
    seed(db, ref)
    assert scalar(db, status) == "broken"


def test_office_holders_are_matched_to_the_data_period(db):
    seed(db, load_reference())
    kerala = scalar(db, "select id from entity where slug = 'kerala'")
    office = scalar(
        db,
        """insert into office (entity_id, office_type, title, is_political)
           values (:entity, 'chief_minister', 'Chief Minister of Kerala', true) returning id""",
        entity=kerala,
    )
    for name, start, end in [
        ("Person A", date(2016, 5, 25), date(2021, 5, 19)),
        ("Person B", date(2021, 5, 20), None),
    ]:
        person = scalar(db, "insert into person (name) values (:name) returning id", name=name)
        db.run(
            """insert into office_term (office_id, person_id, start_date, end_date, source_type,
                                        source_url, verified_at)
               values (:office, :person, :start, :end, 'curated', 'https://example.org', :verified)""",
            office=office,
            person=person,
            start=start,
            end=end,
            verified=date(2026, 10, 3),
        )

    def holders(start, end):
        rows = db.run(
            "select person_name from office_holders_during(:entity, :start, :end)",
            entity=kerala,
            start=start,
            end=end,
        )
        return [r[0] for r in rows]

    assert holders(date(2019, 1, 1), date(2019, 12, 31)) == ["Person A"]
    assert holders(date(2021, 1, 1), date(2021, 12, 31)) == ["Person A", "Person B"]
    assert holders(date(2024, 1, 1), date(2024, 12, 31)) == ["Person B"]
