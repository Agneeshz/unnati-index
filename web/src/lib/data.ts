import "server-only";
import { neon } from "@neondatabase/serverless";
import { cacheLife, cacheTag } from "next/cache";
import { locale as rootLocale } from "next/root-params";

/**
 * Read-only queries for the site. Every function is cached and tagged; the pipeline calls
 * POST /api/revalidate with these tags ("scores", "observations", "officials") after it loads
 * new data, so pages regenerate only when the numbers change.
 */

function sql() {
  const url = process.env.DATABASE_URL_READONLY ?? process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL (or DATABASE_URL_READONLY) is not set");
  return neon(url);
}

export const COMPOSITE = "unnati-index";
export const METHODOLOGY = "1.1";

export type PeerGroup = "large_state" | "ne_himalayan_state" | "ut";

export type Place = {
  slug: string;
  name: string;
  nameHi: string | null;
  type: "state" | "ut" | "country";
  peerGroup: PeerGroup | null;
};

export type ScoreRow = {
  slug: string;
  level: "indicator" | "pillar" | "composite";
  key: string;
  score: number | null;
  coverage: number | null;
  rank: number | null;
  rankPeer: number | null;
  rankPrev: number | null;
  rankPeerPrev: number | null;
  periodLabel: string | null;
};

export type Indicator = {
  id: string;
  name: string;
  description: string;
  unit: string;
  direction: "higher_better" | "lower_better" | "neutral";
  categoryId: string;
  pillarId: string | null;
  decimals: number;
  caveat: string | null;
  rankable: boolean;
};

export type Observation = {
  slug: string;
  indicatorId: string;
  start: string;
  end: string;
  label: string;
  value: number;
  ciLow: number | null;
  ciHigh: number | null;
  provisional: boolean;
  note: string | null;
};

export type Pillar = { id: string; name: string; description: string };

export type OfficeHolder = {
  officeType: string;
  title: string;
  isPolitical: boolean;
  person: string;
  party: string | null;
  start: string;
  end: string | null;
  sourceUrl: string;
};

const iso = (d: unknown) => (d instanceof Date ? d.toISOString().slice(0, 10) : String(d));

export async function getPlaces(): Promise<Place[]> {
  "use cache";
  cacheTag("places");
  cacheLife("max");
  const rows = await sql()`
    select slug, name, name_hi, type, peer_group from entity
    where type in ('state', 'ut', 'country') and valid_to is null
    order by name`;
  return rows.map((r) => ({
    slug: r.slug,
    name: r.name,
    nameHi: r.name_hi,
    type: r.type,
    peerGroup: r.peer_group,
  }));
}

export async function getPillars(): Promise<Pillar[]> {
  "use cache";
  cacheTag("places");
  cacheLife("max");
  const rows = await sql()`select id, name, description from pillar order by sort, id`;
  return rows.map((r) => ({ id: r.id, name: r.name, description: r.description }));
}

export type TextLocale = "en" | "hi";

/**
 * The language for data text (indicator names, units, index descriptions). Pages pass nothing and
 * get their route's locale; places without one (route handlers, static params) get English.
 */
async function textLocale(requested?: string): Promise<TextLocale> {
  if (requested) return requested === "hi" ? "hi" : "en";
  try {
    return (await rootLocale()) === "hi" ? "hi" : "en";
  } catch {
    return "en";
  }
}

export async function getCategories(locale?: string): Promise<{ id: string; name: string; ranked: boolean }[]> {
  return categoriesIn(await textLocale(locale));
}

async function categoriesIn(locale: TextLocale) {
  "use cache";
  cacheTag("places");
  cacheLife("max");
  const hi = locale === "hi";
  const rows = await sql()`
    select id, case when ${hi} then coalesce(name_hi, name) else name end as name, ranked
    from category order by sort, id`;
  return rows.map((r) => ({ id: r.id as string, name: r.name as string, ranked: r.ranked as boolean }));
}

export async function getIndicators(locale?: string): Promise<Indicator[]> {
  return indicatorsIn(await textLocale(locale));
}

