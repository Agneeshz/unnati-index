import "server-only";
import { type GeoProjection, type GeoStream, geoBounds, geoMercator, geoPath } from "d3-geo";
import type { FeatureCollection, Geometry } from "geojson";
import { feature, mesh } from "topojson-client";
import { presimplify, quantile, simplify } from "topojson-simplify";
import type { Topology } from "topojson-specification";
import topology from "../../public/geo/india-states.topo.json";
import detailedTopology from "../geo/india-states-detailed.topo.json";
import cityTopology from "../geo/cities.topo.json";
import waterTopology from "../geo/water.topo.json";

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

type WaterPart = { feature: GeoJSON.Feature<GeoJSON.Polygon>; bounds: [[number, number], [number, number]] };
let waterParts: WaterPart[] | null = null;

/** OpenStreetMap water around every city (ODbL; geo/water.mjs), for zoomed-in maps only: one
 *  entry per polygon with its bounds, so a frame draws only the water it shows. */
function water(): WaterPart[] {
  if (!waterParts) {
    const topo = waterTopology as unknown as Topology;
    const all = feature(topo, topo.objects.water) as unknown as FeatureCollection;
    waterParts = all.features.flatMap((f) => {
      const g = f.geometry;
      const polygons = g.type === "Polygon" ? [g.coordinates] : g.type === "MultiPolygon" ? g.coordinates : [];
      return polygons.map((coordinates) => {
        const part: GeoJSON.Feature<GeoJSON.Polygon> = {
          type: "Feature",
          properties: {},
          geometry: { type: "Polygon", coordinates },
        };
        return { feature: part, bounds: geoBounds(part) };
      });
    });
  }
  return waterParts;
}

let cityFeatures: GeoJSON.Feature<GeoJSON.Geometry, { slug: string }>[] | null = null;

/** City boundaries (geo/cities.mjs) drawn in a frame: those with some part inside it. */
function cityOutlines(path: ReturnType<typeof geoPath>, width: number, height: number) {
  if (!cityFeatures) {
    const topo = cityTopology as unknown as Topology;
    cityFeatures = (feature(topo, topo.objects.cities) as unknown as FeatureCollection<GeoJSON.Geometry, { slug: string }>)
      .features;
  }
  return cityFeatures.flatMap((f) => {
    const [[x0, y0], [x1, y1]] = path.bounds(f);
    if (x1 < 0 || y1 < 0 || x0 > width || y0 > height) return [];
    const d = path(f);
    return d ? [{ slug: f.properties.slug, d }] : [];
  });
}

let borderLines: FeatureCollection | null = null;

/** Borders between states and India's land borders near cities, without coastlines (the water
 *  draws those): the land borders are the states' outer edge away from the sea (geo/water.mjs). */
function stateBorders(): FeatureCollection {
  if (!borderLines) {
    const states = detailedTopology as unknown as Topology;
    const between = mesh(states, states.objects.states as never, (a, b) => a !== b);
    const waterTopo = waterTopology as unknown as Topology;
    const land = feature(waterTopo, waterTopo.objects.landborders) as unknown as FeatureCollection;
    borderLines = {
      type: "FeatureCollection",
      features: [{ type: "Feature", properties: {}, geometry: between }, ...land.features],
    };
  }
  return borderLines;
}

/** Projection stream that skips points within `minPx` of the last one drawn: water outlines carry
 *  more detail than a close-up can show, and every point costs page weight. */
function decimate(minPx: number, out: GeoStream): GeoStream {
  let last: [number, number] | null = null;
  let pending: [number, number] | null = null;
  return {
    point(x, y) {
      if (!last || Math.hypot(x - last[0], y - last[1]) >= minPx) {
        out.point(x, y);
        last = [x, y];
        pending = null;
      } else pending = [x, y];
    },
    lineStart() {
      last = null;
      pending = null;
      out.lineStart();
    },
    lineEnd() {
      if (pending) out.point(pending[0], pending[1]);
      out.lineEnd();
    },
    polygonStart: () => out.polygonStart(),
    polygonEnd: () => out.polygonEnd(),
    sphere: () => out.sphere?.(),
  };
}

/** The water in a frame as one SVG path, without parts under ~4 px across. */
function waterPath(projection: GeoProjection, clipped: GeoProjection, width: number, height: number): string {
  const [west, north] = projection.invert?.([0, 0]) ?? [0, 0];
  const [east, south] = projection.invert?.([width, height]) ?? [0, 0];
  const minDegrees = 4 / ((projection.scale() * Math.PI) / 180);
  const parts = water().filter(
    ({ bounds: [[w, s], [e, n]] }) =>
      e >= west && w <= east && n >= south && s <= north && Math.max(e - w, n - s) >= minDegrees,
  );
  if (parts.length === 0) return "";
  const path = geoPath({ stream: (out: GeoStream) => clipped.stream(decimate(1.5, out)) }).digits(1);
  return path({ type: "FeatureCollection", features: parts.map((p) => p.feature) }) ?? "";
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
  /** Sea and large inland water on zoomed-in maps (SVG path), drawn over the states: the official
   *  boundaries count harbours, creeks, backwaters and lakes as land. Empty on wider maps. */
  water?: string;
  /** With water: the borders between states as lines, drawn over it (the coastline then comes
   *  from the water, so state outlines are filled without a stroke). */
  borders?: string;
  /** Municipal boundaries of the cities reaching into a zoomed-in frame (OpenStreetMap). */
  cities?: { slug: string; d: string }[];
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
    water: zoom > 8 ? waterPath(projection, clipped, width, height) : "",
    borders: zoom > 8 ? (path(stateBorders()) ?? "") : "",
    cities: zoom > 8 ? cityOutlines(path, width, height) : [],
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
