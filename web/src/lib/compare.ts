export const MAX_COMPARE = 4;

/** Land borders between states and UTs (each pair listed once; the map is made symmetric). */
const BORDERS: Record<string, string[]> = {
  "andhra-pradesh": ["telangana", "karnataka", "tamil-nadu", "odisha", "chhattisgarh", "puducherry"],
  "arunachal-pradesh": ["assam", "nagaland"],
  assam: ["nagaland", "manipur", "mizoram", "tripura", "meghalaya", "west-bengal"],
  bihar: ["uttar-pradesh", "jharkhand", "west-bengal"],
  chhattisgarh: ["madhya-pradesh", "maharashtra", "telangana", "odisha", "jharkhand", "uttar-pradesh"],
  goa: ["maharashtra", "karnataka"],
  gujarat: ["rajasthan", "madhya-pradesh", "maharashtra", "dadra-and-nagar-haveli-and-daman-and-diu"],
  haryana: ["punjab", "himachal-pradesh", "uttar-pradesh", "rajasthan", "delhi", "chandigarh"],
  "himachal-pradesh": ["jammu-and-kashmir", "ladakh", "punjab", "uttarakhand"],
  jharkhand: ["west-bengal", "odisha", "uttar-pradesh"],
  karnataka: ["maharashtra", "telangana", "tamil-nadu", "keralam"],
  keralam: ["tamil-nadu", "puducherry"],
  "madhya-pradesh": ["rajasthan", "uttar-pradesh", "maharashtra"],
  maharashtra: ["telangana", "dadra-and-nagar-haveli-and-daman-and-diu"],
  manipur: ["nagaland", "mizoram"],
  mizoram: ["tripura"],
  punjab: ["jammu-and-kashmir", "rajasthan", "chandigarh"],
  rajasthan: ["uttar-pradesh"],
  sikkim: ["west-bengal"],
  "tamil-nadu": ["puducherry"],
  "uttar-pradesh": ["uttarakhand", "delhi"],
  "jammu-and-kashmir": ["ladakh"],
};

const NEIGHBOURS: Map<string, string[]> = (() => {
  const out = new Map<string, Set<string>>();
  const link = (a: string, b: string) => {
    if (!out.has(a)) out.set(a, new Set());
    out.get(a)!.add(b);
  };
  for (const [a, list] of Object.entries(BORDERS))
    for (const b of list) {
      link(a, b);
      link(b, a);
    }
  return new Map([...out].map(([k, v]) => [k, [...v].sort()]));
})();

export function neighbours(slug: string): string[] {
  return NEIGHBOURS.get(slug) ?? [];
}

/** Well-known rivalries shown when nothing is selected yet. */
export const POPULAR: [string, string][] = [
  ["keralam", "tamil-nadu"],
  ["bihar", "uttar-pradesh"],
  ["maharashtra", "gujarat"],
  ["karnataka", "telangana"],
  ["punjab", "haryana"],
  ["west-bengal", "odisha"],
  ["assam", "tripura"],
  ["delhi", "chandigarh"],
];

/**
 * Places to compare from the `e` search param: "?e=kerala,bihar" or repeated "?e=kerala&e=bihar"
 * (what the picker form submits). Unknown and repeated slugs are dropped; at most four are kept.
 */
export function parseSelection(raw: string | string[] | undefined, valid: Iterable<string>): string[] {
  const allowed = new Set(valid);
  const values = (Array.isArray(raw) ? raw : raw ? [raw] : []).flatMap((v) => v.split(","));
  const out: string[] = [];
  for (const value of values) {
    const slug = value.trim().toLowerCase();
    if (allowed.has(slug) && !out.includes(slug)) out.push(slug);
  }
  return out.slice(0, MAX_COMPARE);
}

export function compareHref(locale: string, slugs: string[]): string {
  return `/${locale}/compare?e=${slugs.join(",")}`;
}

/**
 * Index of the best value in a row, or null when it can't be called: fewer than two values,
 * a neutral indicator, or a tie for the best.
 */
export function bestIndex(
  values: (number | null)[],
  direction: "higher_better" | "lower_better" | "neutral",
): number | null {
  if (direction === "neutral") return null;
  const present = values.flatMap((v, i) => (v == null ? [] : [{ v, i }]));
  if (present.length < 2) return null;
  const sign = direction === "higher_better" ? 1 : -1;
  const best = present.reduce((a, b) => (sign * b.v > sign * a.v ? b : a));
  return present.filter((p) => p.v === best.v).length > 1 ? null : best.i;
}