async function indicatorsIn(locale: TextLocale): Promise<Indicator[]> {
  "use cache";
  cacheTag("places");
  cacheLife("max");
  const hi = locale === "hi";
  // Hindi text falls back to English column by column.
  const rows = await sql()`
    select i.id,
           case when ${hi} then coalesce(i.name_hi, i.name) else i.name end as name,
           case when ${hi} then coalesce(i.description_hi, i.description) else i.description end as description,
           case when ${hi} then coalesce(i.unit_hi, i.unit) else i.unit end as unit,
           i.direction, i.category_id, i.decimals,
           case when ${hi} then coalesce(i.caveat_hi, i.caveat) else i.caveat end as caveat,
           i.rankable, mi.pillar_id
    from indicator i
    left join methodology_indicator mi on mi.indicator_id = i.id and mi.version = ${METHODOLOGY}
    order by i.category_id, i.name`;
  return rows.map((r) => ({
    id: r.id,
    name: r.name,
    description: r.description,
    unit: r.unit,
    direction: r.direction,
    categoryId: r.category_id,
    pillarId: r.pillar_id,
    decimals: r.decimals,
    caveat: r.caveat,
    rankable: r.rankable,
  }));
}

/** Latest edition number that has scores. */
export async function getLatestEdition(): Promise<number | null> {
  "use cache";
  cacheTag("scores");
  cacheLife("days");
  const rows = await sql()`select max(edition) as e from score where methodology_version = ${METHODOLOGY}`;
  return rows[0]?.e ?? null;
}

export async function getScores(edition: number, level?: ScoreRow["level"]): Promise<ScoreRow[]> {
  "use cache";
  cacheTag("scores");
  cacheLife("days");
  const rows = await sql()`
    select e.slug, s.level, s.key, s.score, s.coverage, s.rank_overall, s.rank_peer,
           s.rank_overall_prev, s.rank_peer_prev, s.data_period_label
    from score s join entity e on e.id = s.entity_id
    where s.methodology_version = ${METHODOLOGY} and s.edition = ${edition}
      and (${level ?? null}::text is null or s.level = ${level ?? null})`;
  return rows.map((r) => ({
    slug: r.slug,
    level: r.level,
    key: r.key,
    score: r.score,
    coverage: r.coverage,
    rank: r.rank_overall,
    rankPeer: r.rank_peer,
    rankPrev: r.rank_overall_prev,
    rankPeerPrev: r.rank_peer_prev,
    periodLabel: r.data_period_label,
  }));
}

/** Composite scores for every edition (for "most improved"). */
export async function getCompositeHistory(): Promise<{ slug: string; edition: number; score: number }[]> {
  "use cache";
  cacheTag("scores");
  cacheLife("days");
  const rows = await sql()`
    select e.slug, s.edition, s.score
    from score s join entity e on e.id = s.entity_id
    where s.methodology_version = ${METHODOLOGY} and s.level = 'composite' and s.score is not null
    order by s.edition`;
  return rows.map((r) => ({ slug: r.slug, edition: r.edition, score: r.score }));
}

/** One place's composite and pillar scores in every edition. */
export async function getPlaceScoreHistory(
  slug: string,
): Promise<{ edition: number; key: string; level: string; score: number | null }[]> {
  "use cache";
  cacheTag("scores", `state:${slug}`);
  cacheLife("days");
  const rows = await sql()`
    select s.edition, s.key, s.level, s.score
    from score s join entity e on e.id = s.entity_id
    where e.slug = ${slug} and s.methodology_version = ${METHODOLOGY} and s.level in ('pillar', 'composite')
    order by s.edition`;
  return rows.map((r) => ({ edition: r.edition, key: r.key, level: r.level, score: r.score }));
}

function toObservation(r: Record<string, unknown>): Observation {
  return {
    slug: r.slug as string,
    indicatorId: r.indicator_id as string,
    start: iso(r.period_start),
    end: iso(r.period_end),
    label: r.period_label as string,
    value: r.value as number,
    ciLow: (r.ci_low as number | null) ?? null,
    ciHigh: (r.ci_high as number | null) ?? null,
    provisional: Boolean(r.is_provisional),
    note: (r.note as string | null) ?? null,
  };
}

/** Every value for one indicator (all places, all periods). */
export async function getIndicatorObservations(indicatorId: string): Promise<Observation[]> {
  "use cache";
  cacheTag("observations", `indicator:${indicatorId}`);
  cacheLife("days");
  const rows = await sql()`
    select e.slug, o.indicator_id, o.period_start, o.period_end, o.period_label, o.value,
           o.ci_low, o.ci_high, o.is_provisional, o.note
    from latest_observation o join entity e on e.id = o.entity_id
    where o.indicator_id = ${indicatorId}
    order by o.period_end`;
  return rows.map(toObservation);
}

