import { describe, expect, it } from "vitest";
import { iso } from "./dates";

describe("iso", () => {
  it("keeps the calendar date of a local-midnight Date in any time zone", () => {
    // The Postgres driver returns dates as local midnight; IST is UTC+5:30.
    expect(iso(new Date(2026, 3, 1))).toBe("2026-04-01");
    expect(iso(new Date(2026, 11, 31))).toBe("2026-12-31");
    expect(iso("2024-01-01")).toBe("2024-01-01");
  });
});
