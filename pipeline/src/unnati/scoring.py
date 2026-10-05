"""Unnati Index scoring, methodology v1 (see the plan, section 3, and /methodology).

1. Goalposts are fixed per methodology version: the "best" end is the indicator's target where
   one exists, otherwise the 97.5th percentile of state/UT values since 2015; the "worst" end
   is the 2.5th percentile (sides swapped for lower-is-better indicators).
2. For an edition, each indicator uses one common period for every place when it can: the most
   recent period that at least 80% of the places with recent data report (so NFHS-6 states are
   not compared with NFHS-5 ones). Places missing from it, and indicators where no period
   reaches 80% (e.g. IMR, annual for bigger states but 3-year pooled for smaller ones), use
   each place's own latest value. Values whose period ended more than six years before the
   edition's cut-off are ignored (NFHS rounds are about five years apart and published late).
3. Indicator score = 100 * (x - worst) / (best - worst), clipped to 0-100; for very skewed
   per-person values (income, exports, electricity) the same on a log scale.
4. A pillar is the weighted mean of its indicator scores when at least 60% of them have data
   (3 of 5, 4 of 6); the Unnati Index is the mean of the pillars when at least six of eight have scores.
5. Ranks are competition ranks ("1, 2, 2, 4") on scores rounded to one decimal, overall and
   within peer groups. India is scored but not ranked.

This module is pure: database reads and writes live in `score_store`."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

METHODOLOGY_VERSION = "1.1"
# Published changes, newest first. A new version inherits the previous version's goalposts for
# every indicator it keeps, so only what changed moves the scores.
METHODOLOGY_NOTES = {
    "1.1": "Inclusion pillar adds violence against women by husbands (NFHS), a survey measure "
    "unaffected by police reporting; the Gender Equality and Social Progress indices use it instead "
    "of registered crimes against women.",
    "1.0": "Unnati Index v1: fixed goalposts, 8 equal-weight pillars",
}
COMPOSITE_KEY = "unnati-index"
GOALPOST_BASE = date(2015, 1, 1)
COMMON_PERIOD_SHARE = 0.8
MAX_AGE_YEARS = 6
PILLAR_MIN_SHARE = 0.6
COMPOSITE_MIN_PILLARS = 6
NATIONAL = "india"


@dataclass(frozen=True)
class Value:
    indicator_id: str
    entity: str
    start: date
    end: date
    label: str
    value: float


@dataclass(frozen=True)
class IndicatorSpec:
    id: str
    pillar: str | None
    direction: str  # higher_better | lower_better
    target: float | None = None
    weight: float = 1.0
    log: bool = False  # score on a log scale (very skewed per-person values)


@dataclass(frozen=True)
class Goalpost:
    worst: float
    best: float


@dataclass
class Score:
    entity: str
    level: str  # indicator | pillar | composite
    key: str
    score: float | None
    coverage: float | None = None
    period_label: str | None = None
    rank_overall: int | None = None
    rank_peer: int | None = None


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolation percentile (q in 0-1) of a non-empty list."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def goalposts(values: Iterable[Value], specs: Mapping[str, IndicatorSpec]) -> dict[str, Goalpost]:
    by_indicator: dict[str, list[float]] = defaultdict(list)
    for v in values:
        if v.indicator_id in specs and v.entity != NATIONAL and v.end >= GOALPOST_BASE:
            by_indicator[v.indicator_id].append(v.value)
    out = {}
    for indicator_id, spec in specs.items():
        data = by_indicator.get(indicator_id)
        if not data:
            continue
        low, high = percentile(data, 0.025), percentile(data, 0.975)
        if spec.direction == "higher_better":
            post = Goalpost(worst=low, best=spec.target if spec.target is not None else high)
        else:
            post = Goalpost(worst=high, best=spec.target if spec.target is not None else low)
        if post.best != post.worst:
            out[indicator_id] = post
    return out


def select(values: Iterable[Value], cutoff: date) -> dict[tuple[str, str], Value]:
    """(indicator, entity) -> the value an edition with this cut-off uses (rule 2 above)."""
    oldest = date(cutoff.year - MAX_AGE_YEARS, cutoff.month, cutoff.day)
    by_indicator: dict[str, list[Value]] = defaultdict(list)
    for v in values:
        if oldest <= v.end <= cutoff:
            by_indicator[v.indicator_id].append(v)
    chosen: dict[tuple[str, str], Value] = {}
    for indicator_id, rows in by_indicator.items():
        places = {v.entity for v in rows if v.entity != NATIONAL}
        latest: dict[str, Value] = {}
        for v in sorted(rows, key=lambda v: (v.end, v.start)):
            latest[v.entity] = v
        by_period: dict[tuple[date, date, str], dict[str, Value]] = defaultdict(dict)
        for v in rows:
            by_period[(v.end, v.start, v.label)][v.entity] = v
        common = None
        for key in sorted(by_period, reverse=True):
            reported = {e for e in by_period[key] if e != NATIONAL}
            if places and len(reported) / len(places) >= COMMON_PERIOD_SHARE:
                common = key
                break
        for entity, newest in latest.items():
            if common is None:
                chosen[(indicator_id, entity)] = newest
                continue
            in_common = by_period[common].get(entity)
            if in_common is not None:
                chosen[(indicator_id, entity)] = in_common
            else:  # not in the common period: its latest value up to that period
                earlier = [v for v in rows if v.entity == entity and v.end <= common[0]]
                chosen[(indicator_id, entity)] = max(earlier, key=lambda v: v.end) if earlier else newest
    return chosen


def indicator_score(value: float, post: Goalpost, log: bool = False) -> float:
    """0-100 between the goalposts. With `log`, distances are measured on a log scale (as UNDP's
    HDI does for income), so $10 -> $100 counts as much as $100 -> $1,000."""
    if log:
        floor = 1e-9
        value, worst, best = (math.log(max(v, floor)) for v in (value, post.worst, post.best))
        if best == worst:
            return 0.0
        raw = 100 * (value - worst) / (best - worst)
    else:
        raw = 100 * (value - post.worst) / (post.best - post.worst)
    return max(0.0, min(100.0, raw))


def competition_ranks(scores: Mapping[str, float]) -> dict[str, int]:
    """1, 2, 2, 4 ... on scores rounded to one decimal, highest first."""
    rounded = {entity: round(score, 1) for entity, score in scores.items()}
    ordered = sorted(rounded.values(), reverse=True)
    return {entity: ordered.index(score) + 1 for entity, score in rounded.items()}


@dataclass(frozen=True)
class ThematicIndex:
    id: str
    kind: str  # "mean" | "hdi"
    components: Mapping[str, list[str]]  # dimension -> indicator ids


# HDI-style goalposts (UNDP method): life expectancy 20-85 years; enrolment 0-100%; per-capita
# NSDP at constant 2011-12 prices on a log scale, Rs 10,000 to Rs 5,00,000.
HDI_LIFE = (20.0, 85.0)
HDI_INCOME = (10_000.0, 500_000.0)


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def hdi(life: float | None, enrolment: list[float], income: float | None) -> float | None:
    """Geometric mean of the three dimension indices, scaled 0-100."""
    if life is None or income is None or income <= 0 or not enrolment:
        return None
    health = _clip((life - HDI_LIFE[0]) / (HDI_LIFE[1] - HDI_LIFE[0]))
    knowledge = _clip(sum(min(e, 100.0) for e in enrolment) / len(enrolment) / 100)
    span = math.log(HDI_INCOME[1]) - math.log(HDI_INCOME[0])
    wealth = _clip((math.log(income) - math.log(HDI_INCOME[0])) / span)
    return 100 * (health * knowledge * wealth) ** (1 / 3)


def score_edition(
    chosen: Mapping[tuple[str, str], Value],
    specs: Mapping[str, IndicatorSpec],
    posts: Mapping[str, Goalpost],
    peer_groups: Mapping[str, str],
    indices: Iterable[ThematicIndex] = (),
) -> list[Score]:
    """Indicator, pillar and composite scores with ranks for every place in `peer_groups`
    (state/UT slug -> peer group) and India, plus thematic indices (level "composite", key =
    index id). Specs without a pillar are scored as indicators only, for the indices."""
    places = [*peer_groups, NATIONAL]
    pillars: dict[str, list[IndicatorSpec]] = defaultdict(list)
    for spec in specs.values():
        if spec.pillar:
            pillars[spec.pillar].append(spec)
    out: list[Score] = []
    indicator_scores: dict[tuple[str, str], float] = {}
    pillar_scores: dict[str, dict[str, float]] = defaultdict(dict)
    composite: dict[str, float] = {}
    for entity in places:
        for spec in specs.values():
            value = chosen.get((spec.id, entity))
            post = posts.get(spec.id)
            if value is None or post is None:
                continue
            s = indicator_score(value.value, post, spec.log)
            indicator_scores[(spec.id, entity)] = s
            out.append(Score(entity, "indicator", spec.id, s, period_label=value.label))
        for pillar_id, members in sorted(pillars.items()):
            total = weight = 0.0
            for spec in members:
                s = indicator_scores.get((spec.id, entity))
                if s is not None:
                    total += s * spec.weight
                    weight += spec.weight
            coverage = weight / sum(spec.weight for spec in members)
            score = total / weight if weight and coverage >= PILLAR_MIN_SHARE - 1e-9 else None
            out.append(Score(entity, "pillar", pillar_id, score, coverage=coverage))
            if score is not None:
                pillar_scores[pillar_id][entity] = score
        scored = [pillar_scores[p][entity] for p in pillars if entity in pillar_scores[p]]
        coverage = len(scored) / len(pillars) if pillars else 0.0
        score = sum(scored) / len(scored) if len(scored) >= COMPOSITE_MIN_PILLARS else None
        out.append(Score(entity, "composite", COMPOSITE_KEY, score, coverage=coverage))
        if score is not None:
            composite[entity] = score

    index_scores: dict[str, dict[str, float]] = defaultdict(dict)
    for index in indices:
        for entity in places:
            if index.kind == "hdi":

                def raw(indicator_id: str, entity: str = entity) -> float | None:
                    v = chosen.get((indicator_id, entity))
                    return v.value if v is not None else None

                enrolment = [v for i in index.components["Knowledge"] if (v := raw(i)) is not None]
                score = hdi(raw(index.components["Health"][0]), enrolment, raw(index.components["Income"][0]))
                coverage = 1.0 if score is not None else 0.0
            else:
                dimensions = []
                for members in index.components.values():
                    have = [indicator_scores[(m, entity)] for m in members if (m, entity) in indicator_scores]
                    if have and len(have) / len(members) >= PILLAR_MIN_SHARE - 1e-9:
                        dimensions.append(sum(have) / len(have))
                coverage = len(dimensions) / len(index.components)
                enough = bool(dimensions) and coverage >= PILLAR_MIN_SHARE - 1e-9
                score = sum(dimensions) / len(dimensions) if enough else None
            out.append(Score(entity, "composite", index.id, score, coverage=coverage))
            if score is not None:
                index_scores[index.id][entity] = score

    # Ranks for pillars and composites, overall and within peer groups (India excluded).
    def rank(level: str, key: str, scores: Mapping[str, float]) -> None:
        ranked = {e: s for e, s in scores.items() if e != NATIONAL}
        overall = competition_ranks(ranked)
        peers: dict[str, dict[str, float]] = defaultdict(dict)
        for e, s in ranked.items():
            peers[peer_groups[e]][e] = s
        peer_rank = {e: r for group in peers.values() for e, r in competition_ranks(group).items()}
        for row in out:
            if row.level == level and row.key == key and row.entity in overall:
                row.rank_overall, row.rank_peer = overall[row.entity], peer_rank[row.entity]

    for pillar_id, scores in pillar_scores.items():
        rank("pillar", pillar_id, scores)
    rank("composite", COMPOSITE_KEY, composite)
    for index_id, scores in index_scores.items():
        rank("composite", index_id, scores)
    return out
