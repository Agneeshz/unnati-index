import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { locale as rootLocale } from "next/root-params";
import { Suspense } from "react";
import { IndiaMap } from "@/components/india-map";
import { BandLabel, ScoreBar } from "@/components/score";
import { isLocale, type Locale } from "@/i18n/config";
import { getDictionary } from "@/i18n/dictionaries";
import { getIndicators, getIndices, getLatestEdition, getPlaces, getScores } from "@/lib/data";
import { fill, formatScore } from "@/lib/present";

export async function generateStaticParams() {
  return (await getIndices()).map((index) => ({ id: index.id }));
}

export async function generateMetadata({ params }: PageProps<"/[locale]/indices/[id]">): Promise<Metadata> {
  const { id } = await params;
  const index = (await getIndices()).find((i) => i.id === id);
  return { title: index?.name ?? "Index" };
}

export default function IndexPage(props: PageProps<"/[locale]/indices/[id]">) {
  return (
    <Suspense fallback={<div className="mx-auto max-w-5xl px-4 py-12 text-muted">…</div>}>
      <IndexDetail params={props.params} />
    </Suspense>
  );
}

async function IndexDetail({ params }: { params: PageProps<"/[locale]/indices/[id]">["params"] }) {
  const { id } = await params;
  const dict = await getDictionary();
  const lang = await rootLocale();
  const locale: Locale = isLocale(lang) ? lang : "en";
  const [indices, places, indicators, edition] = await Promise.all([
    getIndices(),
    getPlaces(),
    getIndicators(),
    getLatestEdition(),
  ]);
  const index = indices.find((i) => i.id === id);
  if (!index || edition == null) notFound();
  const scores = (await getScores(edition, "composite")).filter((s) => s.key === id);
  const bySlug = new Map(scores.map((s) => [s.slug, s]));
  const indicatorName = new Map(indicators.map((i) => [i.id, i.name]));
  const states = places.filter((p) => p.type !== "country");
  const ranked = states
    .filter((p) => bySlug.get(p.slug)?.score != null)
    .sort((a, b) => (bySlug.get(a.slug)?.rank ?? 0) - (bySlug.get(b.slug)?.rank ?? 0));
  const missing = states.filter((p) => bySlug.get(p.slug)?.score == null).sort((a, b) => a.name.localeCompare(b.name));
  const india = bySlug.get("india");
  const name = (p: (typeof places)[number]) => (locale === "hi" && p.nameHi ? p.nameHi : p.name);

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <p className="text-sm text-muted">
        <Link href={`/${locale}/indices`} className="underline underline-offset-2">
          {dict.ui.indices.title}
        </Link>
        {index.inspiredBy ? ` · ${fill(dict.ui.indices.inspiredBy, { name: index.inspiredBy })}` : ""}
      </p>
      <h1 className="mt-1 text-3xl font-bold tracking-tight">{index.name}</h1>
      <p className="mt-2 max-w-3xl text-muted">{index.description}</p>
      {india?.score != null && (
        <p className="mt-2 text-sm">
          {dict.ui.common.india}: <strong className="tabular-nums">{formatScore(india.score, locale)}</strong> / 100
        </p>
      )}
      {index.caveat && (
        <aside className="mt-4 max-w-3xl rounded-md border border-border bg-accent-soft px-4 py-3 text-sm">
          <strong>{dict.ui.indicators.caveat}:</strong> {index.caveat}
        </aside>
      )}

      <div className="mt-6 grid gap-8 lg:grid-cols-2">
        <IndiaMap
          title={index.name}
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
            {dict.ui.indices.method}
          </h2>
          <p className="mt-2 text-sm text-muted">{index.method}</p>
          <h3 className="mt-5 font-semibold">{dict.ui.indices.components}</h3>
          <dl className="mt-2 space-y-3 text-sm">
            {index.components.map(({ dimension, indicators: members }) => (
              <div key={dimension}>
                <dt className="font-medium">{dimension}</dt>
                <dd>
                  <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
                    {members.map((m) => (
                      <li key={m}>
                        <Link href={`/${locale}/indicators/${m}`} className="text-muted underline underline-offset-2">
                          {indicatorName.get(m) ?? m}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </dd>
              </div>
            ))}
          </dl>
        </section>
      </div>

      <section aria-labelledby="ranking" className="mt-10">
        <h2 id="ranking" className="text-xl font-semibold">
          {index.name} {edition}
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
                  <td className="px-3 py-2 text-muted italic">{dict.ui.common.notAvailable}</td>
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
