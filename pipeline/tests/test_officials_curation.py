from datetime import date

import pytest

from unnati.connectors import wikidata_officials as wd
from unnati.connectors import wikipedia_incumbents as wp
from unnati.reference import load_reference

REF = load_reference()
ENTITIES = {e.slug: e.to_entity() for e in REF.entities}
MAPPINGS = wd.load_position_map()
TODAY = date(2026, 10, 3)
CM_KERALA, GOV_KERALA = "Q26218416", "Q1748927"


def build(*raw_terms):
    return wd.build_terms(raw_terms, [], MAPPINGS, ENTITIES, TODAY).terms


def raw(statement, position, person, name, start, end=None, groups=()):
    return wd.RawTerm(statement, position, person, name, None, start, end, tuple(groups))


# --- the shipped curation files ----------------------------------------------------------------


def test_curated_file_is_valid_and_sourced():
    terms = wd.curated_terms(wd.load_curated(), MAPPINGS)
    assert terms, "officials.yaml should not be empty"
    for t in terms:
        assert t.source_url.startswith("https://")
        assert t.person_qid.startswith("Q")
        assert t.end is None or t.end >= t.start
        assert t.source_type == "curated" and not t.needs_review
    assert len({t.external_id for t in terms}) == len(terms)


def test_overrides_file_entries_all_cite_sources():
    for key, override in wd.load_overrides().items():
        assert key.startswith("wikidata:") and override["source_url"].startswith("https://"), key


def test_curated_terms_do_not_overlap_each_other():
    terms = wd.curated_terms(wd.load_curated(), MAPPINGS)
    wd.flag_overlaps(terms, TODAY)
    assert not [t.external_id for t in terms if t.needs_review]


# --- curated terms ------------------------------------------------------------------------------


def test_curated_terms_need_identity_and_source():
    entry = {"entity": "keralam", "office": "chief_minister", "person": "X", "start": date(2026, 5, 18)}
    with pytest.raises(ValueError, match="wikidata"):
        wd.curated_terms([entry], MAPPINGS)
    with pytest.raises(ValueError, match="unknown office"):
        wd.curated_terms(
            [{**entry, "office": "mayor", "wikidata": "Q1", "source_url": "https://x"}], MAPPINGS
        )


def test_curated_party_only_for_elected_offices():
    [cm, gov] = wd.curated_terms(
        [
            {
                "entity": "keralam",
                "office": "chief_minister",
                "person": "A",
                "wikidata": "Q1",
                "start": date(2026, 5, 18),
                "party": "Q10225",
                "source_url": "https://x",
            },
            {
                "entity": "keralam",
                "office": "governor",
                "person": "B",
                "wikidata": "Q2",
                "start": date(2025, 1, 2),
                "party": "Q10230",
                "source_url": "https://x",
                "additional_charge": True,
            },
        ],
        MAPPINGS,
    )
    assert cm.party_qid == "Q10225" and gov.party_qid is None
    assert "additional charge" in gov.advisories


def test_wikidata_duplicate_of_a_curated_term_is_dropped_and_reported():
    wikidata_terms = build(raw("s1", CM_KERALA, "Q6956446", "V. D. Satheesan", date(2026, 5, 19)))
    curated = wd.curated_terms(
        [
            {
                "entity": "keralam",
                "office": "chief_minister",
                "person": "V. D. Satheesan",
                "wikidata": "Q6956446",
                "start": date(2026, 5, 18),
                "source_url": "https://x",
            }
        ],
        MAPPINGS,
    )
    merged, notes = wd.merge_curated(wikidata_terms, curated)
    assert [t.source_type for t in merged] == ["curated"]
    assert "can be retired" in notes[0]


# --- overrides ----------------------------------------------------------------------------------


def test_override_fixes_a_mislabelled_name_and_closes_the_term():
    [term] = build(raw("s1", GOV_KERALA, "Q7289378", "Q7289378", date(2023, 2, 18)))
    assert term.needs_review  # no English name, and possibly stale
    wd.apply_overrides(
        [term],
        {
            term.external_id: {
                "person_name": "Ramesh Bais",
                "end": date(2024, 7, 30),
                "source_url": "https://x",
            }
        },
    )
    assert (term.person_name, term.end, term.needs_review) == ("Ramesh Bais", date(2024, 7, 30), False)


def test_maintainer_note_does_not_hide_a_term():
    [term] = build(raw("s1", GOV_KERALA, "Q1", "Someone", date(2025, 1, 2)))
    wd.apply_overrides([term], {term.external_id: {"note": "checked", "source_url": "https://x"}})
    assert not term.needs_review and "maintainer: checked" in term.advisories


