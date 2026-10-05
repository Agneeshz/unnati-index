"""Sync the reference data (entities, aliases, taxonomy, registry) into the database.

Idempotent: rows are upserted by their natural keys, so it is safe to run on every deploy.
Aliases and lineage are derived data and are replaced wholesale. Nothing is deleted from the
core tables, because observations and scores may still reference retired rows."""

from __future__ import annotations

import json

from unnati.core.entities import normalize_name
from unnati.db import Connection, transaction
from unnati.reference import ReferenceData

_UPSERT_ENTITY = """
    insert into entity (slug, name, name_hi, type, lgd_code, census2011_code,
                        peer_group, valid_from, valid_to, wikidata_qid)
    values (:slug, :name, :name_hi, :type, :lgd_code, :census2011_code,
            :peer_group, :valid_from, :valid_to, :wikidata_qid)
    on conflict (slug) do update set
        name = excluded.name, name_hi = excluded.name_hi, type = excluded.type,
        lgd_code = excluded.lgd_code, census2011_code = excluded.census2011_code,
        peer_group = excluded.peer_group, valid_from = excluded.valid_from,
        valid_to = excluded.valid_to, wikidata_qid = excluded.wikidata_qid
"""

_SET_PARENT = """
    update entity set parent_id = (select id from entity p where p.slug = :parent_slug)
    where slug = :slug
"""

_INSERT_LINEAGE = """
    insert into entity_lineage (predecessor_id, successor_id, event_date, kind, note)
    select a.id, b.id, :event_date, :kind, :note from entity a, entity b
    where a.slug = :predecessor_slug and b.slug = :successor_slug
"""

_INSERT_ALIAS = """
    insert into entity_alias (alias_norm, entity_id, period_from, period_to)
    select :alias_norm, id, :period_from, :period_to from entity where slug = :entity_slug
"""

_UPSERT_SOURCE = """
    insert into source (id, name, publisher, url, license, attribution)
    values (:id, :name, :publisher, :url, :license, :attribution)
    on conflict (id) do update set
        name = excluded.name, publisher = excluded.publisher, url = excluded.url,
        license = excluded.license, attribution = excluded.attribution
"""

# A dataset the freshness monitor marked "broken" stays broken until its connector is fixed.
_UPSERT_DATASET = """
    insert into dataset (id, source_id, title, connector, cadence, landing_url, status)
    values (:id, :source, :title, :connector, :cadence, :landing_url, :status)
    on conflict (id) do update set
        source_id = excluded.source_id, title = excluded.title, connector = excluded.connector,
        cadence = excluded.cadence, landing_url = excluded.landing_url,
        status = case
            when excluded.status = 'paused' then 'paused'
            when dataset.status = 'broken' then 'broken'
            else excluded.status
        end
"""

_UPSERT_CATEGORY = """
    insert into category (id, name, name_hi, description, sort, ranked)
    values (:id, :name, :name_hi, :description, :sort, :ranked)
    on conflict (id) do update set
        name = excluded.name, name_hi = excluded.name_hi, description = excluded.description,
        sort = excluded.sort, ranked = excluded.ranked
"""

_UPSERT_PILLAR = """
    insert into pillar (id, name, name_hi, description, sort)
    values (:id, :name, :name_hi, :description, :sort)
    on conflict (id) do update set
        name = excluded.name, name_hi = excluded.name_hi, description = excluded.description,
        sort = excluded.sort
"""

_UPSERT_INDICATOR = """
    insert into indicator (id, name, name_hi, description, unit, direction, category_id,
                           dataset_id, frequency, decimals, rankable, is_derived, formula,
                           caveat, sdg_target, valid_min, valid_max)
    values (:id, :name, :name_hi, :description, :unit, :direction, :category,
            :dataset, :frequency, :decimals, :rankable, :is_derived, :derived,
            :caveat, :target, :valid_min, :valid_max)
    on conflict (id) do update set
        name = excluded.name, name_hi = excluded.name_hi, description = excluded.description,
        unit = excluded.unit, direction = excluded.direction, category_id = excluded.category_id,
        dataset_id = excluded.dataset_id, frequency = excluded.frequency,
        decimals = excluded.decimals, rankable = excluded.rankable,
        is_derived = excluded.is_derived, formula = excluded.formula, caveat = excluded.caveat,
        sdg_target = excluded.sdg_target, valid_min = excluded.valid_min,
        valid_max = excluded.valid_max
"""


