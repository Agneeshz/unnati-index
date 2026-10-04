import { COMPOSITE, getLatestEdition, getPlaces, getScores } from "@/lib/data";
import { OG_SIZE, OG_TYPE, ogCard } from "@/lib/og";

export const alt = "Unnati Index: India's progress, state by state";
export const size = OG_SIZE;
export const contentType = OG_TYPE;

export default async function Image() {
  const [places, edition] = await Promise.all([getPlaces(), getLatestEdition()]);
  const scores = edition == null ? [] : await getScores(edition, "composite");
  const large = new Set(places.filter((p) => p.peerGroup === "large_state").map((p) => p.slug));
  const names = new Map(places.map((p) => [p.slug, p.name]));
  const top = scores
    .filter((s) => s.key === COMPOSITE && s.score != null && large.has(s.slug))
    .sort((a, b) => (b.score as number) - (a.score as number))
    .slice(0, 3);
  return ogCard({
    eyebrow: edition ? `${edition} rankings` : "Rankings",
    title: "India's progress, state by state",
    lines: top.length ? ["Leading large states"] : [],
    rows: top.map((s, i) => ({ label: `${i + 1}. ${names.get(s.slug)}`, value: `${(s.score as number).toFixed(1)} / 100` })),
  });
}
