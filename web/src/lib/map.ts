import "server-only";
import { type GeoProjection, geoMercator, geoPath } from "d3-geo";
import type { FeatureCollection, Geometry } from "geojson";
import { feature } from "topojson-client";
import { presimplify, quantile, simplify } from "topojson-simplify";
import type { Topology } from "topojson-specification";
import topology from "../../public/geo/india-states.topo.json";

export const MAP_WIDTH = 560;
export const MAP_HEIGHT = 640;

export type Shape = { slug: string; name: string; d: string; cx: number; cy: number; area: number };

/** Places too small to see at national scale; maps add a marker for them. */
export const SMALL_PLACES = new Set([
  "chandigarh",
  "delhi",
  "puducherry",
  "lakshadweep",
  "dadra-and-nagar-haveli-and-daman-and-diu",
  "goa",
  "andaman-and-nicobar-islands",
]);

let shapes: Shape[] | null = null;
let indiaProjection: GeoProjection | null = null;

type StateFeatures = FeatureCollection<Geometry, { slug: string; name: string }>;

/**
 * The state boundaries, full detail for zoomed state maps, or simplified for national maps:
 * keeping 30% of the points is indistinguishable at 560 px and cuts the paths from 251 KB to
 * 79 KB per map (and Next repeats them in the page payload). Shared borders stay shared.
 */
const featureCache = new Map<string, StateFeatures>();

function stateFeatures(detail: "full" | "national" = "full"): StateFeatures {
  const cached = featureCache.get(detail);
  if (cached) return cached;
  let topo = topology as unknown as Topology;
  if (detail === "national") {
    const weighted = presimplify(JSON.parse(JSON.stringify(topo)) as Parameters<typeof presimplify>[0]);
    topo = simplify(weighted, quantile(weighted, 0.3)) as unknown as Topology;
  }
  const features = feature(topo, topo.objects.states) as unknown as StateFeatures;
  featureCache.set(detail, features);
  return features;
}

/** [x, y] on the national map for a longitude/latitude (same projection as indiaShapes). */
export function projectIndia(longitude: number, latitude: number): [number, number] {
  indiaShapes();
  return (indiaProjection as GeoProjection)([longitude, latitude]) ?? [0, 0];
}

/** Projected SVG paths for every state/UT (computed once per server process). */
export function indiaShapes(): Shape[] {
  if (shapes) return shapes;
  const states = stateFeatures("national");
  const projection = geoMercator().fitSize([MAP_WIDTH, MAP_HEIGHT], states);
  indiaProjection = projection;
  const path = geoPath(projection).digits(1);
  shapes = states.features.map((f) => {
    const [cx, cy] = path.centroid(f);
    return { slug: f.properties.slug, name: f.properties.name, d: path(f) ?? "", cx, cy, area: path.area(f) };
  });
  return shapes;
}

/** Five sequential steps (light -> dark) from the validated blue ramp. */
export const RAMP = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"];

/** Class breaks by quantile, so each colour holds about the same number of places. */
export function breaks(values: number[], classes = RAMP.length): number[] {
  const sorted = [...values].sort((a, b) => a - b);
  if (sorted.length === 0) return [];
  const out: number[] = [];
  for (let i = 1; i < classes; i++) {
    out.push(sorted[Math.min(sorted.length - 1, Math.floor((i * sorted.length) / classes))]);
  }
  return [...new Set(out)];
}

export function classOf(value: number, cuts: number[]): number {
  let index = 0;
  while (index < cuts.length && value >= cuts[index]) index++;
  // Spread fewer classes across the ramp so the darkest step is always used.
  const classes = cuts.length + 1;
  return classes === 1 ? RAMP.length - 1 : Math.round((index * (RAMP.length - 1)) / (classes - 1));
}

export type StateView = {
  width: number;
  height: number;
  /** The state itself, then its surroundings (drawn faintly for context). */
  shape: Shape;
  others: Shape[];
  project: (longitude: number, latitude: number) => [number, number];
};

const views = new Map<string, StateView>();

/** One state fitted to the frame, with neighbouring states clipped around it. */
export function stateView(slug: string, width = 560, height = 420): StateView | null {
  const key = `${slug}:${width}x${height}`;
  if (views.has(key)) return views.get(key) ?? null;
  const full = stateFeatures();
  const fullTarget = full.features.find((f) => f.properties.slug === slug);
  if (!fullTarget) return null;
  const pad = Math.round(Math.min(width, height) * 0.08);
  const projection = geoMercator().fitExtent(
    [
      [pad, pad],
      [width - pad, height - pad],
    ],
    fullTarget,
  );
  // Zoomed in past 3x the national map (small states), simplified outlines would show; otherwise
  // they are indistinguishable and far lighter. The state and its neighbours use the same set,
  // so shared borders line up.
  indiaShapes();
  const zoom = projection.scale() / (indiaProjection as GeoProjection).scale();
  const states = zoom > 3 ? full : stateFeatures("national");
  const target = states.features.find((f) => f.properties.slug === slug) ?? fullTarget;
  const path = geoPath(projection).digits(1);
  const toShape = (f: (typeof states.features)[number]): Shape => {
    const [cx, cy] = path.centroid(f);
    return { slug: f.properties.slug, name: f.properties.name, d: path(f) ?? "", cx, cy, area: path.area(f) };
  };
  const view: StateView = {
    width,
    height,
    shape: toShape(target),
    // Only neighbours that reach into the frame (all 36 at full detail made a map ~380 KB).
    others: states.features
      .filter((f) => {
        if (f === target) return false;
        const [[x0, y0], [x1, y1]] = path.bounds(f);
        return x1 >= 0 && y1 >= 0 && x0 <= width && y0 <= height;
      })
      .map(toShape),
    project: (longitude, latitude) => projection([longitude, latitude]) ?? [0, 0],
  };
  views.set(key, view);
  return view;
}
