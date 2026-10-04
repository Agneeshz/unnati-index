import { getIndicatorObservations, getIndicators, getPlaces } from "@/lib/data";
import { OG_SIZE, OG_TYPE, ogCard } from "@/lib/og";
import { formatValue } from "@/lib/present";

export const alt = "Indicator ranking on the Unnati Index";
export const size = OG_SIZE;
export const contentType = OG_TYPE;

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [indicators, places, observations] = await Promise.all([
    getIndicators(),
    getPlaces(),
    getIndicatorObservations(id),
  ]);
  const indicator = indicators.find((i) => i.id === id);
  if (!indicator) return ogCard({ eyebrow: "Indicators", title: "Indicator" });
  const names = new Map(places.map((p) => [p.slug, p.name]));
  // The most recent period that at least half the states and UTs report.
  const counts = new Map<string, { n: number; end: string }>();
  for (const o of observations)
    if (o.slug !== "india") counts.set(o.label, { n: (counts.get(o.label)?.n ?? 0) + 1, end: o.end });
  const period = [...counts]
    .filter(([, c]) => c.n >= 18)
    .sort((a, b) => b[1].end.localeCompare(a[1].end))[0]?.[0];
  const current = observations.filter((o) => o.label === period);
  const india = current.find((o) => o.slug === "india");
  const ranked = indicator.rankable && indicator.direction !== "neutral";
  const sign = indicator.direction === "lower_better" ? 1 : -1;
  const top = ranked
    ? current
        .filter((o) => o.slug !== "india" && names.has(o.slug))
        .sort((a, b) => sign * (a.value - b.value))
        .slice(0, 3)
    : [];
  return ogCard({
    eyebrow: period ? `Indicator · ${period}` : "Indicator",
    title: indicator.name,
    lines: india ? [`India: ${formatValue(india.value, indicator, "en")}`] : [],
    rows: top.map((o, i) => ({
      label: `${i + 1}. ${names.get(o.slug)}`,
      value: formatValue(o.value, indicator, "en"),
    })),
  });
}