_UPSERT_INDEX = """
    insert into index_definition
        (id, name, name_hi, description, method, caveat, inspired_by, components, sort)
    values (:id, :name, :name_hi, :description, :method, :caveat, :inspired_by,
            cast(:components as jsonb), :sort)
    on conflict (id) do update set
        name = excluded.name, name_hi = excluded.name_hi, description = excluded.description,
        method = excluded.method, caveat = excluded.caveat, inspired_by = excluded.inspired_by,
        components = excluded.components, sort = excluded.sort
"""

_INDICATOR_HI = """
    update indicator set name_hi = :name, description_hi = :description, caveat_hi = :caveat
    where id = :id
"""

_INDEX_HI = """
    update index_definition set name_hi = :name, description_hi = :description, method_hi = :method,
        caveat_hi = :caveat, inspired_by_hi = :inspired_by, dimensions_hi = cast(:dimensions as jsonb)
    where id = :id
"""


def _seed_hindi(conn: Connection, ref: ReferenceData) -> None:
    hi = ref.hindi
    conn.run("update indicator set name_hi = null, description_hi = null, caveat_hi = null, unit_hi = null")
    for key, text in hi.indicators.items():
        conn.run(_INDICATOR_HI, id=key, **text.model_dump())
    for unit, text in hi.units.items():
        conn.run("update indicator set unit_hi = :hi where unit = :unit", unit=unit, hi=text)
    for key, text in hi.indices.items():
        conn.run(
            _INDEX_HI,
            id=key,
            **text.model_dump(exclude={"dimensions"}),
            dimensions=json.dumps(text.dimensions, ensure_ascii=False),
        )


def seed(conn: Connection, ref: ReferenceData) -> dict[str, int]:
    with transaction(conn):
        for e in ref.entities:
            conn.run(_UPSERT_ENTITY, **e.model_dump(exclude={"parent_slug"}))
        for e in ref.entities:
            if e.parent_slug:
                conn.run(_SET_PARENT, slug=e.slug, parent_slug=e.parent_slug)

        conn.run("delete from entity_lineage")
        for row in ref.lineage:
            conn.run(_INSERT_LINEAGE, **row.model_dump())

        conn.run("delete from entity_alias")
        for a in ref.aliases:
            conn.run(
                _INSERT_ALIAS,
                alias_norm=normalize_name(a.alias),
                entity_slug=a.entity_slug,
                period_from=a.period_from,
                period_to=a.period_to,
            )

        for s in ref.registry.sources:
            conn.run(_UPSERT_SOURCE, **s.model_dump())
        for d in ref.registry.datasets:
            conn.run(
                _UPSERT_DATASET,
                **d.model_dump(exclude={"enabled"}),
                status="active" if d.enabled else "paused",
            )

        for sort, c in enumerate(ref.categories, 1):
            conn.run(_UPSERT_CATEGORY, **c.model_dump(), sort=sort)
        for sort, p in enumerate(ref.pillars, 1):
            conn.run(_UPSERT_PILLAR, **p.model_dump(), sort=sort)
        for i in ref.indicators:
            conn.run(
                _UPSERT_INDICATOR,
                **i.model_dump(exclude={"pillar", "scale"}),
                is_derived=i.derived is not None,
            )
        conn.run(
            "delete from index_definition where not (id = any(cast(:ids as text[])))",
            ids=[x.id for x in ref.indices],
        )
        for sort, x in enumerate(ref.indices, 1):
            conn.run(
                _UPSERT_INDEX,
                **x.model_dump(exclude={"kind", "components"}),
                # A list keeps the dimensions in their defined order (jsonb objects don't).
                components=json.dumps([{"dimension": k, "indicators": v} for k, v in x.components.items()]),
                sort=sort,
            )
        _seed_hindi(conn, ref)

    return {
        "entities": len(ref.entities),
        "lineage": len(ref.lineage),
        "aliases": len(ref.aliases),
        "sources": len(ref.registry.sources),
        "datasets": len(ref.registry.datasets),
        "categories": len(ref.categories),
        "pillars": len(ref.pillars),
        "indicators": len(ref.indicators),
    }
