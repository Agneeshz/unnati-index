import "server-only";
import { geoMercator, geoPath } from "d3-geo";
import type { FeatureCollection, Geometry } from "geojson";
import { feature } from "topojson-client";
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

/** Projected SVG paths for every state/UT (computed once per server process). */
export function indiaShapes(): Shape[] {
  if (shapes) return shapes;
  const topo = topology as unknown as Topology;
  const states = feature(topo, topo.objects.states) as unknown as FeatureCollection<
    Geometry,
    { slug: string; name: string }
  >;
  const projection = geoMercator().fitSize([MAP_WIDTH, MAP_HEIGHT], states);
  const path = geoPath(projection);
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
