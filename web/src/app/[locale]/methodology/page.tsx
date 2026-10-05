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
        {dict.ui.methodology.rules.map((rule) => (
          <div key={rule.title}>
            <dt className="font-semibold">{rule.title}</dt>
            <dd className="mt-1 text-muted">{rule.body}</dd>
          </div>
        ))}
      </dl>

      <h2 className="mt-12 text-2xl font-semibold">{dict.ui.methodology.goalpostsTitle}</h2>
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
                    {dict.ui.methodology.indicator}
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    {dict.ui.methodology.score0}
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    {dict.ui.methodology.score100}
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
