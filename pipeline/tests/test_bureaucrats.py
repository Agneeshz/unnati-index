from datetime import date, timedelta

import pytest

from unnati.connectors import wikipedia_bureaucrats as wb
from unnati.db import scalar
from unnati.officials import load_observed_terms
from unnati.reference import load_reference
from unnati.seed import seed

REF = load_reference()
NAMES = {e.slug: e.name for e in REF.entities}
RANKED = [c.id for c in REF.categories if c.ranked]

STATES_TABLE = """
{| class="wikitable sortable mw-collapsible"
|+<big>List of current Chief Secretaries in the States of India</big>
!style="padding-center:15px;"|S.No.
!style="padding-center:15px;"|State
!style="padding-center:15px;"|Capital
!style="padding-center:15px;"|List
!style="padding-center:15px;"|Chief Secretary
!style="padding-center:15px;"|Batch
|-
|1
|[[Andhra Pradesh]]
|[[Amaravati]]
|
|align=center|G. Sai Prasad, IAS
|align=right|1991
|-
|2
|[[Assam]]
|[[Dispur]]
| [[List of chief secretaries of Assam|List]]
|align=center|Ravi Kota, IAS<ref>{{Cite news |url=https://example.org/kota |work=TOI}}</ref>
|align=right|1993
|-
|3
|[[Himachal Pradesh]]
|[[Shimla]]
|
|align=center|''Kamlesh Kumar Pant'' ''(additional charge)'', IAS
|align=right|1993
|}
"""

POLICE_TABLE = """
{| class="wikitable sortable"
|+State Police Chiefs
!style="padding-center:15px;"|S.No.
!style="padding-center:15px;"|State
!style="padding-center:15px;"|Headquarters
!style="padding-center:15px;"|Name of Police Chief
|-
|1
|[[Andhra Pradesh Police|Andhra Pradesh]]
|[[Amaravati]]
|align=center|[[Harish Kumar Gupta]], [[Indian Police Service|IPS]]
|-
|2
|[[Tripura Police|Tripura]]
|[[Agartala]]
|align=center|Vacant
|-
|3
|[[West Bengal Police|West Bengal]]
|[[Kolkata]]
|align=center|''Siddh Nath Gupta (acting)'', [[Indian Police Service|IPS]]
|}
"""


def test_columns_are_found_by_header_and_names_cleaned():
    rows = wb.parse_table(
        STATES_TABLE, "List of current Chief Secretaries in the States", "chief_secretary", "X"
    )
    assert [(r.place, r.name, r.additional_charge) for r in rows] == [
        ("Andhra Pradesh", "G. Sai Prasad", False),
        ("Assam", "Ravi Kota", False),
        ("Himachal Pradesh", "Kamlesh Kumar Pant", True),
    ]
    assert rows[1].citation == "https://example.org/kota" and rows[0].citation is None


def test_police_table_link_text_vacancies_and_acting():
    rows = wb.parse_table(POLICE_TABLE, "State Police Chiefs", "dgp", "X")
    assert [(r.place, r.name, r.acting) for r in rows] == [
        ("Andhra Pradesh", "Harish Kumar Gupta", False),
        ("West Bengal", "Siddh Nath Gupta", True),
    ]


def observed(names: dict[str, str]):
    # Enough rows to pass the partial-page guard: Chief Secretaries for every current state/UT.
    slugs = [e.slug for e in REF.entities if e.type in ("state", "ut") and e.valid_to is None]
    rows = [(s, "chief_secretary", names.get(s, f"CS of {s}"), "https://example.org", None) for s in slugs]
    rows += [(s, "dgp", f"DGP of {s}", "https://example.org", None) for s in slugs]
    return rows


def open_terms(db, slug, office_type):
    return db.run(
        """select p.name, t.start_date, t.end_date from office_term t join office o on o.id = t.office_id
           join entity e on e.id = o.entity_id join person p on p.id = t.person_id
           where e.slug = :s and o.office_type = :o order by t.start_date, p.name""",
        s=slug,
        o=office_type,
    )


def test_observed_terms_open_persist_and_close_on_change(db):
    seed(db, REF)
    day1, day2 = date(2026, 10, 3), date(2026, 10, 10)
    first = load_observed_terms(db, observed({"assam": "Ravi Kota"}), NAMES, RANKED, day1)
    assert first == {"opened": 72, "closed": 0, "unchanged": 0}

    again = load_observed_terms(db, observed({"assam": "Ravi Kota"}), NAMES, RANKED, day1)
    assert again == {"opened": 0, "closed": 0, "unchanged": 72}

    changed = load_observed_terms(db, observed({"assam": "New Person"}), NAMES, RANKED, day2)
    assert changed == {"opened": 1, "closed": 1, "unchanged": 71}
    assert open_terms(db, "assam", "chief_secretary") == [
        ["Ravi Kota", day1, day2 - timedelta(days=1)],
        ["New Person", day2, None],
    ]
    note = scalar(
        db, "select review_note from office_term where end_date is null and external_id like '%new-person'"
    )
    assert "first observed in office on 2026-10-10" in note


def test_observed_categories_and_titles(db):
    seed(db, REF)
    load_observed_terms(db, observed({}), NAMES, RANKED, date(2026, 10, 3))
    rows = db.run(
        "select o.office_type, o.title from office o join entity e on e.id = o.entity_id"
        " where e.slug = 'delhi'"
    )
    assert dict(rows) == {
        "chief_secretary": "Chief Secretary of Delhi",
        "dgp": "Commissioner of Police, Delhi",
    }
    cats = dict(
        db.run(
            """select o.office_type, count(*) from office_category c join office o on o.id = c.office_id
               join entity e on e.id = o.entity_id where e.slug = 'assam' group by 1"""
        )
    )
    assert cats == {"chief_secretary": len(RANKED), "dgp": 1}


def test_a_partial_page_never_closes_terms(db):
    seed(db, REF)
    load_observed_terms(db, observed({}), NAMES, RANKED, date(2026, 10, 3))
    with pytest.raises(ValueError, match="refusing"):
        load_observed_terms(db, observed({})[:10], NAMES, RANKED, date(2026, 10, 10))
    assert scalar(db, "select count(*) from office_term where end_date is not null") == 0
