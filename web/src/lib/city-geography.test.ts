import { readFileSync } from "node:fs";
import path from "node:path";
import { geoContains } from "d3-geo";
import { feature } from "topojson-client";
import type { Topology } from "topojson-specification";
import { describe, expect, it } from "vitest";
import detailed from "../geo/india-states-detailed.topo.json";

// City dots must sit on land in their own state: a coordinate in the sea (Kochi's listed one
// was 2 km off the coast) shows up on the close-up maps.
describe("city coordinates", () => {
  it("lie inside their state's boundary", () => {
    const topo = detailed as unknown as Topology;
    const states = feature(topo, topo.objects.states) as unknown as GeoJSON.FeatureCollection<
      GeoJSON.Geometry,
      { slug: string }
    >;
    const bySlug = new Map(states.features.map((f) => [f.properties.slug, f]));
    const csv = readFileSync(path.join(__dirname, "../../../pipeline/src/unnati/reference/cities.csv"), "utf8");
    const [header, ...lines] = csv.trim().split(/\r?\n/);
    const cols = header.split(",");
    const outside = lines
      .map((line) => Object.fromEntries(line.split(",").map((v, i) => [cols[i], v])))
      .filter((c) => {
        const state = bySlug.get(c.state_slug);
        return !state || !geoContains(state, [Number(c.longitude), Number(c.latitude)]);
      })
      .map((c) => c.slug);
    expect(outside).toEqual([]);
  });
});