/** Every value for one place (all indicators, all periods). */
export async function getPlaceObservations(slug: string): Promise<Observation[]> {
  "use cache";
  cacheTag("observations", `state:${slug}`);
  cacheLife("days");
  const rows = await sql()`
    select e.slug, o.indicator_id, o.period_start, o.period_end, o.period_label, o.value,
           o.ci_low, o.ci_high, o.is_provisional, o.note
    from latest_observation o join entity e on e.id = o.entity_id
    where e.slug = ${slug}
    order by o.period_end`;
  return rows.map(toObservation);
}

/** Office-holders whose tenure overlapped [start, end]. */
export async function getOfficeHolders(slug: string, start: string, end: string): Promise<OfficeHolder[]> {
  "use cache";
  cacheTag("officials", `state:${slug}`);
  cacheLife("days");
  const rows = await sql()`
    select h.office_type, h.title, h.is_political, h.person_name, p.name as party,
           h.start_date, h.end_date, h.source_url
    from entity e
    cross join lateral office_holders_during(e.id, ${start}::date, ${end}::date) h
    left join party p on p.id = h.party_id
    where e.slug = ${slug}
    order by h.start_date desc`;
  return rows.map((r) => ({
    officeType: r.office_type,
    title: r.title,
    isPolitical: r.is_political,
    person: r.person_name,
    party: r.is_political ? r.party : null,
    start: iso(r.start_date),
    end: r.end_date ? iso(r.end_date) : null,
    sourceUrl: r.source_url,
  }));
}

export async function getGoalposts(): Promise<{ indicatorId: string; pillarId: string; worst: number; best: number }[]> {
  "use cache";
  cacheTag("scores");
  cacheLife("days");
  const rows = await sql()`
    select indicator_id, pillar_id, goal_worst, goal_best from methodology_indicator
    where version = ${METHODOLOGY} order by pillar_id, indicator_id`;
  return rows.map((r) => ({
    indicatorId: r.indicator_id,
    pillarId: r.pillar_id,
    worst: r.goal_worst,
    best: r.goal_best,
  }));
}

export type ThematicIndex = {
  id: string;
  name: string;
  description: string;
  method: string;
  caveat: string | null;
  inspiredBy: string | null;
  components: { dimension: string; indicators: string[] }[];
};

export async function getIndices(locale?: string): Promise<ThematicIndex[]> {
  return indicesIn(await textLocale(locale));
}

async function indicesIn(locale: TextLocale): Promise<ThematicIndex[]> {
  "use cache";
  cacheTag("places");
  cacheLife("max");
  const rows = await sql()`
    select id, name, name_hi, description, description_hi, method, method_hi, caveat, caveat_hi,
           inspired_by, inspired_by_hi, components, dimensions_hi
    from index_definition order by sort`;
  const hi = locale === "hi";
  const pick = (en: string | null, translated: string | null) => (hi && translated ? translated : en);
  return rows.map((r) => ({
    id: r.id,
    name: pick(r.name, r.name_hi) as string,
    description: pick(r.description, r.description_hi) as string,
    method: pick(r.method, r.method_hi) as string,
    caveat: pick(r.caveat, r.caveat_hi),
    inspiredBy: pick(r.inspired_by, r.inspired_by_hi),
    components: (r.components as ThematicIndex["components"]).map((c) => ({
      dimension: (hi && r.dimensions_hi?.[c.dimension]) || c.dimension,
      indicators: c.indicators,
    })),
  }));
}

export type DatasetStatus = {
  id: string;
  title: string;
  source: string;
  cadence: string;
  lastChecked: string | null;
  lastChanged: string | null;
  landingUrl: string | null;
};

export async function getDatasets(): Promise<DatasetStatus[]> {
  "use cache";
  cacheTag("observations");
  cacheLife("hours");
  const rows = await sql()`
    select d.id, d.title, s.name as source, d.cadence, d.last_checked_at, d.last_changed_at, d.landing_url
    from dataset d join source s on s.id = d.source_id
    where d.status <> 'paused'
    order by d.last_changed_at desc nulls last`;
  return rows.map((r) => ({
    id: r.id,
    title: r.title,
    source: r.source,
    cadence: r.cadence,
    lastChecked: r.last_checked_at ? new Date(r.last_checked_at).toISOString() : null,
    lastChanged: r.last_changed_at ? new Date(r.last_changed_at).toISOString() : null,
    landingUrl: r.landing_url,
  }));
}

