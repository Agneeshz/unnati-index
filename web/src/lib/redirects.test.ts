import { describe, expect, it } from "vitest";
import type { SearchPlace } from "./data";
import { renamedSlug } from "./redirects";

const place = (slug: string, type: SearchPlace["type"], aliases: string[]): SearchPlace => ({
  slug,
  name: slug,
  nameHi: null,
  type,
  stateSlug: null,
  aliases,
});
const places = [
  place("keralam", "state", ["kerala", "keralam"]),
  place("odisha", "state", ["orissa", "odisha"]),
  place("gurugram", "city", ["gurgaon", "gurugram"]),
];

describe("renamedSlug", () => {
  it("maps an old name to the current slug", () => {
    expect(renamedSlug(places, "kerala", ["state", "ut"])).toBe("keralam");
    expect(renamedSlug(places, "Orissa", ["state", "ut"])).toBe("odisha");
    expect(renamedSlug(places, "gurgaon", ["city"])).toBe("gurugram");
  });

  it("keeps states and cities apart and ignores unknown names", () => {
    expect(renamedSlug(places, "gurgaon", ["state", "ut"])).toBeNull();
    expect(renamedSlug(places, "atlantis", ["state", "ut"])).toBeNull();
    expect(renamedSlug(places, "keralam", ["state", "ut"])).toBeNull();
  });
});
