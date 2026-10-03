from collections import Counter
from datetime import date

import pytest

from unnati.connectors import wikidata_officials as wd
from unnati.reference import load_reference

REF = load_reference()
ENTITIES = {e.slug: e.to_entity() for e in REF.entities}
MAPPINGS = wd.load_position_map()
TODAY = date(2026, 10, 3)

CM_KERALA, GOV_KERALA = "Q26218416", "Q1748927"
CM_AP, CM_JK = "Q1813083", "Q38882023"
CPIM, CPIML, INC, NCP = "Q1061", "Q1062", "Q10225", "Q10226"


def raw(statement, position, person="Q1", name="Person One", start=None, end=None, groups=()):
    return wd.RawTerm(statement, position, person, name, None, start, end, tuple(groups))


def build(*raw_terms, memberships=()):
    return wd.build_terms(raw_terms, memberships, MAPPINGS, ENTITIES, TODAY)


# --- the position map --------------------------------------------------------------------------


def test_position_map_covers_every_state_and_ut():
    current = {e.slug: e for e in REF.entities if e.type in ("state", "ut") and e.valid_to is None}
    offices = Counter((m.entity_slug, m.office_type) for m in MAPPINGS)
    for slug, entity in current.items():
        if entity.type == "state":
            assert offices[(slug, "chief_minister")] == 1, slug
            assert offices[(slug, "governor")] == 1, slug
        else:
            heads = offices[(slug, "lieutenant_governor")] + offices[(slug, "administrator")]
            assert heads == 1, slug
    for slug in ("delhi", "puducherry", "jammu-and-kashmir"):
        assert offices[(slug, "chief_minister")] == 1


def test_position_map_is_consistent():
    assert {m.entity_slug for m in MAPPINGS} <= ENTITIES.keys()
    pairs = [(m.position_qid, m.entity_slug) for m in MAPPINGS]
    assert len(pairs) == len(set(pairs))
    titles = {(m.entity_slug, m.office_type): m.title for m in MAPPINGS}
    assert titles[("kerala", "chief_minister")] == "Chief Minister of Kerala"


# --- parsing -----------------------------------------------------------------------------------


def test_parse_terms_groups_rows_by_statement():
    e = "http://www.wikidata.org/entity/"
    rows = [
        {
            "statement": f"{e}statement/Q9-abc",
            "position": f"{e}{CM_KERALA}",
            "person": f"{e}Q9",
            "personLabel": "A. Leader",
            "nameHi": "ए. नेता",
            "start": "2016-05-25T00:00:00Z",
            "group": f"{e}{CPIM}",
            "groupLabel": "CPI(M)",
        },
        {
            "statement": f"{e}statement/Q9-abc",
            "position": f"{e}{CM_KERALA}",
            "person": f"{e}Q9",
            "personLabel": "A. Leader",
            "start": "2016-05-25T00:00:00Z",
            "group": f"{e}{CPIML}",
            "groupLabel": "CPI(ML)",
        },
    ]
    [term] = wd.parse_terms(rows)
    assert term.statement_id == "Q9-abc"
    assert term.person_name_hi == "ए. नेता"
    assert term.start == date(2016, 5, 25) and term.end is None
    assert term.group_parties == ((CPIM, "CPI(M)"), (CPIML, "CPI(ML)"))


# --- boundaries --------------------------------------------------------------------------------


def test_andhra_pradesh_terms_follow_the_2014_split():
    result = build(
        raw("s1", CM_AP, start=date(2004, 5, 14), end=date(2009, 9, 2), groups=[(INC, "INC")]),
        raw("s2", CM_AP, person="Q2", start=date(2014, 6, 8), end=date(2019, 5, 29), groups=[(INC, "X")]),
    )
    placed = {(t.person_qid, t.entity_slug) for t in result.terms}
    assert placed == {("Q1", "andhra-pradesh-undivided"), ("Q2", "andhra-pradesh")}


def test_a_term_spanning_the_split_is_clipped_into_both_entities():
    result = build(raw("s1", CM_AP, start=date(2013, 1, 1), end=date(2015, 1, 1), groups=[(INC, "INC")]))
    spans = {t.entity_slug: (t.start, t.end) for t in result.terms}
    assert spans == {
        "andhra-pradesh-undivided": (date(2013, 1, 1), date(2014, 6, 1)),
        "andhra-pradesh": (date(2014, 6, 2), date(2015, 1, 1)),
    }
    assert len({t.external_id for t in result.terms}) == 2


def test_jammu_and_kashmir_state_and_ut():
    result = build(
        raw("s1", CM_JK, start=date(2016, 4, 4), end=date(2018, 6, 19), groups=[(INC, "X")]),
        raw("s2", CM_JK, person="Q2", start=date(2024, 10, 16), groups=[(INC, "X")]),
    )
    assert {(t.person_qid, t.entity_slug) for t in result.terms} == {
        ("Q1", "jammu-and-kashmir-state"),
        ("Q2", "jammu-and-kashmir"),
    }


def test_old_terms_duplicates_and_undated_terms():
    result = build(
        raw("s1", CM_KERALA, start=date(1991, 6, 24), end=date(1995, 3, 22)),
        raw("s2", CM_KERALA, start=date(2006, 5, 18), end=date(2011, 5, 14), groups=[(CPIM, "CPI(M)")]),
        raw("s3", CM_KERALA, start=date(2006, 5, 18), end=date(2011, 5, 14), groups=[(CPIM, "CPI(M)")]),
        raw("s4", CM_KERALA, person="Q4", name="Undated"),
    )
    assert [t.external_id for t in result.terms] == ["wikidata:s2:kerala"]
    assert result.problems == ["Undated (Q4): term has no start date; skipped"]


