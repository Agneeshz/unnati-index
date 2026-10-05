from collections import Counter

from unnati.core.periods import calendar_year, fiscal_year
from unnati.reference import load_reference

REF = load_reference()
CURRENT = [e for e in REF.entities if e.type in ("state", "ut") and e.valid_to is None]


def test_36_current_states_and_uts():
    assert len(CURRENT) == 36
    assert Counter(e.type for e in CURRENT) == {"state": 28, "ut": 8}


def test_peer_groups_follow_niti_grouping():
    assert Counter(e.peer_group for e in CURRENT) == {
        "large_state": 18,
        "ne_himalayan_state": 10,
        "ut": 8,
    }


def test_current_entities_have_codes():
    for e in CURRENT:
        assert e.lgd_code, e.slug
        assert e.wikidata_qid, e.slug
    assert len({e.lgd_code for e in CURRENT}) == 36


def test_every_current_entity_resolves_by_its_own_name():
    resolver = REF.resolver()
    for e in CURRENT:
        assert resolver.resolve(e.name, calendar_year(2025)).slug == e.slug


def test_aliases_are_unambiguous_across_sample_periods():
    resolver = REF.resolver()
    periods = [fiscal_year(y) for y in range(2005, 2027)] + [calendar_year(y) for y in range(2005, 2027)]
    for alias in REF.aliases:
        for period in periods:
            try:
                resolver.resolve(alias.alias, period)
            except LookupError as err:
                # Not existing yet/any more is fine; ambiguity is not.
                assert "none is valid" in str(err), f"{alias.alias} in {period.label}: {err}"


def test_lineage_dates_line_up_with_entity_validity():
    by_slug = {e.slug: e for e in REF.entities}
    for row in REF.lineage:
        before, after = by_slug[row.predecessor_slug], by_slug[row.successor_slug]
        assert before.valid_to is not None and before.valid_to < row.event_date
        assert after.valid_from == row.event_date


def test_composite_has_eight_pillars_with_four_to_seven_indicators():
    per_pillar = Counter(i.pillar for i in REF.indicators if i.pillar)
    assert set(per_pillar) == {p.id for p in REF.pillars}
    assert all(4 <= n <= 7 for n in per_pillar.values()), per_pillar
    assert sum(per_pillar.values()) == 44  # v1.1: adds spousal violence (NFHS) to inclusion


def test_unranked_categories_have_no_composite_indicators():
    unranked = {c.id for c in REF.categories if not c.ranked}
    assert not [i.id for i in REF.indicators if i.pillar and i.category in unranked]


def test_every_dataset_is_used_or_registered_for_later():
    used = {i.dataset for i in REF.indicators}
    registered = {d.id for d in REF.registry.datasets}
    assert used <= registered


def test_valid_ranges_contain_targets():
    for i in REF.indicators:
        if i.target is not None:
            assert i.valid_min is None or i.valid_min <= i.target, i.id
            assert i.valid_max is None or i.target <= i.valid_max, i.id


def test_every_indicator_unit_and_index_has_hindi_text():
    ref = load_reference()
    hi = ref.hindi
    assert {i.id for i in ref.indicators} - set(hi.indicators) == set()
    assert {i.unit for i in ref.indicators} - set(hi.units) == set()
    assert {x.id for x in ref.indices} - set(hi.indices) == set()
    for i in ref.indicators:
        assert bool(hi.indicators[i.id].caveat) == bool(i.caveat), f"{i.id}: caveat missing in one language"
    for x in ref.indices:
        assert bool(hi.indices[x.id].caveat) == bool(x.caveat), x.id
    # The site formats percentages by the unit's first character, so Hindi units must keep it.
    for unit, text in hi.units.items():
        assert unit.startswith("%") == text.startswith("%"), unit
