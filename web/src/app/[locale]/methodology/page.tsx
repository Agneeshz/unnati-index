import type { Metadata } from "next";
import Link from "next/link";
import { locale as rootLocale } from "next/root-params";
import { isLocale, type Locale } from "@/i18n/config";
import { type Dictionary, getDictionary } from "@/i18n/dictionaries";
import { getGoalposts, getIndicators, METHODOLOGY } from "@/lib/data";
import { formatValue } from "@/lib/present";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.ui.methodology.title };
}

// The rules are stated in English for now; they mirror pipeline/src/unnati/scoring.py.
const RULES = [
  {
    title: "Rates, not totals",
    body: "Every ranked indicator is a rate, share or per-person value, so large states don't win just by size.",
  },
  {
    title: "Fixed goalposts",
    body: "Each indicator is scored 0-100 between two fixed goalposts. The best end is a national or SDG target where one exists, otherwise the 97.5th percentile of state values since 2015; the worst end is the 2.5th percentile. Goalposts stay fixed for a methodology version, so a score only rises when the state's own numbers improve. Very skewed per-person values (income, exports, electricity) are scored on a log scale, as UNDP does for income, so going from 10 to 100 counts as much as from 100 to 1,000.",
  },
  {
    title: "One period for everyone",
    body: "Each indicator compares states on a common period when at least 80% of them report it (for example, everyone on NFHS-5 until NFHS-6 covers most states). Otherwise each state's latest value is used, and the period is shown next to every number. Values more than six years old are not used.",
  },
  {
    title: "Pillars and the index",
    body: "A pillar is the average of its indicator scores, computed only when at least 60% of its indicators have data. The Unnati Index is the average of the eight pillars, computed only when at least six have scores. Gaps are never filled in silently.",
  },
  {
    title: "Ranks and bands",
    body: "States are ranked within peer groups (large states; North-East and Himalayan states; Union Territories) and overall. Equal scores at one decimal share a rank. Bands follow NITI Aayog's: Achiever (100), Front Runner (65-99), Performer (50-64), Aspirant (below 50).",
  },
  {
    title: "Progress",
    body: "Earlier editions are recomputed with the same goalposts, using only data for periods that had ended by then, so 'most improved' compares like with like.",
  },
];

export default async function MethodologyPage() {
  const dict = await getDictionary();
  const lang = await rootLocale();
  const locale: Locale = isLocale(lang) ? lang : "en";
  const [goalposts, indicators] = await Promise.all([getGoalposts(), getIndicators()]);
  const indicatorById = new Map(indicators.map((i) => [i.id, i]));
  const pillarIds = [...new Set(goalposts.map((g) => g.pillarId))];

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <h1 className="text-3xl font-bold tracking-tight">
        {dict.ui.methodology.title} <span className="text-muted">v{METHODOLOGY}</span>
      </h1>
      <dl className="mt-6 grid gap-6 sm:grid-cols-2">
        {RULES.map((rule) => (
          <div key={rule.title}>
            <dt className="font-semibold">{rule.title}</dt>
            <dd className="mt-1 text-muted">{rule.body}</dd>
          </div>
        ))}
      </dl>

      <h2 className="mt-12 text-2xl font-semibold">Indicators and goalposts</h2>
      {pillarIds.map((pillarId) => (
        <section key={pillarId} className="mt-6" aria-labelledby={`p-${pillarId}`}>
          <h3 id={`p-${pillarId}`} className="font-semibold">
            {dict.pillars[pillarId as keyof Dictionary["pillars"]]?.name ?? pillarId}
          </h3>
          <div className="mt-2 overflow-x-auto rounded-lg border border-border bg-surface">
            <table className="w-full min-w-[36rem] text-sm">
              <thead className="border-b border-border text-left text-muted">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Indicator
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Score 0 at
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Score 100 at
                  </th>
                </tr>
              </thead>
              <tbody>
                {goalposts
                  .filter((g) => g.pillarId === pillarId)
                  .map((g) => {
                    const indicator = indicatorById.get(g.indicatorId);
                    if (!indicator) return null;
                    return (
                      <tr key={g.indicatorId} className="border-b border-border last:border-0">
                        <th scope="row" className="px-3 py-2 text-left font-normal">
                          <Link href={`/${locale}/indicators/${g.indicatorId}`} className="hover:underline">
                            {indicator.name}
                          </Link>
                        </th>
                        <td className="px-3 py-2 tabular-nums">{formatValue(g.worst, indicator, locale)}</td>
                        <td className="px-3 py-2 tabular-nums">{formatValue(g.best, indicator, locale)}</td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}
