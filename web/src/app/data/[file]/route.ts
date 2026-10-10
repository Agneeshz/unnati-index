import { notFound } from "next/navigation";
import { csvResponse, toCsv } from "@/lib/csv";
import { getCategories, getExportRows, getIndicatorSources, getIndicators } from "@/lib/data";

/**
 * Data downloads (CC BY 4.0):
 * - /data/indicators.csv: the catalogue (definitions, units, direction, source);
 * - /data/<indicator-id>.csv: every value of one indicator, all places and periods;
 * - /data/all.csv: every value of every indicator.
 * Values are the latest vintage; earlier revisions stay in the database but are not exported.
 */
export async function GET(_request: Request, { params }: RouteContext<"/data/[file]">) {
  const { file } = await params;
  const name = file.replace(/\.csv$/, "");
  if (name === file) notFound();
  const [indicators, sources] = await Promise.all([getIndicators("en"), getIndicatorSources()]);
  const byId = new Map(indicators.map((i) => [i.id, i]));
  const sourceOf = new Map(sources.map((s) => [s.indicatorId, s]));

  if (name === "indicators") {
    const categories = new Map((await getCategories("en")).map((c) => [c.id, c.name]));
    return csvResponse(
      toCsv(
        ["indicator_id", "name", "description", "unit", "direction", "ranked", "category", "pillar", "caveat", "source", "dataset", "source_url"],
        indicators.map((i) => {
          const s = sourceOf.get(i.id);
          return [
            i.id,
            i.name,
            i.description,
            i.unit,
            i.direction,
            i.rankable,
            categories.get(i.categoryId) ?? i.categoryId,
            i.pillarId,
            i.caveat,
            s?.source,
            s?.dataset,
            s?.url,
          ];
        }),
      ),
      "unnati-indicators.csv",
    );
  }

  if (name !== "all" && !byId.has(name)) notFound();
  const rows = await getExportRows(name === "all" ? undefined : name);
  return csvResponse(
    toCsv(
      ["indicator_id", "indicator", "unit", "place_slug", "place", "place_type", "city_state", "period", "period_start", "period_end", "value", "ci_low", "ci_high", "provisional", "note", "source"],
      rows.map((o) => [
        o.indicatorId,
        byId.get(o.indicatorId)?.name,
        byId.get(o.indicatorId)?.unit,
        o.slug,
        o.placeName,
        o.placeType,
        o.stateSlug,
        o.label,
        o.start,
        o.end,
        o.value,
        o.ciLow,
        o.ciHigh,
        o.provisional,
        o.note,
        sourceOf.get(o.indicatorId)?.source,
      ]),
    ),
    name === "all" ? "unnati-all-indicators.csv" : `unnati-${name}.csv`,
  );
}
