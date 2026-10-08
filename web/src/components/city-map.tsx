import { locale as rootLocale } from "next/root-params";
import { MapTooltip } from "@/components/map-tooltip";
import type { Locale } from "@/i18n/config";
import { type Dictionary, getDictionary } from "@/i18n/dictionaries";
import { clusters, type Label, placeLabels } from "@/lib/city-layout";
import { getPlaces } from "@/lib/data";
import { formatNumber } from "@/lib/format";
import {
  type Bounds,
  boundsAround,
  indiaShapes,
  MAP_HEIGHT,
  MAP_WIDTH,
  type MapView,
  projectIndia,
  RAMP,
  regionView,
  stateView,
} from "@/lib/map";
import { type AqiCategory, aqiCategory, fill } from "@/lib/present";

export type CityPoint = {
  slug: string;
  name: string;
  latitude: number;
  longitude: number;
  population: number | null;
  aqi: number | null; // 30-day average
};

/** Where a map looks: all of India, one state, or the area around a city. */
export type CityMapView = "india" | { state: string } | { around: string; km: number; state?: string };

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
const MAX_INSETS = 3;
const INSET = { width: 560, height: 360 };
const AROUND_KM = [45, 30, 20]; // a city close-up zooms in until every nearby city can be named

type Dot = CityPoint & { x: number; y: number; r: number; category: AqiCategory | null; tip: string };
type Frame = { view: MapView; dots: Dot[]; labels: Map<string, Label> };

function dotsFor(view: MapView, points: CityPoint[], scale: number, dict: Dictionary, locale: Locale): Dot[] {
  return points
    .map((p) => {
      const [x, y] = view.project(p.longitude, p.latitude);
      const r = scale * (4 + 8 * Math.sqrt((p.population ?? 150_000) / LARGEST));
      const category = p.aqi != null ? aqiCategory(p.aqi) : null;
      const air = category
        ? `${dict.ui.cities.aqi30}: ${formatNumber(p.aqi as number, 0, locale)} (${dict.ui.aqi[category]})`
        : dict.ui.cities.noAqi;
      const people = p.population ? ` · ${formatNumber(p.population, 0, locale)} (2011)` : "";
      return { ...p, x, y, r, category, tip: `${p.name}${people} · ${air}` };
    })
    .filter((d) => d.x >= 0 && d.x <= view.width && d.y >= 0 && d.y <= view.height)
    .sort((a, b) => (b.population ?? 0) - (a.population ?? 0));
}

/** Highlighted city first, then by population: the order labels are given room. */
function byPriority(dots: Dot[], highlight?: string): Dot[] {
  return [...dots.filter((d) => d.slug === highlight), ...dots.filter((d) => d.slug !== highlight)];
}

/**
 * Cities as dots: size by population, fill by 30-day average air quality (named in every hover
 * label and in the legend), every dot a link. Every city whose label fits is named; where
 * cities are too crowded to name, the busiest areas are repeated as enlarged insets with
 * full-detail borders, outlined on the main map. The same values are in the table beside it.
 */
