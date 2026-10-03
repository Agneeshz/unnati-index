"""Load office-holders into the database (people, parties, offices, terms).

Idempotent: people are keyed by Wikidata QID, offices by (entity, type, title) and terms by
external id. Wikidata terms that disappear upstream (corrected or deleted statements) are
removed; curated terms are never touched by a Wikidata sync.

Each table is written with one set-based statement (arrays passed through ``unnest``), so a sync
costs a handful of round trips however many terms it carries."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from unnati.connectors.wikidata_officials import (
    HEAD_OF_GOVERNMENT,
    PARTY_OFFICES,
    PositionMapping,
    Term,
    categories_for,
)
from unnati.db import Connection, scalar, transaction

_UPSERT_PARTIES = """
    insert into party (id, name, wikidata_qid)
    select id, name, id from unnest(cast(:ids as text[]), cast(:names as text[])) as p(id, name)
    on conflict (id) do update set name = excluded.name
"""

_UPSERT_PEOPLE = """
    insert into person (name, name_hi, wikidata_qid)
    select * from unnest(cast(:names as text[]), cast(:names_hi as text[]), cast(:qids as text[]))
    on conflict (wikidata_qid) do update
        set name = excluded.name, name_hi = coalesce(excluded.name_hi, person.name_hi)
    returning wikidata_qid, id
"""

_UPSERT_OFFICES = """
    insert into office (entity_id, office_type, title, is_political, wikidata_position_qid)
    select e.id, o.office_type, o.title, o.is_political, o.position
    from unnest(cast(:slugs as text[]), cast(:office_types as text[]), cast(:titles as text[]),
                cast(:political as boolean[]), cast(:positions as text[]))
         as o(slug, office_type, title, is_political, position)
    join entity e on e.slug = o.slug
    on conflict (entity_id, office_type, title) do update
        set is_political = excluded.is_political,
            wikidata_position_qid = excluded.wikidata_position_qid
    returning id, (select slug from entity where id = office.entity_id), office_type, title
"""

# Two statements, not one: a data-modifying CTE and the outer insert see the same snapshot, so
# the insert would collide with the rows being deleted.
_CLEAR_OFFICE_CATEGORIES = """
    delete from office_category where office_id = any(cast(:offices as int[]))
"""

_INSERT_OFFICE_CATEGORIES = """
    insert into office_category (office_id, category_id)
    select * from unnest(cast(:offices as int[]), cast(:categories as text[]))
"""

_UPSERT_TERMS = """
    insert into office_term (office_id, person_id, start_date, end_date, party_id, source_type,
                             source_url, verified_at, external_id, needs_review, review_note)
    select t.office_id, t.person_id, t.start_date, t.end_date, t.party_id, 'wikidata',
           t.source_url, :verified, t.external_id, t.needs_review, t.review_note
    from unnest(cast(:offices as int[]), cast(:people as int[]), cast(:starts as date[]),
                cast(:ends as date[]), cast(:parties as text[]), cast(:urls as text[]),
                cast(:ids as text[]), cast(:review as boolean[]), cast(:notes as text[]))
         as t(office_id, person_id, start_date, end_date, party_id, source_url, external_id,
              needs_review, review_note)
    on conflict (external_id) where external_id is not null do update set
        office_id = excluded.office_id, person_id = excluded.person_id,
        start_date = excluded.start_date, end_date = excluded.end_date,
        party_id = excluded.party_id, source_url = excluded.source_url,
        verified_at = excluded.verified_at, needs_review = excluded.needs_review,
        review_note = excluded.review_note
"""

_REMOVE_VANISHED = """
    with gone as (
        delete from office_term
        where source_type = 'wikidata' and not (external_id = any(cast(:ids as text[])))
        returning 1)
    select count(*) from gone
"""


def load_wikidata_terms(
    conn: Connection,
    terms: list[Term],
    mappings: Iterable[PositionMapping],
    ranked_categories: list[str],
    verified_on: date,
) -> dict[str, int]:
    offices = list({(m.entity_slug, m.office_type, m.title): m for m in mappings}.values())
    parties = sorted({(t.party_qid, t.party_label or t.party_qid) for t in terms if t.party_qid})
    people = list({t.person_qid: t for t in terms}.values())
    with_head_of_government = {m.entity_slug for m in offices if m.office_type in HEAD_OF_GOVERNMENT}

    with transaction(conn):
        if parties:
            conn.run(_UPSERT_PARTIES, ids=[p[0] for p in parties], names=[p[1] for p in parties])

        person_ids = dict(
            conn.run(
                _UPSERT_PEOPLE,
                names=[p.person_name for p in people],
                names_hi=[p.person_name_hi for p in people],
                qids=[p.person_qid for p in people],
            )
        )

        office_ids = {
            (slug, office_type, title): office_id
            for office_id, slug, office_type, title in conn.run(
                _UPSERT_OFFICES,
                slugs=[m.entity_slug for m in offices],
                office_types=[m.office_type for m in offices],
                titles=[m.title for m in offices],
                political=[m.office_type in PARTY_OFFICES for m in offices],
                positions=[m.position_qid for m in offices],
            )
        }

        pairs = [
            (office_ids[(m.entity_slug, m.office_type, m.title)], category)
            for m in offices
            for category in categories_for(
                m.office_type, m.entity_slug, m.entity_slug in with_head_of_government, ranked_categories
            )
        ]
        conn.run(_CLEAR_OFFICE_CATEGORIES, offices=list(office_ids.values()))
        conn.run(
            _INSERT_OFFICE_CATEGORIES,
            offices=[p[0] for p in pairs],
            categories=[p[1] for p in pairs],
        )

        conn.run(
            _UPSERT_TERMS,
            verified=verified_on,
            offices=[office_ids[(t.entity_slug, t.office_type, t.title)] for t in terms],
            people=[person_ids[t.person_qid] for t in terms],
            starts=[t.start for t in terms],
            ends=[t.end for t in terms],
            parties=[t.party_qid for t in terms],
            urls=[t.source_url for t in terms],
            ids=[t.external_id for t in terms],
            review=[t.needs_review for t in terms],
            notes=[t.review_note for t in terms],
        )
        removed = scalar(conn, _REMOVE_VANISHED, ids=[t.external_id for t in terms])

    return {
        "parties": len(parties),
        "people": len(person_ids),
        "offices": len(office_ids),
        "terms": len(terms),
        "needs_review": sum(t.needs_review for t in terms),
        "removed": removed,
    }
