-- migrate:up

-- Office terms are imported from Wikidata and curated files. Imports are keyed by a stable
-- external id (e.g. the Wikidata statement id) so re-running them updates rather than duplicates,
-- and a term that fails automatic checks is held for human review: the website shows only
-- terms where needs_review is false.
alter table office_term add column external_id text;
alter table office_term add column needs_review boolean not null default false;
alter table office_term add column review_note text;

create unique index office_term_external_id_idx on office_term (external_id) where external_id is not null;

-- Only reviewed terms are ever shown against data.
create or replace function office_holders_during(p_entity_id integer, p_start date, p_end date)
returns table (
    office_id    integer,
    office_type  text,
    title        text,
    portfolio    text,
    is_political boolean,
    person_id    integer,
    person_name  text,
    party_id     text,
    start_date   date,
    end_date     date,
    is_acting    boolean,
    source_url   text,
    verified_at  date
)
language sql stable as $$
    select o.id, o.office_type, o.title, o.portfolio, o.is_political,
           p.id, p.name, t.party_id, t.start_date, t.end_date, t.is_acting,
           t.source_url, t.verified_at
    from office o
    join office_term t on t.office_id = o.id
    join person p on p.id = t.person_id
    where o.entity_id = p_entity_id
      and not t.needs_review
      and t.start_date <= p_end
      and coalesce(t.end_date, 'infinity'::date) >= p_start
    order by o.office_type, t.start_date
$$;

-- migrate:down

create or replace function office_holders_during(p_entity_id integer, p_start date, p_end date)
returns table (
    office_id    integer,
    office_type  text,
    title        text,
    portfolio    text,
    is_political boolean,
    person_id    integer,
    person_name  text,
    party_id     text,
    start_date   date,
    end_date     date,
    is_acting    boolean,
    source_url   text,
    verified_at  date
)
language sql stable as $$
    select o.id, o.office_type, o.title, o.portfolio, o.is_political,
           p.id, p.name, t.party_id, t.start_date, t.end_date, t.is_acting,
           t.source_url, t.verified_at
    from office o
    join office_term t on t.office_id = o.id
    join person p on p.id = t.person_id
    where o.entity_id = p_entity_id
      and t.start_date <= p_end
      and coalesce(t.end_date, 'infinity'::date) >= p_start
    order by o.office_type, t.start_date
$$;

drop index office_term_external_id_idx;
alter table office_term drop column review_note;
alter table office_term drop column needs_review;
alter table office_term drop column external_id;
