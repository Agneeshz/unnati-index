import { describe, expect, it } from "vitest";
import { isLocale, negotiateLocale } from "./config";

describe("negotiateLocale", () => {
  it("defaults to English", () => {
    expect(negotiateLocale(null)).toBe("en");
    expect(negotiateLocale("")).toBe("en");
    expect(negotiateLocale("fr-FR,fr;q=0.9")).toBe("en");
  });

  it("does not send visitors to Hindi before it launches", () => {
    expect(negotiateLocale("hi-IN,hi;q=0.9,en;q=0.8")).toBe("en");
  });

  it("respects quality weights among launched locales", () => {
    expect(negotiateLocale("ta;q=0.9,en-IN;q=0.5")).toBe("en");
    expect(negotiateLocale("en;q=0")).toBe("en");
  });
});

describe("isLocale", () => {
  it("accepts only supported locales", () => {
    expect(isLocale("en")).toBe(true);
    expect(isLocale("hi")).toBe(true);
    expect(isLocale("fr")).toBe(false);
    expect(isLocale(undefined)).toBe(false);
  });
});