export type ReleaseEvent = {
  id: number;
  datasetId: string;
  happenedAt: string;
  title: string;
  source: string;
  summary: string | null;
  indicators: string[];
  periods: string[];
  sourceUrl: string | null;
};

/** Data releases loaded by the pipeline, newest first (the updates page, RSS and home page). */
export async function getReleases(limit = 100): Promise<ReleaseEvent[]> {
  "use cache";
  cacheTag("observations");
  cacheLife("hours");
  const rows = await sql()`
    select e.id, e.dataset_id, e.happened_at, e.title, s.name as source, e.summary, e.indicators, e.periods,
           r.source_url
    from release_event e
    join dataset d on d.id = e.dataset_id
    join source s on s.id = d.source_id
    left join ingestion_run r on r.id = e.run_id
    order by e.happened_at desc
    limit ${limit}`;
  return rows.map((r) => ({
    id: Number(r.id),
    datasetId: r.dataset_id,
    happenedAt: new Date(r.happened_at).toISOString(),
    title: r.title,
    source: r.source,
    summary: r.summary,
    indicators: r.indicators,
    periods: r.periods,
    sourceUrl: r.source_url,
  }));
}

export type City = {
  slug: string;
  name: string;
  nameHi: string | null;
  stateSlug: string;
  latitude: number;
  longitude: number;
  population: number | null; // Census 2011
  millionPlus: boolean;
};

/** The city roster (Census 2011 cities over 4 lakh, plus state capitals), largest first. */
export async function getCities(): Promise<City[]> {
  "use cache";
  cacheTag("places");
  cacheLife("max");
  const rows = await sql()`
    select c.slug, c.name, c.name_hi, s.slug as state_slug, c.latitude, c.longitude, c.population_2011,
           c.peer_group
    from entity c join entity s on s.id = c.parent_id
    where c.type = 'city' and c.valid_to is null
    order by c.population_2011 desc nulls last, c.name`;
  return rows.map((r) => ({
    slug: r.slug,
    name: r.name,
    nameHi: r.name_hi,
    stateSlug: r.state_slug,
    latitude: r.latitude,
    longitude: r.longitude,
    population: r.population_2011,
    millionPlus: r.peer_group === "city_million_plus",
  }));
}

/** Every city value for the given indicators (all periods), for the cities overview. */
export async function getCityObservations(indicatorIds: string[]): Promise<Observation[]> {
  "use cache";
  cacheTag("observations");
  cacheLife("hours");
  const rows = await sql()`
    select e.slug, o.indicator_id, o.period_start, o.period_end, o.period_label, o.value,
           o.ci_low, o.ci_high, o.is_provisional, o.note
    from latest_observation o join entity e on e.id = o.entity_id
    where e.type = 'city' and o.indicator_id = any(${indicatorIds})
    order by o.period_end`;
  return rows.map(toObservation);
}

export type SearchPlace = {
  slug: string;
  name: string;
  nameHi: string | null;
  type: "state" | "ut" | "city";
  stateSlug: string | null; // a city's state
  aliases: string[]; // normalised other names (Orissa, Gurgaon, Bangalore...)
};

/** Current states, UTs and cities with every other name they go by, for the site search. */
export async function getSearchPlaces(): Promise<SearchPlace[]> {
  "use cache";
  cacheTag("places");
  cacheLife("max");
  const rows = await sql()`
    select e.slug, e.name, e.name_hi, e.type, p.slug as parent_slug,
           coalesce(array_agg(distinct a.alias_norm) filter (where a.alias_norm is not null), '{}') as aliases
    from entity e
    left join entity p on p.id = e.parent_id
    left join entity_alias a on a.entity_id = e.id
    where e.type in ('state', 'ut', 'city') and e.valid_to is null
    group by e.slug, e.name, e.name_hi, e.type, p.slug`;
  return rows.map((r) => ({
    slug: r.slug,
    name: r.name,
    nameHi: r.name_hi,
    type: r.type,
    stateSlug: r.type === "city" ? r.parent_slug : null,
    aliases: r.aliases,
  }));
}
