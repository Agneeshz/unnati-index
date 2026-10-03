import { describe, expect, it } from "vitest";
import { isAuthorised, parseTags } from "./revalidate";

describe("isAuthorised", () => {
  it("accepts the right bearer token", () => {
    expect(isAuthorised("Bearer s3cret", "s3cret")).toBe(true);
  });

  it("rejects wrong, missing or malformed credentials", () => {
    expect(isAuthorised("Bearer wrong!", "s3cret")).toBe(false);
    expect(isAuthorised("Bearer s3cre", "s3cret")).toBe(false);
    expect(isAuthorised("s3cret", "s3cret")).toBe(false);
    expect(isAuthorised(null, "s3cret")).toBe(false);
  });

  it("refuses everything when no secret is configured", () => {
    expect(isAuthorised("Bearer ", undefined)).toBe(false);
    expect(isAuthorised("Bearer ", "")).toBe(false);
  });
});

describe("parseTags", () => {
  it("returns de-duplicated valid tags", () => {
    expect(parseTags({ tags: ["indicator:imr", "state:kerala", "indicator:imr"] })).toEqual([
      "indicator:imr",
      "state:kerala",
    ]);
  });

  it("rejects malformed bodies and tags", () => {
    expect(parseTags(null)).toBeNull();
    expect(parseTags({})).toBeNull();
    expect(parseTags({ tags: [] })).toBeNull();
    expect(parseTags({ tags: ["Upper:Case"] })).toBeNull();
    expect(parseTags({ tags: ["has space"] })).toBeNull();
    expect(parseTags({ tags: [42] })).toBeNull();
    expect(parseTags({ tags: Array.from({ length: 101 }, (_, i) => `t${i}`) })).toBeNull();
  });
});
