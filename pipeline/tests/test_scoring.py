import math
from datetime import date

from unnati import scoring
from unnati.scoring import Goalpost, IndicatorSpec, Value


def v(indicator, entity, end_year, value, label=None, start_year=None):
    start = date(start_year or end_year, 1, 1)
    return Value(indicator, entity, start, date(end_year, 12, 31), label or str(end_year), value)


def test_goalposts_use_targets_and_percentiles():
    specs = {
        "imr": IndicatorSpec("imr", "health", "lower_better", target=None),
        "mmr": IndicatorSpec("mmr", "health", "lower_better", target=70),
    }
    values = [v("imr", f"s{i}", 2024, float(i)) for i in range(41)] + [
        v("mmr", "a", 2024, 100),
        v("mmr", "b", 2024, 300),
    ]
    values.append(v("imr", "s99", 2010, 500))  # before the 2015 base: ignored
    posts = scoring.goalposts(values, specs)
    assert posts["imr"] == Goalpost(worst=39.0, best=1.0)
    assert posts["mmr"].best == 70 and posts["mmr"].worst == 295.0


def test_indicator_score_is_clipped_and_direction_aware():
    assert scoring.indicator_score(5, Goalpost(worst=39, best=1)) == 100 * 34 / 38
    assert scoring.indicator_score(0, Goalpost(worst=39, best=1)) == 100
    assert scoring.indicator_score(60, Goalpost(worst=39, best=1)) == 0


def test_select_uses_a_common_period_when_most_places_have_it():
    # NFHS-6 covers 2 of 4 places, NFHS-5 all 4: everyone is compared on NFHS-5.
    rows = [v("stunting", e, 2021, 30, "NFHS-5", 2019) for e in "abcd"]
    rows += [v("stunting", e, 2024, 25, "NFHS-6", 2023) for e in "ab"]
    chosen = scoring.select(rows, date(2026, 10, 1))
    assert {chosen[("stunting", e)].label for e in "abcd"} == {"NFHS-5"}


def test_select_falls_back_to_each_place_latest_and_ignores_old_values():
    rows = [v("imr", "big", 2024, 20), v("imr", "big", 2023, 21), v("imr", "small", 2024, 9, "2022-24", 2022)]
    rows.append(v("imr", "stale", 2015, 50))
    chosen = scoring.select(rows, date(2026, 10, 1))
    assert chosen[("imr", "big")].label == "2024" and chosen[("imr", "small")].label == "2022-24"
    assert ("imr", "stale") not in chosen
    # an earlier edition does not see later data
    assert scoring.select(rows, date(2023, 12, 31))[("imr", "big")].value == 21


def test_competition_ranks_tie_on_one_decimal():
    assert scoring.competition_ranks({"a": 70.04, "b": 70.01, "c": 65}) == {"a": 1, "b": 1, "c": 3}


def test_pillar_and_composite_need_enough_data():
    specs = {
        f"i{p}{n}": IndicatorSpec(f"i{p}{n}", f"p{p}", "higher_better") for p in range(8) for n in range(5)
    }
    posts = {k: Goalpost(worst=0, best=100) for k in specs}
    full = {(k, "x"): v(k, "x", 2024, 50) for k in specs}
    # "y" has 3 of 5 indicators (60%) in six pillars and 2 of 5 in two: six pillars, so scored.
    partial = {(k, "y"): v(k, "y", 2024, 80) for k in specs if int(k[2]) < (3 if int(k[1]) < 6 else 2)}
    scores = scoring.score_edition(
        {**full, **partial}, specs, posts, {"x": "large_state", "y": "large_state"}
    )
    composite = {s.entity: s for s in scores if s.level == "composite"}
    assert composite["x"].score == 50 and composite["y"].score == 80
    assert composite["y"].coverage == 6 / 8
    assert (composite["y"].rank_overall, composite["x"].rank_overall) == (1, 2)
    pillar7 = next(s for s in scores if s.entity == "y" and s.key == "p7")
    assert pillar7.score is None and pillar7.coverage == 0.4


def test_hdi_is_a_geometric_mean_with_undp_goalposts():
    # life 72.5 -> 0.808; enrolment mean 60 -> 0.6; income Rs 1,50,000 -> ln-scaled 0.692
    value = scoring.hdi(72.5, [80.0, 40.0], 150_000.0)
    expected = 100 * ((52.5 / 65) * 0.6 * (math.log(15) / math.log(50))) ** (1 / 3)
    assert abs(value - expected) < 1e-9
    assert scoring.hdi(None, [80.0], 150_000.0) is None
    assert scoring.hdi(72.5, [], 150_000.0) is None


def test_mean_index_needs_most_dimensions():
    specs = {k: IndicatorSpec(k, None, "higher_better") for k in ("a1", "a2", "b1", "c1")}
    posts = {k: Goalpost(worst=0, best=100) for k in specs}
    index = scoring.ThematicIndex("demo", "mean", {"A": ["a1", "a2"], "B": ["b1"], "C": ["c1"]})
    chosen = {
        ("a1", "x"): v("a1", "x", 2024, 40),
        ("a2", "x"): v("a2", "x", 2024, 60),
        ("b1", "x"): v("b1", "x", 2024, 80),
    }
    chosen[("c1", "y")] = v("c1", "y", 2024, 90)
    scores = scoring.score_edition(chosen, specs, posts, {"x": "large_state", "y": "large_state"}, [index])
    demo = {s.entity: s for s in scores if s.key == "demo"}
    assert demo["x"].score == 65 and demo["x"].coverage == 2 / 3 and demo["x"].rank_overall == 1
    assert demo["y"].score is None  # one of three dimensions
