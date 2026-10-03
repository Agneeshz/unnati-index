-- migrate:up

-- ---------------------------------------------------------------------------
-- Geography
-- ---------------------------------------------------------------------------

-- Countries, states, UTs, cities and districts. Boundary changes (AP/Telangana
-- 2014, J&K/Ladakh 2019, DNH + DD 2020) are modelled as separate entities with
-- validity dates, so time series show a break instead of fake continuity.
create table entity (
    id              integer generated always as identity primary key,
    slug            text not null unique,
    name            text not null,
    name_hi         text,
    type            text not null check (type in ('country', 'state', 'ut', 'city', 'district')),
    lgd_code        integer,
    census2011_code text,
    parent_id       integer references entity (id),
    peer_group      text check (peer_group in (
                        'large_state', 'ne_himalayan_state', 'ut',
                        'city_million_plus', 'city_other')),
    valid_from      date,
    valid_to        date,
    wikidata_qid    text,
    check (valid_to is null or valid_from is null or valid_to > valid_from)
);

-- LGD codes are unique among *current* entities of a type (historic entities may reuse them).
create unique index entity_current_lgd_idx on entity (type, lgd_code)
    where lgd_code is not null and valid_to is null;

create table entity_lineage (
    predecessor_id integer not null references entity (id),
    successor_id   integer not null references entity (id),
    event_date     date not null,
    kind           text not null check (kind in ('split', 'merge', 'reorganisation', 'rename')),
    note           text,
    primary key (predecessor_id, successor_id)
);

-- Alternative spellings used by sources ("Orissa", "NCT of Delhi", "A & N Islands").
-- period_from/period_to scope an alias to the *data period* it applies to, e.g.
-- "Andhra Pradesh" means the undivided state for periods before 2 June 2014.
create table entity_alias (
    id          integer generated always as identity primary key,
    alias_norm  text not null,
    entity_id   integer not null references entity (id),
    period_from date,
    period_to   date
);

create index entity_alias_norm_idx on entity_alias (alias_norm);

-- ---------------------------------------------------------------------------
-- Sources and datasets (synced from pipeline/unnati/registry.yaml)
-- ---------------------------------------------------------------------------

create table source (
    id          text primary key,
    name        text not null,
    publisher   text not null,
    url         text not null,
    license     text not null,
    attribution text not null
);

create table dataset (
    id               text primary key,
    source_id        text not null references source (id),
    title            text not null,
    connector        text not null,
    cadence          text not null check (cadence in (
                         'hourly', 'daily', 'weekly', 'monthly', 'quarterly',
                         'annual', 'biennial', 'irregular')),
    landing_url      text,
    status           text not null default 'active' check (status in ('active', 'paused', 'broken')),
    last_checked_at  timestamptz,
    last_changed_at  timestamptz,
    last_fingerprint text,
    next_expected    date,
    notes            text
);

-- ---------------------------------------------------------------------------
-- Taxonomy: categories (for browsing), pillars (for the composite), indicators
-- ---------------------------------------------------------------------------

create table category (
    id          text primary key,
    name        text not null,
    name_hi     text,
    description text,
    sort        smallint not null,
    ranked      boolean not null default true
);

create table pillar (
    id          text primary key,
    name        text not null,
    name_hi     text,
    description text,
    sort        smallint not null
);

create table indicator (
    id          text primary key,
    name        text not null,
    name_hi     text,
    description text not null,
    unit        text not null,
    direction   text not null check (direction in ('higher_better', 'lower_better', 'neutral')),
    category_id text not null references category (id),
    dataset_id  text references dataset (id),
    frequency   text not null,
    decimals    smallint not null default 1,
    rankable    boolean not null default true,
    is_derived  boolean not null default false,
    formula     text,
    caveat      text,
    sdg_target  double precision,
    valid_min   double precision,
    valid_max   double precision
);

-- ---------------------------------------------------------------------------
-- Ingestion runs (each successful load is a "vintage") and observations
-- ---------------------------------------------------------------------------

create table ingestion_run (
    id          bigint generated always as identity primary key,
    dataset_id  text not null references dataset (id),
    trigger     text not null check (trigger in ('schedule', 'manual', 'backfill')),
    status      text not null check (status in ('running', 'unchanged', 'loaded', 'failed', 'rejected')),
    started_at  timestamptz not null default now(),
    finished_at timestamptz,
    fingerprint text,
    source_url  text,
    raw_sha256  text,
    raw_uri     text,
    rows_loaded integer,
    validation  jsonb,
    error       text,
    git_sha     text
);

create index ingestion_run_dataset_idx on ingestion_run (dataset_id, started_at desc);

-- A new row is written only when a value is new or revised, so every government
-- revision is preserved without duplicating unchanged values on each refresh.
create table observation (
    indicator_id   text not null references indicator (id),
    entity_id      integer not null references entity (id),
    period_start   date not null,
    period_end     date not null,
    period_label   text not null,
    period_type    text not null check (period_type in (
                       'day', 'month', 'quarter', 'fiscal_year', 'calendar_year',
                       'survey_round', 'multi_year')),
    value          double precision not null,
    ci_low         double precision,
    ci_high        double precision,
    is_provisional boolean not null default false,
    note           text,
    run_id         bigint not null references ingestion_run (id),
    primary key (indicator_id, entity_id, period_start, period_end, run_id),
    check (period_end >= period_start)
);

