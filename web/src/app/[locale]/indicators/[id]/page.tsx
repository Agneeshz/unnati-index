import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { locale as rootLocale } from "next/root-params";
import { Suspense } from "react";
import { isLocale, type Locale } from "@/i18n/config";
import { type Dictionary, getDictionary } from "@/i18n/dictionaries";
import { getIndicatorObservations, getIndicators, getPlaces, type Observation } from "@/lib/data";
import { fill, formatValue } from "@/lib/present";

export async function generateStaticParams() {
  const indicators = await getIndicators();
  return indicators.map((i) => ({ id: i.id }));
}

export async function generateMetadata({ params }: PageProps<"/[locale]/indicators/[id]">): Promise<Metadata> {
  const { id } = await params;
  const indicator = (await getIndicators()).find((i) => i.id === id);
  return { title: indicator?.name ?? "Indicator" };
}

export default function IndicatorPage(props: PageProps<"/[locale]/indicators/[id]">) {
  return (
    <Suspense fallback={<div className="mx-auto max-w-5xl px-4 py-12 text-muted">…</div>}>
      <IndicatorDetail params={props.params} />
    </Suspense>
  );
}

async function IndicatorDetail({ params }: { params: PageProps<"/[locale]/indicators/[id]">["params"] }) {
  const { id } = await params;
  const dict = await getDictionary();
  const lang = await rootLocale();
  const locale: Locale = isLocale(lang) ? lang : "en";
  const [indicators, places, observations] = await Promise.all([
    getIndicators(),
    getPlaces(),
    getIndicatorObservations(id),
  ]);
  const indicator = indicators.find((i) => i.id === id);
  if (!indicator) notFound();

  const latest = new Map<string, Observation>();
  for (const o of observations) latest.set(o.slug, o); // ordered by period end
  const placeBySlug = new Map(places.map((p) => [p.slug, p]));
  // Every state and UT appears: those with data ranked first, then the rest marked "not available".
  const states = places.filter((p) => p.type !== "country");
  const withData = states
    .filter((p) => latest.has(p.slug))
    .map((p) => latest.get(p.slug) as Observation)
    .sort((a, b) => (indicator.direction === "lower_better" ? a.value - b.value : b.value - a.value));
  const withoutData = states.filter((p) => !latest.has(p.slug)).sort((a, b) => a.name.localeCompare(b.name));
  const rows = withData;
  const rankOf = (o: Observation) => withData.findIndex((x) => x.value === o.value) + 1; // ties share a rank
  const national = observations.filter((o) => o.slug === "india");
  const max = Math.max(...rows.map((r) => Math.abs(r.value)), ...national.map((r) => Math.abs(r.value)), 0);
  const directionText =
    indicator.direction === "lower_better"
      ? dict.ui.common.lowerBetter
      : indicator.direction === "higher_better"
        ? dict.ui.common.higherBetter
        : dict.ui.common.neutral;
  const pillarName = indicator.pillarId
    ? (dict.pillars[indicator.pillarId as keyof Dictionary["pillars"]]?.name ?? indicator.pillarId)
    : null;

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <p className="text-sm text-muted">
        <Link href={`/${locale}/indicators`} className="underline underline-offset-2">
          {dict.ui.indicators.title}
        </Link>
        {pillarName ? ` · ${fill(dict.ui.indicators.inPillar, { pillar: pillarName })}` : ""}
      </p>
      <h1 className="mt-1 text-3xl font-bold tracking-tight">{indicator.name}</h1>
      <p className="mt-2 max-w-3xl text-muted">{indicator.description}</p>
      <p className="mt-2 text-sm">
        {indicator.unit} · {directionText}
      </p>
      {indicator.caveat && (
        <aside className="mt-4 max-w-3xl rounded-md border border-border bg-accent-soft px-4 py-3 text-sm">
          <strong>{dict.ui.indicators.caveat}:</strong> {indicator.caveat}
        </aside>
      )}

      <section aria-labelledby="latest" className="mt-8">
        <h2 id="latest" className="text-xl font-semibold">
          {dict.ui.indicators.latest}
        </h2>
        <p className="mt-1 text-sm text-muted">
          {fill(dict.ui.indicators.coverage, { n: withData.length, total: states.length })}
        </p>
        <div className="mt-3 overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="w-full min-w-[36rem] text-sm">
            <thead className="border-b border-border text-left text-muted">
              <tr>
                <th scope="col" className="w-12 px-3 py-2 font-medium">
                  #
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {dict.ui.common.place}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {dict.ui.common.value}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {dict.ui.common.period}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => {
                const place = placeBySlug.get(o.slug)!;
                return (
                  <tr key={o.slug} className="border-b border-border last:border-0">
                    <td className="px-3 py-2 tabular-nums text-muted">{indicator.rankable ? rankOf(o) : ""}</td>
                    <th scope="row" className="px-3 py-2 text-left font-medium">
                      <Link href={`/${locale}/states/${o.slug}`} className="hover:underline">
                        {locale === "hi" && place.nameHi ? place.nameHi : place.name}
                      </Link>
                    </th>
                    <td className="px-3 py-2">
                      <ValueBar o={o} max={max} indicator={indicator} locale={locale} dict={dict} />
                    </td>
                    <td className="px-3 py-2 text-muted">{o.label}</td>
                  </tr>
                );
              })}
              {withoutData.map((place) => (
                <tr key={place.slug} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 text-muted">–</td>
                  <th scope="row" className="px-3 py-2 text-left font-medium">
                    <Link href={`/${locale}/states/${place.slug}`} className="hover:underline">
                      {locale === "hi" && place.nameHi ? place.nameHi : place.name}
                    </Link>
                  </th>
                  <td className="px-3 py-2 text-muted italic">{dict.ui.common.notAvailable}</td>
                  <td className="px-3 py-2 text-muted">–</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {national.length > 0 && (
        <section aria-labelledby="history" className="mt-10">
          <h2 id="history" className="text-xl font-semibold">
            {dict.ui.common.india}: {dict.ui.indicators.history}
          </h2>
          <div className="mt-3 overflow-x-auto rounded-lg border border-border bg-surface">
            <table className="w-full min-w-[30rem] text-sm">
              <tbody>
                {[...national].reverse().map((o) => (
                  <tr key={o.label} className="border-b border-border last:border-0">
                    <th scope="row" className="w-40 px-3 py-2 text-left font-normal text-muted">
                      {o.label}
                    </th>
                    <td className="px-3 py-2">
                      <ValueBar o={o} max={max} indicator={indicator} locale={locale} dict={dict} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

function ValueBar({
  o,
  max,
  indicator,
  locale,
  dict,
}: {
  o: Observation;
  max: number;
  indicator: { unit: string; decimals: number };
  locale: Locale;
  dict: Dictionary;
}) {
  const width = max > 0 ? Math.max(1, (Math.abs(o.value) / max) * 100) : 0;
  const text = `${formatValue(o.value, indicator, locale)}${o.provisional ? ` (${dict.ui.common.provisional})` : ""}`;
  return (
    <span className="flex items-center gap-2" title={o.note ?? undefined}>
      <span aria-hidden="true" className="relative h-2 w-24 shrink-0 rounded-full bg-border sm:w-40">
        <span className="absolute inset-y-0 left-0 rounded-full bg-accent" style={{ width: `${width}%` }} />
      </span>
      <span className="tabular-nums">{text}</span>
      {o.ciLow != null && o.ciHigh != null && (
        <span className="text-xs text-muted">
          (95% CI {o.ciLow}–{o.ciHigh})
        </span>
      )}
    </span>
  );
}
