import { describe, expect, it } from "vitest";
import { clusters, placeLabels } from "./city-layout";

const dot = (slug: string, x: number, y: number, r = 5) => ({ slug, name: slug, x, y, r });

describe("placeLabels", () => {
  it("labels every dot that has room, moving labels left near the right edge", () => {
    const labels = placeLabels([dot("pune", 100, 100), dot("nagpur", 390, 100)], 400, 200);
    expect(labels.get("pune")?.anchor).toBe("start");
    expect(labels.get("nagpur")?.anchor).toBe("end");
  });

  it("never lets two labels or a label and a dot overlap", () => {
    // Three dots in a tight row: the middle one has no clear side, but can go above or below.
    const labels = placeLabels([dot("a", 100, 100), dot("b", 112, 100), dot("c", 124, 100)], 400, 200);
    expect(labels.size).toBe(3);
    expect(new Set([...labels.values()].map((l) => `${l.x},${l.y}`)).size).toBe(3);
  });

  it("stops at the maximum", () => {
    expect(placeLabels([dot("a", 50, 50), dot("b", 50, 150)], 400, 200, 1).size).toBe(1);
  });
});

describe("clusters", () => {
  it("groups nearby dots and keeps isolated ones apart, largest group first", () => {
    const groups = clusters([dot("a", 0, 0), dot("b", 10, 0), dot("c", 18, 5), dot("far", 300, 300)], 20);
    expect(groups.map((g) => g.map((d) => d.slug).sort())).toEqual([["a", "b", "c"], ["far"]]);
  });
});
