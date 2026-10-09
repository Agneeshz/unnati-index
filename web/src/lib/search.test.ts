import { describe, expect, it } from "vitest";
import { normalize, type SearchEntry, search } from "./search";

const entry = (type: SearchEntry["type"], title: string, extra: Partial<SearchEntry> = {}): SearchEntry => ({
  type,
  title,
  href: `/${title}`,
  names: [normalize(title)],
  ...extra,
});

const ENTRIES: SearchEntry[] = [
  entry("state", "Keralam", { names: ["keralam", "केरलम"], aliases: ["kerala"] }),
  entry("state", "Odisha", { aliases: ["orissa"] }),
  entry("state", "Tamil Nadu"),
  entry("city", "Gurugram", { aliases: ["gurgaon"] }),
  entry("city", "Bhubaneswar"),
  entry("city", "Sri Vijaya Puram", { aliases: ["port blair"] }),
  entry("pillar", "Inclusion", { text: "fair distribution of gains" }),
  entry("indicator", "Average air quality index"),
  entry("indicator", "Infant mortality rate", { text: normalize("Deaths of infants under one year") }),
  entry("indicator", "Under-5 mortality rate"),
];

const titles = (q: string) => search(ENTRIES, q).map((r) => r.title);

describe("search", () => {
  it("matches names from the start, then any word", () => {
    expect(titles("kera")[0]).toBe("Keralam");
    expect(titles("nadu")).toEqual(["Tamil Nadu"]);
    expect(titles("mortality")).toEqual(["Infant mortality rate", "Under-5 mortality rate"]);
  });

  it("finds former names and Hindi names", () => {
    expect(titles("Orissa")).toEqual(["Odisha"]);
    expect(titles("gurgaon")).toEqual(["Gurugram"]);
    expect(titles("केरल")).toEqual(["Keralam"]);
  });

  it("forgives one typo in a longer word, and falls back to descriptions", () => {
    expect(titles("bhubneswar")).toEqual(["Bhubaneswar"]);
    expect(titles("infants")).toEqual(["Infant mortality rate"]);
  });

  it("does not match letters inside unrelated words", () => {
    expect(titles("air")).toEqual(["Average air quality index"]);
  });

  it("returns nothing for an empty query", () => {
    expect(search(ENTRIES, "  ")).toEqual([]);
  });
});
