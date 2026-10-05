import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { locale as rootLocale } from "next/root-params";
import { Suspense } from "react";
import { IndiaMap } from "@/components/india-map";
import { BandLabel, ScoreBar } from "@/components/score";
import { isLocale, type Locale } from "@/i18n/config";
import { type Dictionary, getDictionary } from "@/i18n/dictionaries";
import { getGoalposts, getIndicators, getLatestEdition, getPillars, getPlaces, getScores } from "@/lib/data";
import { fill, formatScore, formatValue } from "@/lib/present";

export async function generateStaticParams() {
  return (await getPillars()).map((p) => ({ id: p.id }));
}

export async function generateMetadata({ params }: PageProps<"/[locale]/pillars/[id]">): Promise<Metadata> {
  const { id } = await params;
  const dict = await getDictionary();
  const pillar = (await getPillars()).find((p) => p.id === id);
  return { title: dict.pillars[id as keyof Dictionary["pillars"]]?.name ?? pillar?.name ?? "Pillar" };
}

export default function PillarPage(props: PageProps<"/[locale]/pillars/[id]">) {
  return (
    <Suspense fallback={<div className="mx-auto max-w-5xl px-4 py-12 text-muted">…</div>}>
      <PillarDetail params={props.params} />
    </Suspense>
  );
}

async function PillarDetail({ params }: { params: PageProps<"/[locale]/pillars/[id]">["params"] }) {
  const { id } = await params;
  const dict = await getDictionary();
  const lang = await rootLocale();
  const locale: Locale = isLocale(lang) ? lang : "en";
  const [pillars, places, indicators, goalposts, edition] = await Promise.all([
    getPillars(),
    getPlaces(),
    getIndicators(),
    getGoalposts(),
    getLatestEdition(),
  ]);
  const pillar = pillars.find((p) => p.id === id);
  if (!pillar || edition == null) notFound();
  const text = dict.pillars[id as keyof Dictionary["pillars"]];
  const title = text?.name ?? pillar.name;
  const scores = (await getScores(edition, "pillar")).filter((s) => s.key === id);
  const bySlug = new Map(scores.map((s) => [s.slug, s]));
  const states = places.filter((p) => p.type !== "country");
  const ranked = states
    .filter((p) => bySlug.get(p.slug)?.score != null)
    .sort((a, b) => (bySlug.get(a.slug)?.rank ?? 0) - (bySlug.get(b.slug)?.rank ?? 0));
  const missing = states.filter((p) => bySlug.get(p.slug)?.score == null).sort((a, b) => a.name.localeCompare(b.name));
  const india = bySlug.get("india");
  const members = indicators.filter((i) => i.pillarId === id);
  const goal = new Map(goalposts.filter((g) => g.pillarId === id).map((g) => [g.indicatorId, g]));
  const name = (p: (typeof places)[number]) => (locale === "hi" && p.nameHi ? p.nameHi : p.name);

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <p className="text-sm text-muted">
        <Link href={`/${locale}/rankings`} className="underline underline-offset-2">
          {dict.ui.nav.rankings}
        </Link>{" "}
        · {dict.ui.pillar.eyebrow}
      </p>
      <h1 className="mt-1 text-3xl font-bold tracking-tight">{title}</h1>
      <p className="mt-2 max-w-3xl text-muted">{text?.description ?? pillar.description}</p>
      {india?.score != null && (
        <p className="mt-2 text-sm">
          {dict.ui.common.india}: <strong className="tabular-nums">{formatScore(india.score, locale)}</strong> / 100
        </p>
      )}

      <div className="mt-6 grid gap-8 lg:grid-cols-2">
        <IndiaMap
          title={title}
          data={Object.fromEntries(
            ranked.map((p) => {
              const s = bySlug.get(p.slug)!;
              return [p.slug, { value: s.score as number, label: `${formatScore(s.score as number, locale)} / 100` }];
            }),
          )}
          formatBreak={(v) => formatScore(v, locale)}
          notAvailable={dict.ui.common.notAvailable}
          note={dict.ui.indices.scaleNote}
          hrefFor={(slug) => `/${locale}/states/${slug}`}
        />
        <section aria-labelledby="method">
          <h2 id="method" className="text-xl font-semibold">
            {dict.ui.indices.components}
          </h2>
          <p className="mt-2 text-sm text-muted">{dict.ui.pillar.method}</p>
          <ul className="mt-3 space-y-2 text-sm">
            {members.map((i) => {
              const g = goal.get(i.id);
              return (
                <li key={i.id} className="rounded-md border border-border bg-surface px-3 py-2">
                  <Link href={`/${locale}/indicators/${i.id}`} className="font-medium hover:underline">
                    {i.name}
                  </Link>
                  <span className="block text-muted">
                    {i.direction === "lower_better" ? dict.ui.common.lowerBetter : dict.ui.common.higherBetter}
                    {g
                      ? ` · ${fill(dict.ui.pillar.goalposts, {
                          worst: formatValue(g.worst, i, locale),
                          best: formatValue(g.best, i, locale),
                        })}`
                      : ""}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      </div>

      <section aria-labelledby="ranking" className="mt-10">
        <h2 id="ranking" className="text-xl font-semibold">
          {title} {edition}
        </h2>
        <p className="mt-1 text-sm text-muted">
          {fill(dict.ui.indicators.coverage, { n: ranked.length, total: states.length })}
        </p>
        <div className="mt-3 overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="w-full min-w-[36rem] text-sm">
            <thead className="border-b border-border text-left text-muted">
              <tr>
                <th scope="col" className="w-12 px-3 py-2 font-medium">
                  {dict.ui.common.rank}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {dict.ui.common.place}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {dict.ui.indices.outOf100}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {dict.ui.common.peerRank}
                </th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((p) => {
                const s = bySlug.get(p.slug)!;
                return (
                  <tr key={p.slug} className="border-b border-border last:border-0">
                    <td className="px-3 py-2 tabular-nums">{s.rank}</td>
                    <th scope="row" className="px-3 py-2 text-left font-medium">
                      <Link href={`/${locale}/states/${p.slug}`} className="hover:underline">
                        {name(p)}
                      </Link>
                    </th>
                    <td className="px-3 py-2">
                      <span className="flex flex-wrap items-center gap-2">
                        <ScoreBar score={s.score} locale={locale} />
                        <BandLabel score={s.score} dict={dict} />
                      </span>
                    </td>
                    <td className="px-3 py-2 tabular-nums text-muted">
                      {s.rankPeer} · {p.peerGroup ? dict.ui.peerGroups[p.peerGroup] : ""}
                    </td>
                  </tr>
                );
              })}
              {missing.map((p) => (
                <tr key={p.slug} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 text-muted">–</td>
                  <th scope="row" className="px-3 py-2 text-left font-medium">
                    <Link href={`/${locale}/states/${p.slug}`} className="hover:underline">
                      {name(p)}
                    </Link>
                  </th>
                  <td className="px-3 py-2 text-muted italic">{dict.ui.common.noScore}</td>
                  <td className="px-3 py-2 text-muted">–</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