# --- parties -----------------------------------------------------------------------------------


def membership(party, label, start=None, end=None, person="Q1"):
    return wd.PartyMembership(person, party, label, start, end)


def test_party_agreed_by_both_sources():
    [term] = build(
        raw("s1", CM_KERALA, start=date(2006, 5, 18), end=date(2011, 5, 14), groups=[(CPIM, "CPI(M)")]),
        memberships=[membership(CPIM, "CPI(M)")],
    ).terms
    assert (term.party_qid, term.needs_review) == (CPIM, False)


def test_conflicting_party_sources_leave_the_party_blank():
    [term] = build(
        raw("s1", CM_KERALA, start=date(2016, 5, 25), end=date(2021, 5, 1), groups=[(CPIML, "CPI(ML)")]),
        memberships=[membership(CPIM, "CPI(M)")],
    ).terms
    # A wrong party is never shown, but the person and tenure are.
    assert term.party_qid is None and not term.needs_review
    assert "party sources disagree" in term.advisories[0]
    assert "party sources disagree" in term.review_note


def test_membership_dates_decide_the_party():
    terms = build(
        raw("s1", CM_KERALA, start=date(2001, 5, 17), end=date(2004, 8, 29)),
        memberships=[
            membership(INC, "INC", end=date(2005, 1, 1)),
            membership(NCP, "NCP", start=date(2005, 1, 2)),
        ],
    ).terms
    assert terms[0].party_qid == INC and not terms[0].needs_review


def test_undated_memberships_in_two_parties_are_ambiguous():
    [term] = build(
        raw("s1", CM_KERALA, start=date(2001, 5, 17), end=date(2004, 8, 29)),
        memberships=[membership(INC, "INC"), membership(NCP, "NCP")],
    ).terms
    assert term.party_qid is None and "several possible parties" in term.advisories[0]
    assert not term.needs_review


def test_governors_never_get_a_party():
    [term] = build(
        raw("s1", GOV_KERALA, start=date(2019, 9, 6), end=date(2024, 12, 24)),
        memberships=[membership(INC, "INC")],
    ).terms
    assert term.party_qid is None and not term.needs_review


# --- freshness and overlaps --------------------------------------------------------------------


def test_long_running_incumbent_is_flagged_as_possibly_stale():
    [term] = build(raw("s1", CM_KERALA, start=date(2016, 5, 25), groups=[(CPIM, "CPI(M)")])).terms
    assert term.needs_review and "possibly out of date" in term.notes[0]


def test_recent_incumbent_is_fine():
    [term] = build(raw("s1", GOV_KERALA, start=date(2025, 1, 2))).terms
    assert not term.needs_review


def test_overlapping_terms_are_flagged():
    terms = build(
        raw("s1", GOV_KERALA, start=date(2019, 9, 6), end=date(2024, 12, 24)),
        raw("s2", GOV_KERALA, person="Q2", name="Second", start=date(2024, 6, 1)),
    ).terms
    assert all(t.needs_review for t in terms)
    assert any("overlaps with Second" in n for n in terms[0].notes)


def test_handover_on_the_same_day_is_not_an_overlap():
    terms = build(
        raw("s1", GOV_KERALA, start=date(2019, 9, 6), end=date(2024, 12, 24)),
        raw("s2", GOV_KERALA, person="Q2", start=date(2024, 12, 24)),
    ).terms
    assert not any(t.needs_review for t in terms)


# --- overrides ---------------------------------------------------------------------------------


def test_overrides_settle_a_flagged_term():
    terms = build(
        raw("s1", CM_KERALA, start=date(2016, 5, 25), groups=[(CPIML, "CPI(ML)")]),
        memberships=[membership(CPIM, "CPI(M)")],
    ).terms
    unused = wd.apply_overrides(
        terms,
        {
            "wikidata:s1:kerala": {
                "party": CPIM,
                "party_label": "CPI(M)",
                "end": date(2026, 5, 20),
                "source_url": "https://example.org/gazette",
                "reviewed": True,
            },
            "wikidata:nope:kerala": {"source_url": "https://example.org"},
        },
    )
    [term] = terms
    assert (term.party_qid, term.end, term.needs_review) == (CPIM, date(2026, 5, 20), False)
    assert term.source_url == "https://example.org/gazette"
    assert unused == ["wikidata:nope:kerala"]


def test_overrides_need_a_source():
    terms = build(raw("s1", GOV_KERALA, start=date(2025, 1, 2))).terms
    with pytest.raises(ValueError, match="source_url"):
        wd.apply_overrides(terms, {"wikidata:s1:kerala": {"reviewed": True}})


# --- accountability ----------------------------------------------------------------------------


def test_categories_for_each_kind_of_office():
    ranked = ["economy", "crime", "governance", "health"]
    assert wd.categories_for("chief_minister", "kerala", True, ranked) == ranked
    assert wd.categories_for("governor", "kerala", True, ranked) == ["governance"]
    assert wd.categories_for("lieutenant_governor", "ladakh", False, ranked) == ranked
    assert wd.categories_for("lieutenant_governor", "delhi", True, ranked) == ["governance", "crime"]
    assert wd.categories_for("lieutenant_governor", "puducherry", True, ranked) == ["governance"]
