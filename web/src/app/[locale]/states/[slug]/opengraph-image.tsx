import { COMPOSITE, getLatestEdition, getPillars, getPlaces, getScores } from "@/lib/data";
import { OG_SIZE, OG_TYPE, ogCard } from "@/lib/og";
import { band } from "@/lib/present";

export const alt = "State report card on the Unnati Index";
export const size = OG_SIZE;
export const contentType = OG_TYPE;

const GROUP = { large_state: "large states", ne_himalayan_state: "North-East & Himalayan states", ut: "Union Territories" };
const BAND = { achiever: "Achiever", frontRunner: "Front Runner", performer: "Performer", aspirant: "Aspirant" };

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const [places, edition, pillars] = await Promise.all([getPlaces(), getLatestEdition(), getPillars()]);
  const place = places.find((p) => p.slug === slug);
  const scores = edition == null ? [] : await getScores(edition);
  const mine = scores.filter((s) => s.slug === slug);
  const composite = mine.find((s) => s.level === "composite" && s.key === COMPOSITE);
  const group = place?.peerGroup ? GROUP[place.peerGroup] : null;
  const total = scores.filter(
    (s) =>
      s.level === "composite" &&
      s.key === COMPOSITE &&
      s.score != null &&
      places.find((p) => p.slug === s.slug)?.peerGroup === place?.peerGroup,
  ).length;
  // Headline: the pillar where the state ranks best in its group.
  const top = mine
    .filter((s) => s.level === "pillar" && s.rankPeer != null)
    .sort((a, b) => (a.rankPeer as number) - (b.rankPeer as number) || (b.score ?? 0) - (a.score ?? 0))[0];
  const pillarName = pillars.find((p) => p.id === top?.key)?.name;
  const lines = [
    composite?.rankPeer != null && group ? `#${composite.rankPeer} of ${total} ${group}` : "",
    top && pillarName && group ? `Best: #${top.rankPeer} in ${pillarName} among ${group}` : "",
  ].filter(Boolean);
  return ogCard({
    eyebrow: edition ? `${edition} report card` : "Report card",
    title: place?.name ?? "State report card",
    big: composite?.score != null ? composite.score.toFixed(1) : undefined,
    bigNote: composite?.score != null ? `/ 100 · ${BAND[band(composite.score)]}` : undefined,
    lines,
  });
}