# --- Wikipedia cross-check ----------------------------------------------------------------------

CM_TABLE = """
== Current list ==
{| class="wikitable sortable"
|+List of chief ministers
|-
! State
|-
| [[Keralam]]
|[[Chief Minister of Kerala|List]]
| [[File:x.jpg|70px]]
! [[V. D. Satheesan]]
| {{dts|format=dmy|2026|05|18}}<br /><small>({{ayd|2026|05|18}})</small>
| [[United Democratic Front (Kerala)|'''UDF''']]
|-
| [[Goa]]
|[[Chief Minister of Goa|List]]
! [[Pramod Sawant]]
| {{dts|format=dmy|2019|3|19}}
|}
"""

GOVERNOR_TABLE = """
== List of incumbent governors ==
{| class="wikitable sortable"
! State
|-
| [[Goa]]
|[[List of governors of Goa|List]]
| [[Ashok Gajapathi Raju|'''Ashok Gajapati Raju''']]
| {{dts|format=dmy|2025|7|26}}
|-
| [[Tamil Nadu]]
|[[List of governors of Tamil Nadu|List]]
| '''[[Rajendra Arlekar]]'''
| {{dts|format=dmy|2026|3|12}}
|}
"""


def test_parse_incumbent_tables():
    cms = wp.parse_table(CM_TABLE, "List of chief ministers", "chief_minister")
    assert [(i.place, i.article, i.start) for i in cms] == [
        ("Keralam", "V. D. Satheesan", date(2026, 5, 18)),
        ("Goa", "Pramod Sawant", date(2019, 3, 19)),
    ]
    govs = wp.parse_table(GOVERNOR_TABLE, "List of incumbent governors", "governor")
    assert [(i.place, i.article, i.person) for i in govs] == [
        ("Goa", "Ashok Gajapathi Raju", "Ashok Gajapati Raju"),
        ("Tamil Nadu", "Rajendra Arlekar", "Rajendra Arlekar"),
    ]


def test_article_titles_follow_redirects():
    payload = {
        "query": {
            "normalized": [{"from": "Santosh_Kumar_Gangwar", "to": "Santosh Kumar Gangwar"}],
            "redirects": [{"from": "Santosh Kumar Gangwar", "to": "Santosh Gangwar"}],
            "pages": {"1": {"title": "Santosh Gangwar", "pageprops": {"wikibase_item": "Q7420653"}}},
        }
    }
    qids = wp.parse_pageprops(payload)
    assert qids["Santosh Kumar Gangwar"] == qids["Santosh_Kumar_Gangwar"] == "Q7420653"


def cross_check(terms, incumbents, qids):
    padding = [wp.Incumbent("Atlantis", "governor", "Nobody", "Nobody", None)] * wp.MIN_ROWS
    return wp.cross_check(terms, incumbents + padding, qids, REF.resolver(), TODAY)


def test_agreement_confirms_a_long_serving_incumbent():
    [term] = build(raw("s1", "Q55018632", "Q28222879", "Pramod Sawant", date(2019, 3, 19)))
    assert term.needs_review  # in office since 2019 with no end date
    cross_check(
        [term],
        [wp.Incumbent("Goa", "chief_minister", "Pramod Sawant", "Pramod Sawant", None)],
        {"Pramod Sawant": "Q28222879"},
    )
    assert not term.needs_review and any("confirmed current" in a for a in term.advisories)


def test_disagreement_hides_the_stale_holder_even_if_reviewed():
    [term] = build(raw("s1", "Q26218416", "Q3595385", "Pinarayi Vijayan", date(2021, 5, 20)))
    term.reviewed = True
    report = cross_check(
        [term],
        [wp.Incumbent("Keralam", "chief_minister", "V. D. Satheesan", "V. D. Satheesan", date(2026, 5, 18))],
        {"V. D. Satheesan": "Q6956446"},
    )
    assert term.needs_review and "Wikipedia lists V. D. Satheesan" in term.conflicts[0]
    assert any("needs a curated term: keralam chief_minister" in line for line in report)


def test_cross_check_is_skipped_when_the_page_layout_changes():
    [term] = build(raw("s1", "Q26218416", "Q3595385", "Pinarayi Vijayan", date(2021, 5, 20)))
    report = wp.cross_check([term], [], {}, REF.resolver(), TODAY)
    assert "skipped" in report[0] and not term.conflicts