export async function CityMap({
  view,
  points,
  title,
  highlight,
  hrefFor,
  maxLabels,
}: {
  view: CityMapView;
  points: CityPoint[];
  title: string;
  highlight?: string;
  hrefFor: (slug: string) => string;
  maxLabels?: number;
}) {
  const [dict, lang, places] = await Promise.all([getDictionary(), rootLocale(), getPlaces()]);
  const locale: Locale = lang === "hi" ? "hi" : "en";
  const stateName = new Map(places.map((p) => [p.slug, locale === "hi" && p.nameHi ? p.nameHi : p.name]));

  let main: MapView | null;
  if (view === "india") {
    main = {
      width: MAP_WIDTH,
      height: MAP_HEIGHT,
      shape: null,
      others: indiaShapes(),
      project: projectIndia,
    };
  } else if (!("around" in view)) {
    main = stateView(view.state);
  } else {
    main = null;
  }
  const scale = view === "india" ? 1 : 1.35;
  let frame: Frame | null = null;
  if (typeof view === "object" && "around" in view) {
    const centre = points.find((p) => p.slug === view.around);
    if (!centre) return null;
    for (const km of AROUND_KM.filter((k) => k <= view.km)) {
      const candidate = regionView(boundsAround(centre.longitude, centre.latitude, km), 560, 420, view.state ?? null);
      const cityDots = dotsFor(candidate, points, scale, dict, locale);
      const named = placeLabels(byPriority(cityDots, highlight), candidate.width, candidate.height, maxLabels);
      if (!frame || named.size > frame.labels.size || named.size === cityDots.length) {
        frame = { view: candidate, dots: cityDots, labels: named };
      }
      if (named.size === cityDots.length) break;
    }
  } else if (main) {
    const dots = dotsFor(main, points, scale, dict, locale);
    frame = { view: main, dots, labels: placeLabels(byPriority(dots, highlight), main.width, main.height, maxLabels) };
  }
  if (!frame) return null;
  main = frame.view;
  const { dots, labels } = frame;

  // Crowded areas: cities left unnamed that sit close together get an enlarged inset.
  const insets: { frame: Frame; bounds: Bounds; title: string }[] = [];
  if (typeof view === "object" && !("around" in view)) {
    // Groups of nearby cities (named or not) with at least one city left unnamed.
    const unnamed = (g: Dot[]) => g.filter((d) => !labels.has(d.slug)).length;
    const crowded = clusters(dots, 40)
      .filter((g) => g.length >= 2 && unnamed(g) > 0)
      .sort((a, b) => unnamed(b) - unnamed(a))
      .slice(0, MAX_INSETS);
    for (const group of crowded) {
      const lons = group.map((d) => d.longitude);
      const lats = group.map((d) => d.latitude);
      const padLon = Math.max(0.12, (Math.max(...lons) - Math.min(...lons)) * 0.35);
      const padLat = Math.max(0.1, (Math.max(...lats) - Math.min(...lats)) * 0.35);
      const bounds: Bounds = [
        [Math.min(...lons) - padLon, Math.min(...lats) - padLat],
        [Math.max(...lons) + padLon, Math.max(...lats) + padLat],
      ];
      const inset = regionView(bounds, INSET.width, INSET.height, view.state);
      const insetDots = dotsFor(inset, points, 1, dict, locale);
      const biggest = insetDots[0] ?? group[0];
      insets.push({
        frame: { view: inset, dots: insetDots, labels: placeLabels(byPriority(insetDots, highlight), inset.width, inset.height) },
        bounds,
        title: fill(dict.ui.cities.insetTitle, { n: insets.length + 1, city: biggest.name }),
      });
    }
  }

  const legend: { text: string; fill: string; dashed?: boolean }[] = [
    { text: dict.ui.aqi.good, fill: AQI_FILL.good },
    { text: dict.ui.aqi.satisfactory, fill: AQI_FILL.satisfactory },
    { text: dict.ui.aqi.moderate, fill: AQI_FILL.moderate },
    { text: dict.ui.aqi.poor, fill: AQI_FILL.poor },
    { text: `${dict.ui.aqi.veryPoor} / ${dict.ui.aqi.severe}`, fill: AQI_FILL.veryPoor },
    { text: dict.ui.common.notAvailable, fill: "var(--surface)", dashed: true },
  ];

  const boxes = insets.map((inset, i) => {
    const [[west, south], [east, north]] = inset.bounds;
    const [x0, y1] = main.project(west, south);
    const [x1, y0] = main.project(east, north);
    return { n: i + 1, x0, y0, x1, y1 };
  });

  return (
    <figure className="rounded-lg border border-border bg-surface p-3">
      <figcaption className="mb-2 text-sm font-medium">{title}</figcaption>
      <MapTooltip>
        <FrameSvg frame={frame} label={title} highlight={highlight} hrefFor={hrefFor} stateName={stateName}>
          {boxes.map((b) => (
            <g key={`box-${b.n}`} pointerEvents="none">
              <rect
                x={b.x0}
                y={b.y0}
                width={b.x1 - b.x0}
                height={b.y1 - b.y0}
                rx={4}
                fill="none"
                className="stroke-fg"
                strokeWidth={1}
                strokeDasharray="4 3"
              />
              <text x={b.x0 + 3} y={b.y0 - 4} className="fill-fg stroke-surface text-[11px] font-semibold" strokeWidth={3} paintOrder="stroke">
                {b.n}
              </text>
            </g>
          ))}
        </FrameSvg>
      </MapTooltip>
      {insets.length > 0 && (
        <div className="mt-3 grid gap-3">
          {insets.map((inset) => (
            <div key={inset.title} className="rounded-md border border-border p-2">
              <p className="mb-1 text-xs font-medium">{inset.title}</p>
              <MapTooltip>
                <FrameSvg
                  frame={inset.frame}
                  label={inset.title}
                  highlight={highlight}
                  hrefFor={hrefFor}
                  stateName={stateName}
                />
              </MapTooltip>
            </div>
          ))}
        </div>
      )}
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
        <p>
          {dict.ui.cities.mapNote}
          {insets.length > 0 ? ` ${dict.ui.cities.insetNote}` : ""}
        </p>
        <p>{dict.ui.map.disclaimer}</p>
      </div>
    </figure>
  );
}

function FrameSvg({
  frame,
  label,
  highlight,
  hrefFor,
  stateName,
  children,
}: {
  frame: Frame;
  label: string;
  highlight?: string;
  hrefFor: (slug: string) => string;
  stateName: Map<string, string>;
  children?: React.ReactNode;
}) {
  const { view, dots, labels } = frame;
  const focused = view.shape != null;
  return (
    <svg viewBox={`0 0 ${view.width} ${view.height}`} role="img" aria-label={label} className="mx-auto h-auto w-full">
      {view.others.map((s) => (
        <path
          key={s.slug}
          d={s.d}
          className={focused ? "fill-bg stroke-border opacity-60" : "fill-bg stroke-border"}
          strokeWidth={0.8}
          data-tip={stateName.get(s.slug) ?? s.name}
        />
      ))}
      {view.shape && (
        <path d={view.shape.d} className="fill-accent-soft stroke-muted" strokeWidth={1.2}>
          <title>{stateName.get(view.shape.slug) ?? view.shape.name}</title>
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
        .filter((d) => labels.has(d.slug))
        .map((d) => {
          const l = labels.get(d.slug) as Label;
          return (
            <text
              key={`l-${d.slug}`}
              x={l.x}
              y={l.y}
              textAnchor={l.anchor}
              className={`fill-fg stroke-surface text-[12px] ${d.slug === highlight ? "font-bold" : "font-medium"}`}
              strokeWidth={3}
              paintOrder="stroke"
              pointerEvents="none"
            >
              {d.name}
            </text>
          );
        })}
      {children}
    </svg>
  );
}
