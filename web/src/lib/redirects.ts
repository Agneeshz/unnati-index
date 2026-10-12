import type { SearchPlace } from "@/lib/data";

/** The current slug for an old or alternative one ("kerala" -> "keralam", "gurgaon" -> "gurugram"),
 *  matched against the normalised aliases the pipeline uses to read source files. */
export function renamedSlug(
  places: SearchPlace[],
  slug: string,
  types: SearchPlace["type"][],
): string | null {
  const name = decodeURIComponent(slug).toLowerCase().replace(/[^a-z]+/g, " ").trim();
  if (!name) return null;
  const match = places.find(
    (p) => types.includes(p.type) && p.slug !== slug && (p.aliases.includes(name) || p.slug === name.replace(/ /g, "-")),
  );
  return match?.slug ?? null;
}
