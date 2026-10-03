"""Validate and load indicator observations from any connector.

A connector produces :class:`Observation` rows (indicator, place, period, value). This module
checks them against the indicator catalogue and loads them as a new *vintage*: a row is
written only when the value is new or differs from the latest stored value, so every
government revision is kept and unchanged refreshes cost nothing.

Hard problems (unknown indicator, value outside its valid range, duplicates) reject the whole
batch. Soft problems (thin coverage of states) are recorded but do not block."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from unnati.core.periods import Period
from unnati.db import Connection, scalar, transaction
from unnati.reference import Indicator

# Values that differ by less than this are the same number re-published with rounding noise.
REVISION_TOLERANCE = 1e-9
# Below this share of current states/UTs, an indicator-period is flagged as thinly covered.
MIN_COVERAGE = 0.8


@dataclass(frozen=True)
class Observation:
    indicator_id: str
    entity_slug: str
    period: Period
    value: float
    ci_low: float | None = None
    ci_high: float | None = None
    is_provisional: bool = False
    note: str | None = None


@dataclass
class Validation:
    hard: list[str] = field(default_factory=list)
    soft: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.hard

    def as_dict(self) -> dict[str, list[str]]:
        return {"hard": self.hard, "soft": self.soft}


def validate(
    observations: list[Observation],
    indicators: Mapping[str, Indicator],
    current_places: int,
    coverage_types: Iterable[str] = ("state", "ut"),
    entity_types: Mapping[str, str] | None = None,
) -> Validation:
    result = Validation()
    seen: Counter = Counter()
    for o in observations:
        indicator = indicators.get(o.indicator_id)
        if indicator is None:
            result.hard.append(f"unknown indicator {o.indicator_id!r}")
            continue
        if not math.isfinite(o.value):
            result.hard.append(f"{o.indicator_id} {o.entity_slug} {o.period.label}: value is not a number")
            continue
        if indicator.valid_min is not None and o.value < indicator.valid_min:
            result.hard.append(
                f"{o.indicator_id} {o.entity_slug} {o.period.label}: {o.value} below {indicator.valid_min}"
            )
        if indicator.valid_max is not None and o.value > indicator.valid_max:
            result.hard.append(
                f"{o.indicator_id} {o.entity_slug} {o.period.label}: {o.value} above {indicator.valid_max}"
            )
        seen[(o.indicator_id, o.entity_slug, o.period.start, o.period.end)] += 1
    result.hard += [f"duplicate observation {k}" for k, n in seen.items() if n > 1]

    if entity_types is not None and current_places:
        per_period: dict[tuple[str, str], set[str]] = defaultdict(set)
        for o in observations:
            if entity_types.get(o.entity_slug) in coverage_types:
                per_period[(o.indicator_id, o.period.label)].add(o.entity_slug)
        for (indicator_id, label), places in sorted(per_period.items()):
            if len(places) < MIN_COVERAGE * current_places:
                result.soft.append(f"{indicator_id} {label}: only {len(places)} states/UTs")
    return result


_LOAD = """
    with incoming as (
        select o.indicator_id, e.id as entity_id, o.period_start, o.period_end, o.period_label,
               o.period_type, o.value, o.ci_low, o.ci_high, o.is_provisional, o.note
        from unnest(cast(:indicators as text[]), cast(:slugs as text[]), cast(:starts as date[]),
                    cast(:ends as date[]), cast(:labels as text[]), cast(:period_types as text[]),
                    cast(:values_ as double precision[]), cast(:lows as double precision[]),
                    cast(:highs as double precision[]), cast(:provisional as boolean[]),
                    cast(:notes as text[]))
             as o(indicator_id, slug, period_start, period_end, period_label, period_type, value,
                  ci_low, ci_high, is_provisional, note)
        join entity e on e.slug = o.slug
    ),
    changed as (
        select i.*, (lo.value is not null) as is_revision
        from incoming i
        left join latest_observation lo
          on lo.indicator_id = i.indicator_id and lo.entity_id = i.entity_id
         and lo.period_start = i.period_start and lo.period_end = i.period_end
        where lo.value is null or abs(lo.value - i.value) > :tolerance
           or lo.is_provisional is distinct from i.is_provisional
    ),
    inserted as (
        insert into observation (indicator_id, entity_id, period_start, period_end, period_label,
                                 period_type, value, ci_low, ci_high, is_provisional, note, run_id)
        select indicator_id, entity_id, period_start, period_end, period_label, period_type, value,
               ci_low, ci_high, is_provisional, note, :run_id
        from changed
        returning 1
    )
    select (select count(*) from incoming), (select count(*) from changed where not is_revision),
           (select count(*) from changed where is_revision), (select count(*) from inserted)
"""


def load(conn: Connection, observations: list[Observation], run_id: int) -> dict[str, int]:
    """Insert new and revised values as vintage ``run_id``. Returns counts."""
    if not observations:
        return {"received": 0, "new": 0, "revised": 0, "unchanged": 0}
    with transaction(conn):
        received, new, revised, _ = conn.run(
            _LOAD,
            indicators=[o.indicator_id for o in observations],
            slugs=[o.entity_slug for o in observations],
            starts=[o.period.start for o in observations],
            ends=[o.period.end for o in observations],
            labels=[o.period.label for o in observations],
            period_types=[o.period.type for o in observations],
            values_=[float(o.value) for o in observations],
            lows=[o.ci_low for o in observations],
            highs=[o.ci_high for o in observations],
            provisional=[o.is_provisional for o in observations],
            notes=[o.note for o in observations],
            tolerance=REVISION_TOLERANCE,
            run_id=run_id,
        )[0]
        if received != len(observations):  # rolls back: an entity slug unknown to the database
            raise ValueError(
                f"{len(observations) - received} observations name entities missing from the database"
            )
    return {"received": received, "new": new, "revised": revised, "unchanged": received - new - revised}


def count_for_run(conn: Connection, run_id: int) -> int:
    return scalar(conn, "select count(*) from observation where run_id = :id", id=run_id)
