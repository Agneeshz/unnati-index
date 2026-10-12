import { describe, expect, it } from "vitest";
import { formatPeriod } from "./period";

describe("formatPeriod", () => {
  it("writes dates out and leaves other English labels alone", () => {
    expect(formatPeriod("2024-01-01", "en")).toBe("1 Jan 2024");
    expect(formatPeriod("Apr–Aug 2026 (FY 2026-27 to date)", "en")).toBe("Apr–Aug 2026 (FY 2026-27 to date)");
    expect(formatPeriod("2024-25", "en")).toBe("2024-25");
  });

  it("translates months, ranges and financial-year-to-date labels into Hindi", () => {
    expect(formatPeriod("2024-01-01", "hi")).toBe("1 जनवरी 2024");
    expect(formatPeriod("Sep 2014", "hi")).toBe("सितंबर 2014");
    expect(formatPeriod("Jul 2025–Jun 2026", "hi")).toBe("जुलाई 2025–जून 2026");
    expect(formatPeriod("2012-13 to 2014-15", "hi")).toBe("2012-13 से 2014-15 तक");
    expect(formatPeriod("Apr–Aug 2026 (FY 2026-27 to date)", "hi")).toBe("अप्रैल–अगस्त 2026 (वित्त वर्ष 2026-27, अब तक)");
    expect(formatPeriod("SS 2024-25", "hi")).toBe("स्वच्छ सर्वेक्षण 2024-25");
    expect(formatPeriod("NFHS-5 (2019-21)", "hi")).toBe("NFHS-5 (2019-21)");
    expect(formatPeriod("2024", "hi")).toBe("2024");
  });
});
