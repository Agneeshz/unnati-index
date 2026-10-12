import type { City, DatasetStatus, Indicator, Observation, Place, ScoreRow } from "@/lib/data";
import { SITE_URL } from "@/lib/site";

/**
 * Public read-only JSON API (/api/v1). Field names match the CSV downloads' columns; values are
 * the latest vintage of each figure. Every response is wrapped with its licence and attribution.
 */

export const API_DOCS = `${SITE_URL}/en/data#api`;

const HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Access-Control-Allow-Origin": "*",
  // Data changes at most daily; the pipeline's revalidation doesn't reach the CDN copy.
  "Cache-Control": "public, max-age=3600, s-maxage=21600, stale-while-revalidate=86400",
};

export function apiResponse(data: unknown): Response {
  const body = {
    licence: "CC BY 4.0",
    attribution: `Unnati Index (${SITE_URL}), compiled from official sources`,
    docs: API_DOCS,
    data,
  };
  return new Response(JSON.stringify(body), { headers: HEADERS });
}

export function apiError(status: number, error: string): Response {
  return new Response(JSON.stringify({ error, docs: API_DOCS }), {
    status,
    headers: { ...HEADERS, "Cache-Control": "public, max-age=300" },
  });
}

/** "hi" for Hindi text (indicator names, units, descriptions), anything else English. */
export function apiLang(request: Request): "en" | "hi" {
  return new URL(request.url).searchParams.get("lang") === "hi" ? "hi" : "en";
}

export function apiPlace(p: Place) {
  return { slug: p.slug, name: p.name, name_hi: p.nameHi, type: p.type, peer_group: p.peerGroup };
}

export function apiCity(c: City) {
  return {
    slug: c.slug,
    name: c.name,
    name_hi: c.nameHi,
    type: "city",
    state: c.stateSlug,
    latitude: c.latitude,
    longitude: c.longitude,
    population_2011: c.population,
    million_plus: c.millionPlus,
  };
}

export function apiIndicator(i: Indicator, source?: { source: string; dataset: string; url: string | null }) {
  return {
    id: i.id,
    name: i.name,
    description: i.description,
    unit: i.unit,
    direction: i.direction,
    ranked: i.rankable,
    category: i.categoryId,
    pillar: i.pillarId,
    decimals: i.decimals,
    caveat: i.caveat,
    source: source?.source ?? null,
    dataset: source?.dataset ?? null,
    source_url: source?.url ?? null,
  };
}

export function apiObservation(o: Observation) {
  return {
    indicator_id: o.indicatorId,
    place_slug: o.slug,
    period: o.label,
    period_start: o.start,
    period_end: o.end,
    value: o.value,
    ci_low: o.ciLow,
    ci_high: o.ciHigh,
    provisional: o.provisional,
    note: o.note,
  };
}

/** One edition's scores grouped by place: the Unnati Index score and ranks, then each pillar. */
export function apiRankings(rows: ScoreRow[]) {
  const ranks = (r: ScoreRow) => ({
    score: r.score,
    rank: r.rank,
    rank_peer: r.rankPeer,
    rank_previous: r.rankPrev,
    rank_peer_previous: r.rankPeerPrev,
  });
  const bySlug = new Map<string, { place_slug: string; unnati_index: object | null; pillars: object }>();
  for (const r of rows) {
    if (r.level === "indicator") continue;
    const entry = bySlug.get(r.slug) ?? { place_slug: r.slug, unnati_index: null, pillars: {} };
    if (r.level === "composite") entry.unnati_index = ranks(r);
    else (entry.pillars as Record<string, object>)[r.key] = { ...ranks(r), coverage: r.coverage };
    bySlug.set(r.slug, entry);
  }
  const rank = (e: { unnati_index: object | null }) =>
    (e.unnati_index as { rank: number | null } | null)?.rank ?? Number.POSITIVE_INFINITY;
  return [...bySlug.values()].sort((a, b) => rank(a) - rank(b) || a.place_slug.localeCompare(b.place_slug));
}

export function apiSource(d: DatasetStatus) {
  return {
    id: d.id,
    title: d.title,
    publisher: d.source,
    cadence: d.cadence,
    landing_url: d.landingUrl,
    last_checked: d.lastChecked,
    last_new_data: d.lastChanged,
    status: d.health.status,
    status_since: "since" in d.health ? d.health.since : null,
  };
}
