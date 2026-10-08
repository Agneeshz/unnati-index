import { locale as rootLocale } from "next/root-params";
import { MapTooltip } from "@/components/map-tooltip";
import { getDictionary } from "@/i18n/dictionaries";
import { getPlaces } from "@/lib/data";
import { formatNumber } from "@/lib/format";
import { indiaShapes, MAP_HEIGHT, MAP_WIDTH, projectIndia, RAMP, stateView } from "@/lib/map";
import { type AqiCategory, aqiCategory } from "@/lib/present";

export type CityPoint = {
  slug: string;
  name: string;
  latitude: number;
  longitude: number;
  population: number | null;
  aqi: number | null; // 30-day average
};

/** AQI categories on the site's sequential ramp; the two worst share the darkest step. */
const AQI_FILL: Record<AqiCategory, string> = {
  good: RAMP[0],
  satisfactory: RAMP[1],
  moderate: RAMP[2],
  poor: RAMP[3],
  veryPoor: RAMP[4],
  severe: RAMP[4],
};
const LARGEST = 12_442_373; // Mumbai, Census 2011: the size scale is the same on every map

/**
 * Cities as dots on India or on one state: size by population, fill by 30-day average air
 * quality, every dot a link with a hover label. Neighbouring states are drawn faintly so a
 * state map keeps its context. The same values are in the table beside it.
 */
export async function CityMap({
  view,
  points,
  title,
  highlight,
  hrefFor,
  labels = 6,
}: {
  view: "india" | string;
  points: CityPoint[];
  title: string;
  highlight?: string;
  hrefFor: (slug: string) => string;
  labels?: number;
}) {
  const [dict, lang, places] = await Promise.all([getDictionary(), rootLocale(), getPlaces()]);
  const locale = lang === "hi" ? "hi" : "en";
  const stateName = new Map(places.map((p) => [p.slug, locale === "hi" && p.nameHi ? p.nameHi : p.name]));

  const india = view === "india";
  const frame = india ? null : stateView(view);
  if (!india && !frame) return null;
  const width = frame?.width ?? MAP_WIDTH;
  const height = frame?.height ?? MAP_HEIGHT;
  const project = frame ? frame.project : projectIndia;
  const target = frame?.shape;
  const others = frame ? frame.others : indiaShapes();
  const scale = india ? 1 : 1.35;

  const dots = points
    .map((p) => {
      const [x, y] = project(p.longitude, p.latitude);
      const r = scale * (4 + 8 * Math.sqrt((p.population ?? 150_000) / LARGEST));
      const category = p.aqi != null ? aqiCategory(p.aqi) : null;
      const air = category
        ? `${dict.ui.cities.aqi30}: ${formatNumber(p.aqi as number, 0, locale)} (${dict.ui.aqi[category]})`
        : dict.ui.cities.noAqi;
      const people = p.population ? ` · ${formatNumber(p.population, 0, locale)} (2011)` : "";
      return { ...p, x, y, r, category, tip: `${p.name}${people} · ${air}` };
    })
    .filter((d) => d.x >= -20 && d.x <= width + 20 && d.y >= -20 && d.y <= height + 20)
    .sort((a, b) => (b.population ?? 0) - (a.population ?? 0)); // big first, so small dots stay on top

  // Direct labels for the largest cities (and the highlighted one), skipping any that collide.
  const placed: { x: number; y: number }[] = [];
  const labelled = new Set<string>();
  for (const d of [...dots.filter((d) => d.slug === highlight), ...dots]) {
    if (labelled.size >= labels + (highlight ? 1 : 0) && d.slug !== highlight) break;
    if (labelled.has(d.slug)) continue;
    if (placed.some((p) => Math.abs(p.y - d.y) < 14 && Math.abs(p.x - d.x) < 70)) continue;
    placed.push({ x: d.x, y: d.y });
    labelled.add(d.slug);
  }

  const legend: { text: string; fill: string; dashed?: boolean }[] = [
    { text: dict.ui.aqi.good, fill: AQI_FILL.good },
    { text: dict.ui.aqi.satisfactory, fill: AQI_FILL.satisfactory },
    { text: dict.ui.aqi.moderate, fill: AQI_FILL.moderate },
    { text: dict.ui.aqi.poor, fill: AQI_FILL.poor },
    { text: `${dict.ui.aqi.veryPoor} / ${dict.ui.aqi.severe}`, fill: AQI_FILL.veryPoor },
    { text: dict.ui.common.notAvailable, fill: "var(--surface)", dashed: true },
  ];

  return (
    <figure className="rounded-lg border border-border bg-surface p-3">
      <figcaption className="mb-2 text-sm font-medium">{title}</figcaption>
      <MapTooltip>
        <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title} className="mx-auto h-auto w-full">
          {others.map((s) => (
            <path
              key={s.slug}
              d={s.d}
              className={india ? "fill-bg stroke-border" : "fill-bg stroke-border opacity-60"}
              strokeWidth={0.8}
              data-tip={stateName.get(s.slug) ?? s.name}
            />
          ))}
          {target && (
            <path d={target.d} className="fill-accent-soft stroke-muted" strokeWidth={1.2}>
              <title>{stateName.get(target.slug) ?? target.name}</title>
            </path>
          )}
          {dots.map((d) => (
            <a key={d.slug} href={hrefFor(d.slug)} aria-label={d.tip}>
              {/* Surface halo keeps overlapping dots apart; an outline keeps the lightest step visible. */}
              <circle cx={d.x} cy={d.y} r={d.r + 2} className="fill-surface" />
              <circle
                cx={d.x}
                cy={d.y}
                r={d.r}
                fill={d.category ? AQI_FILL[d.category] : "var(--surface)"}
                className="stroke-fg"
                strokeWidth={d.slug === highlight ? 2.5 : 0.75}
                strokeDasharray={d.category ? undefined : "2 2"}
                data-tip={d.tip}
                tabIndex={0}
              >
                <title>{d.tip}</title>
              </circle>
            </a>
          ))}
          {dots
            .filter((d) => labelled.has(d.slug))
            .map((d) => (
              <text
                key={`l-${d.slug}`}
                // Labels sit right of the dot, or left of it near the right edge.
                x={d.x > width - 110 ? d.x - d.r - 4 : d.x + d.r + 4}
                textAnchor={d.x > width - 110 ? "end" : "start"}
                y={d.y + 4}
                className={`fill-fg stroke-surface text-[12px] ${d.slug === highlight ? "font-bold" : "font-medium"}`}
                strokeWidth={3}
                paintOrder="stroke"
                pointerEvents="none"
              >
                {d.name}
              </text>
            ))}
        </svg>
      </MapTooltip>
      <div className="mt-2 space-y-1 text-xs text-muted">
        <ul className="flex flex-wrap gap-x-3 gap-y-1" aria-label={dict.ui.map.legend}>
          {legend.map((item) => (
            <li key={item.text} className="flex items-center gap-1.5">
              <svg aria-hidden="true" width="12" height="12" className="shrink-0">
                <circle
                  cx="6"
                  cy="6"
                  r="5"
                  fill={item.fill}
                  className="stroke-fg"
                  strokeWidth="0.75"
                  strokeDasharray={item.dashed ? "2 2" : undefined}
                />
              </svg>
              {item.text}
            </li>
          ))}
        </ul>
        <p>{dict.ui.cities.mapNote}</p>
      </div>
    </figure>
  );
}
