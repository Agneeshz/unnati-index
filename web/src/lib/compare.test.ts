import { describe, expect, it } from "vitest";
import { bestIndex, neighbours, parseSelection } from "./compare";

const VALID = ["keralam", "bihar", "goa", "delhi", "punjab"];

describe("parseSelection", () => {
  it("accepts comma lists and repeated params, dropping unknown and repeated slugs", () => {
    expect(parseSelection("keralam,bihar,nowhere,keralam", VALID)).toEqual(["keralam", "bihar"]);
    expect(parseSelection(["keralam", "", "Goa"], VALID)).toEqual(["keralam", "goa"]);
    expect(parseSelection(undefined, VALID)).toEqual([]);
  });

  it("keeps at most four", () => {
    expect(parseSelection(VALID.join(","), VALID)).toHaveLength(4);
  });
});

describe("neighbours", () => {
  it("is symmetric", () => {
    expect(neighbours("keralam")).toContain("karnataka");
    expect(neighbours("karnataka")).toContain("keralam");
    expect(neighbours("lakshadweep")).toEqual([]);
  });
});

describe("bestIndex", () => {
  it("follows the indicator's direction and refuses ties and neutral indicators", () => {
    expect(bestIndex([5, 30, null], "lower_better")).toBe(0);
    expect(bestIndex([5, 30, null], "higher_better")).toBe(1);
    expect(bestIndex([30, 30], "higher_better")).toBeNull();
    expect(bestIndex([1, 2], "neutral")).toBeNull();
    expect(bestIndex([1, null], "higher_better")).toBeNull();
  });
});
