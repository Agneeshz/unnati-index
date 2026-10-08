import "server-only";
import { type GeoProjection, geoMercator, geoPath } from "d3-geo";
import type { FeatureCollection, Geometry } from "geojson";
import { feature } from "topojson-client";
import { presimplify, quantile, simplify } from "topojson-simplify";
import type { Topology } from "topojson-specification";
import topology from "../../public/geo/india-states.topo.json";
import detailedTopology from "../geo/india-states-detailed.topo.json";

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

function stateFeatures(detail: "full" | "national" | "detailed" = "full"): StateFeatures {
  const cached = featureCache.get(detail);
  if (cached) return cached;
  // "detailed" keeps 20% of the source's points (server-only, ~1 MB) for zoomed-in maps.
  let topo = (detail === "detailed" ? detailedTopology : topology) as unknown as Topology;
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

export type MapView = {
  width: number;
  height: number;
  /** The highlighted state (state maps only), and every other state reaching into the frame. */
  shape: Shape | null;
  others: Shape[];
  project: (longitude: number, latitude: number) => [number, number];
};
/** @deprecated name kept for callers: a state map is a MapView with a highlighted shape. */
export type StateView = MapView;

const views = new Map<string, MapView>();

/** Outlines fitted to a frame and clipped to it, so off-frame geometry costs nothing. */
function frameView(
  fit: GeoJSON.Feature | GeoJSON.FeatureCollection,
  width: number,
  height: number,
  highlight: string | null,
  padShare = 0.08,
): MapView {
  const pad = Math.round(Math.min(width, height) * padShare);
  const projection = geoMercator().fitExtent(
    [
      [pad, pad],
      [width - pad, height - pad],
    ],
    fit,
  );
  // Detail follows zoom: simplified outlines for state-sized views, the national file past 3x, and
  // the detailed file past 8x (city close-ups, crowded-area insets). Every shape in a frame uses the same set, so shared
  // borders line up.
  indiaShapes();
  const zoom = projection.scale() / (indiaProjection as GeoProjection).scale();
  const states = zoom > 8 ? stateFeatures("detailed") : zoom > 3 ? stateFeatures() : stateFeatures("national");
  // Outlines are clipped to the frame; points use the same projection unclipped, so a city just
  // outside the frame keeps its true position.
  const clipped = geoMercator()
    .scale(projection.scale())
    .translate(projection.translate())
    .clipExtent([
      [-2, -2],
      [width + 2, height + 2],
    ]);
  const path = geoPath(clipped).digits(1);
  const toShape = (f: (typeof states.features)[number]): Shape => {
    const [cx, cy] = path.centroid(f);
    return { slug: f.properties.slug, name: f.properties.name, d: path(f) ?? "", cx, cy, area: path.area(f) };
  };
  const shapes = states.features.map(toShape).filter((s) => s.d);
  return {
    width,
    height,
    shape: shapes.find((s) => s.slug === highlight) ?? null,
    others: shapes.filter((s) => s.slug !== highlight),
    project: (longitude, latitude) => projection([longitude, latitude]) ?? [0, 0],
  };
}

/** One state fitted to the frame, with neighbouring states around it. */
export function stateView(slug: string, width = 560, height = 420): MapView | null {
  const key = `state:${slug}:${width}x${height}`;
  if (views.has(key)) return views.get(key) ?? null;
  const target = stateFeatures().features.find((f) => f.properties.slug === slug);
  if (!target) return null;
  const view = frameView(target, width, height, slug);
  views.set(key, view);
  return view;
}

export type Bounds = [[number, number], [number, number]]; // [[west, south], [east, north]]

/** Any area (a crowded part of a state, the surroundings of a city) fitted to the frame. */
export function regionView(bounds: Bounds, width = 300, height = 240, highlight: string | null = null): MapView {
  const key = `region:${bounds.flat().map((n) => n.toFixed(3)).join(",")}:${width}x${height}:${highlight}`;
  const cached = views.get(key);
  if (cached) return cached;
  const [[west, south], [east, north]] = bounds;
  const box: GeoJSON.Feature = {
    type: "Feature",
    properties: {},
    geometry: {
      type: "MultiPoint",
      coordinates: [
        [west, south],
        [east, north],
      ],
    },
  };
  const view = frameView(box, width, height, highlight, 0.04);
  views.set(key, view);
  return view;
}

/** A square-ish box of about `km` kilometres around a point. */
export function boundsAround(longitude: number, latitude: number, km: number): Bounds {
  const dLat = km / 111;
  const dLon = km / (111 * Math.cos((latitude * Math.PI) / 180));
  return [
    [longitude - dLon, latitude - dLat],
    [longitude + dLon, latitude + dLat],
  ];
}
