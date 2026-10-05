import { describe, expect, it } from "vitest";
import { formatCompact, formatNumber, formatPercent } from "./format";

describe("formatNumber", () => {
  it("groups digits the Indian way", () => {
    expect(formatNumber(1234567)).toBe("12,34,567");
    expect(formatNumber(1000)).toBe("1,000");
    expect(formatNumber(-98765432)).toBe("-9,87,65,432");
  });

  it("rounds to the requested decimals", () => {
    expect(formatNumber(418.94, 1)).toBe("418.9");
    expect(formatNumber(5, 1)).toBe("5.0");
  });

  it("uses Latin digits for Hindi", () => {
    expect(formatNumber(1234567, 0, "hi")).toBe("12,34,567");
  });
});

describe("formatCompact", () => {
  it("uses crore and lakh", () => {
    expect(formatCompact(45_600_000)).toBe("4.56 crore");
    expect(formatCompact(123_000)).toBe("1.23 lakh");
    expect(formatCompact(5_88_600_000)).toBe("58.86 crore");
  });

  it("leaves small values as grouped numbers", () => {
    expect(formatCompact(99_999)).toBe("99,999");
  });

  it("handles negatives and Hindi units", () => {
    expect(formatCompact(-2_50_00_000)).toBe("-2.50 crore");
    expect(formatCompact(1_77_175, "hi")).toBe("1.77 लाख");
  });
});

describe("formatPercent", () => {
  it("appends a percent sign", () => {
    expect(formatPercent(5.5)).toBe("5.5%");
    expect(formatPercent(54.44, 1)).toBe("54.4%");
  });
});

describe("releaseSummary", async () => {
  const { releaseSummary } = await import("./present");
  const hi = (await import("@/i18n/dictionaries/hi.json")).default;
  const en = (await import("@/i18n/dictionaries/en.json")).default;
  it("rebuilds the pipeline's English summary in the page language", () => {
    expect(releaseSummary("110 new and 155 revised figures across 3 indicators", hi)).toBe(
      "3 संकेतकों में 110 नए और 155 संशोधित आँकड़े",
    );
    expect(releaseSummary("30 new figures across 1 indicator", en)).toBe("30 new figures across 1 indicator");
    expect(releaseSummary("something else", hi)).toBe("something else");
  });
});