create index observation_entity_idx on observation (entity_id, indicator_id);

create view latest_observation as
select distinct on (indicator_id, entity_id, period_start, period_end) *
from observation
order by indicator_id, entity_id, period_start, period_end, run_id desc;

-- ---------------------------------------------------------------------------
-- Methodology (versioned) and scores
-- ---------------------------------------------------------------------------

create table methodology (
    version      text primary key,
    published_on date not null,
    is_current   boolean not null default false,
    notes        text
);

create unique index methodology_one_current_idx on methodology (is_current) where is_current;

-- Which indicators feed which pillar, with fixed goalposts, per methodology version.
create table methodology_indicator (
    version      text not null references methodology (version),
    indicator_id text not null references indicator (id),
    pillar_id    text not null references pillar (id),
    weight       double precision not null default 1 check (weight > 0),
    goal_worst   double precision not null,
    goal_best    double precision not null,
    primary key (version, indicator_id),
    check (goal_worst <> goal_best)
);

create table score (
    methodology_version text not null references methodology (version),
    edition             smallint not null,
    entity_id           integer not null references entity (id),
    level               text not null check (level in ('indicator', 'pillar', 'composite')),
    key                 text not null,
    score               double precision check (score between 0 and 100),
    coverage            double precision check (coverage between 0 and 1),
    rank_overall        smallint,
    rank_peer           smallint,
    rank_overall_prev   smallint,
    rank_peer_prev      smallint,
    data_period_label   text,
    computed_at         timestamptz not null default now(),
    primary key (methodology_version, edition, entity_id, level, key)
);

-- ---------------------------------------------------------------------------
-- Live feeds (e.g. hourly AQI). Raw readings are kept ~30 days and rolled up
-- into daily observations to stay within the free database tier.
-- ---------------------------------------------------------------------------

create table live_station (
    id        text primary key,
    name      text not null,
    city      text,
    entity_id integer references entity (id),
    latitude  double precision,
    longitude double precision,
    source_id text not null references source (id)
);

create table live_reading (
    station_id  text not null references live_station (id),
    metric      text not null,
    observed_at timestamptz not null,
    value       double precision not null,
    primary key (station_id, metric, observed_at)
);

create index live_reading_time_idx on live_reading (observed_at desc);

-- "NCRB Crime in India 2024 added" etc. Feeds the homepage, RSS and /sources.
create table release_event (
    id          bigint generated always as identity primary key,
    dataset_id  text not null references dataset (id),
    run_id      bigint references ingestion_run (id),
    happened_at timestamptz not null default now(),
    title       text not null,
    summary     text,
    indicators  text[] not null default '{}',
    periods     text[] not null default '{}'
);

create index release_event_time_idx on release_event (happened_at desc);

-- ---------------------------------------------------------------------------
-- Leadership & accountability: politicians and bureaucrats per entity.
-- Office-holders are always shown for the period a number describes.
-- ---------------------------------------------------------------------------

create table party (
    id           text primary key,
    name         text not null,
    abbreviation text,
    wikidata_qid text unique
);

create table person (
    id           integer generated always as identity primary key,
    name         text not null,
    name_hi      text,
    wikidata_qid text unique,
    myneta_url   text,
    official_url text
);

create table office (
    id                    integer generated always as identity primary key,
    entity_id             integer not null references entity (id),
    office_type           text not null check (office_type in (
                              'prime_minister', 'union_minister',
                              'governor', 'lieutenant_governor', 'administrator',
                              'chief_minister', 'deputy_chief_minister', 'minister',
                              'chief_secretary', 'dgp', 'secretary', 'hc_chief_justice',
                              'mayor', 'municipal_commissioner', 'police_commissioner',
                              'district_collector', 'superintendent_of_police',
                              'mp', 'mla')),
    title                 text not null,
    portfolio             text,
    is_political          boolean not null,
    wikidata_position_qid text,
    unique (entity_id, office_type, title)
);

-- Which categories an office is accountable for (e.g. Health Minister -> health).
create table office_category (
    office_id   integer not null references office (id),
    category_id text not null references category (id),
    primary key (office_id, category_id)
);

create table office_term (
    id          integer generated always as identity primary key,
    office_id   integer not null references office (id),
    person_id   integer not null references person (id),
    start_date  date not null,
    end_date    date,
    party_id    text references party (id),
    is_acting   boolean not null default false,
    source_type text not null check (source_type in ('wikidata', 'curated', 'official')),
    source_url  text not null,
    verified_at date not null,
    note        text,
    check (end_date is null or end_date >= start_date)
);

create index office_term_office_idx on office_term (office_id, start_date);

-- Office-holders whose tenure overlaps a data period [p_start, p_end].
create function office_holders_during(p_entity_id integer, p_start date, p_end date)
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

-- migrate:down

drop function office_holders_during(integer, date, date);
drop table office_term;
drop table office_category;
drop table office;
drop table person;
drop table party;
drop table release_event;
drop table live_reading;
drop table live_station;
drop table score;
drop table methodology_indicator;
drop table methodology;
drop view latest_observation;
drop table observation;
drop table ingestion_run;
drop table indicator;
drop table pillar;
drop table category;
drop table dataset;
drop table source;
drop table entity_alias;
drop table entity_lineage;
drop table entity;
