"""Read observations, compute the Unnati Index for each edition, and store the scores.

Goalposts are written once per methodology version and reused afterwards, so an edition's
scores only move when the underlying numbers do. Editions run from FIRST_EDITION to the
current year; an edition's cut-off is 31 December of its year (today for the current one),
and rank changes compare with the previous edition."""

from __future__ import annotations

from datetime import date

from unnati import scoring
from unnati.db import Connection, transaction
from unnati.reference import load_reference

FIRST_EDITION = 2023


def specs() -> dict[str, scoring.IndicatorSpec]:
    """Pillar indicators, plus indicators used only by the thematic indices (no pillar)."""
    ref = load_reference()
    in_indices = {i for x in ref.indices for i in x.indicator_ids()}
    return {
        i.id: scoring.IndicatorSpec(i.id, i.pillar, i.direction, i.target, log=i.scale == "log")
        for i in ref.indicators
        if i.pillar or i.id in in_indices
    }


def indices() -> list[scoring.ThematicIndex]:
    return [scoring.ThematicIndex(x.id, x.kind, x.components) for x in load_reference().indices]


def peer_groups() -> dict[str, str]:
    return {
        e.slug: e.peer_group
        for e in load_reference().entities
        if e.type in ("state", "ut") and e.valid_to is None and e.peer_group
    }


def load_values(conn: Connection, indicator_ids: list[str]) -> list[scoring.Value]:
    rows = conn.run(
        """select o.indicator_id, e.slug, o.period_start, o.period_end, o.period_label, o.value
           from latest_observation o join entity e on e.id = o.entity_id
           where o.indicator_id = any(cast(:ids as text[]))""",
        ids=indicator_ids,
    )
    return [scoring.Value(*row) for row in rows]


def ensure_goalposts(
    conn: Connection, spec: dict[str, scoring.IndicatorSpec], values: list[scoring.Value], today: date
) -> dict[str, scoring.Goalpost]:
    """Stored goalposts for this version; any indicator without one gets it computed now."""
    version = scoring.METHODOLOGY_VERSION
    conn.run(
        """insert into methodology (version, published_on, is_current, notes)
           values (:v, :d, true, 'Unnati Index v1: fixed goalposts, 8 equal-weight pillars')
           on conflict (version) do nothing""",
        v=version,
        d=today,
    )
    stored = {
        row[0]: scoring.Goalpost(row[1], row[2])
        for row in conn.run(
            "select indicator_id, goal_worst, goal_best from methodology_indicator where version = :v",
            v=version,
        )
    }
    fresh = scoring.goalposts(values, {k: s for k, s in spec.items() if k not in stored})
    for indicator_id, post in fresh.items():
        conn.run(
            """insert into methodology_indicator
                   (version, indicator_id, pillar_id, weight, goal_worst, goal_best)
               values (:v, :i, :p, :w, :worst, :best)""",
            v=version,
            i=indicator_id,
            p=spec[indicator_id].pillar,
            w=spec[indicator_id].weight,
            worst=post.worst,
            best=post.best,
        )
    return {**stored, **fresh}


def compute(
    values: list[scoring.Value],
    spec: dict[str, scoring.IndicatorSpec],
    posts: dict[str, scoring.Goalpost],
    today: date,
) -> dict[int, list[scoring.Score]]:
    groups = peer_groups()
    editions = {}
    for edition in range(FIRST_EDITION, today.year + 1):
        cutoff = today if edition == today.year else date(edition, 12, 31)
        editions[edition] = scoring.score_edition(
            scoring.select(values, cutoff), spec, posts, groups, indices()
        )
    return editions


def run(conn: Connection, today: date) -> dict[int, list[scoring.Score]]:
    spec = specs()
    values = load_values(conn, list(spec))
    with transaction(conn):
        posts = ensure_goalposts(conn, spec, values, today)
        editions = compute(values, spec, posts, today)
        store(conn, editions)
    return editions


def store(conn: Connection, editions: dict[int, list[scoring.Score]]) -> None:
    version = scoring.METHODOLOGY_VERSION
    conn.run("delete from score where methodology_version = :v", v=version)
    for edition, scores in editions.items():
        previous = {
            (s.entity, s.level, s.key): (s.rank_overall, s.rank_peer) for s in editions.get(edition - 1, [])
        }
        rows = [(s, previous.get((s.entity, s.level, s.key), (None, None))) for s in scores]
        conn.run(
            """insert into score (methodology_version, edition, entity_id, level, key, score, coverage,
                                  rank_overall, rank_peer, rank_overall_prev, rank_peer_prev,
                                  data_period_label)
               select :v, :edition, e.id, s.level, s.key, s.score, s.coverage,
                      s.r, s.rp, s.rprev, s.rpprev, s.label
               from unnest(cast(:slugs as text[]), cast(:levels as text[]), cast(:keys as text[]),
                           cast(:scores as double precision[]), cast(:coverages as double precision[]),
                           cast(:ranks as smallint[]), cast(:peer_ranks as smallint[]),
                           cast(:prev as smallint[]), cast(:peer_prev as smallint[]), cast(:labels as text[]))
                    as s(slug, level, key, score, coverage, r, rp, rprev, rpprev, label)
               join entity e on e.slug = s.slug""",
            v=version,
            edition=edition,
            slugs=[s.entity for s, _ in rows],
            levels=[s.level for s, _ in rows],
            keys=[s.key for s, _ in rows],
            scores=[s.score for s, _ in rows],
            coverages=[s.coverage for s, _ in rows],
            ranks=[s.rank_overall for s, _ in rows],
            peer_ranks=[s.rank_peer for s, _ in rows],
            prev=[p[0] for _, p in rows],
            peer_prev=[p[1] for _, p in rows],
            labels=[s.period_label for s, _ in rows],
        )
