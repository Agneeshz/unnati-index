import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { locale as rootLocale } from "next/root-params";
import { Suspense } from "react";
import { BandLabel, RankChange, ScoreBar } from "@/components/score";
import { isLocale, type Locale } from "@/i18n/config";
import { type Dictionary, getDictionary } from "@/i18n/dictionaries";
import {
  COMPOSITE,
  getIndicators,
  getIndices,
  getLatestEdition,
  getOfficeHolders,
  getPillars,
  getPlaceObservations,
  getPlaces,
  getScores,
  type Observation,
  type Place,
  type ScoreRow,
} from "@/lib/data";
import { fill, formatScore, formatValue } from "@/lib/present";

export async function generateStaticParams() {
  const places = await getPlaces();
  return places.filter((p) => p.type !== "country").map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: PageProps<"/[locale]/states/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const place = (await getPlaces()).find((p) => p.slug === slug);
  return { title: place?.name ?? "State" };
}

export default function StatePage(props: PageProps<"/[locale]/states/[slug]">) {
  return (
    <Suspense fallback={<div className="mx-auto max-w-5xl px-4 py-12 text-muted">…</div>}>
      <ReportCard params={props.params} />
    </Suspense>
  );
}

function placeName(place: Place, locale: Locale) {
  return locale === "hi" && place.nameHi ? place.nameHi : place.name;
}

async function ReportCard({ params }: { params: PageProps<"/[locale]/states/[slug]">["params"] }) {
  const { slug } = await params;
  const dict = await getDictionary();
  const lang = await rootLocale();
  const locale: Locale = isLocale(lang) ? lang : "en";
  const places = await getPlaces();
  const place = places.find((p) => p.slug === slug && p.type !== "country");
  if (!place) notFound();
  const edition = await getLatestEdition();
  if (edition == null) notFound();
  const [scores, pillars, indicators, observations, indices] = await Promise.all([
    getScores(edition),
    getPillars(),
    getIndicators(),
    getPlaceObservations(slug),
    getIndices(),
  ]);

  const mine = scores.filter((s) => s.slug === slug);
  const composite = mine.find((s) => s.level === "composite" && s.key === COMPOSITE);
  const peers = places.filter((p) => p.peerGroup === place.peerGroup).map((p) => p.slug);
  const peerTotal = scores.filter(
    (s) => s.level === "composite" && s.score != null && peers.includes(s.slug),
  ).length;
  const indicatorById = new Map(indicators.map((i) => [i.id, i]));

  // The value each indicator score used (same period as the score), else the latest value.
  const latestByIndicator = new Map<string, Observation>();
  for (const o of observations) latestByIndicator.set(o.indicatorId, o);
  const usedValue = (indicatorId: string, period: string | null) =>
    observations.find((o) => o.indicatorId === indicatorId && o.label === period) ??
    latestByIndicator.get(indicatorId);

  const indicatorScores = mine
    .filter((s) => s.level === "indicator" && s.score != null)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const strengths = indicatorScores.slice(0, 5);
  const weaknesses = indicatorScores.slice(-5).reverse();

  // Office-holders: the twelve months before the median end of the data used in this card.
  const ends = indicatorScores
    .map((s) => usedValue(s.key, s.periodLabel)?.end)
    .filter((e): e is string => Boolean(e))
    .sort();
  const dataEnd = ends.length ? ends[Math.floor(ends.length / 2)] : new Date().toISOString().slice(0, 10);
  const dataYear = Number(dataEnd.slice(0, 4));
  const leaders = await getOfficeHolders(slug, `${dataYear}-01-01`, `${dataYear}-12-31`);

  const pillarAverage = (pillarId: string, slugs: string[]) => {
    const values = scores
      .filter((s) => s.level === "pillar" && s.key === pillarId && s.score != null && slugs.includes(s.slug))
      .map((s) => s.score as number);
    return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <p className="text-sm text-muted">
        <Link href={`/${locale}/rankings`} className="underline underline-offset-2">
          {dict.ui.nav.rankings}
        </Link>{" "}
        · {place.peerGroup ? dict.ui.peerGroups[place.peerGroup] : ""}
      </p>
      <h1 className="mt-1 text-3xl font-bold tracking-tight">{placeName(place, locale)}</h1>
      <p className="text-muted">
        {dict.ui.state.reportCard} · {fill(dict.ui.common.edition, { year: edition })}
      </p>

      <section aria-label={dict.site.name} className="mt-6 rounded-lg border border-border bg-surface p-5">
        {composite?.score != null ? (
          <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
            <div>
              <p className="text-sm text-muted">{dict.site.name}</p>
              <p className="text-5xl font-bold tabular-nums">
                {formatScore(composite.score, locale)}
                <span className="ml-1 text-base font-normal text-muted">/ 100</span>
              </p>
            </div>
            <div className="space-y-1">
              <BandLabel score={composite.score} dict={dict} />
              <p>
                {fill(dict.ui.state.rankOf, {
                  rank: composite.rankPeer ?? "–",
                  total: peerTotal,
                  group: place.peerGroup ? dict.ui.peerGroups[place.peerGroup] : "",
                })}{" "}
                <RankChange rank={composite.rankPeer} previous={composite.rankPeerPrev} dict={dict} />
              </p>
            </div>
          </div>
        ) : (
          <p className="text-muted">{dict.ui.state.notScored}</p>
        )}
      </section>

      <section aria-labelledby="pillars" className="mt-10">
        <h2 id="pillars" className="text-xl font-semibold">
          {dict.ui.state.pillarsTitle}
        </h2>
        <div className="mt-3 overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="w-full min-w-[34rem] text-sm">
            <thead className="border-b border-border text-left text-muted">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium" />
                <th scope="col" className="px-3 py-2 font-medium">
                  {placeName(place, locale)}
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  {dict.ui.state.peerAverage}
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  {dict.ui.common.peerRank}
                </th>
              </tr>
            </thead>
            <tbody>
              {pillars.map((p) => {
                const s = mine.find((r) => r.level === "pillar" && r.key === p.id);
                const avg = pillarAverage(p.id, peers);
                return (
                  <tr key={p.id} className="border-b border-border last:border-0">
                    <th scope="row" className="px-3 py-2 text-left font-medium">
                      {dict.pillars[p.id as keyof Dictionary["pillars"]]?.name ?? p.name}
                    </th>
                    <td className="px-3 py-2">
                      {s?.score != null ? (
                        <ScoreBar score={s.score} locale={locale} />
                      ) : (
                        <span className="text-muted">{dict.ui.common.noScore}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-muted">
                      {avg != null ? formatScore(avg, locale) : "–"}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{s?.rankPeer ?? "–"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="indices" className="mt-10">
        <h2 id="indices" className="text-xl font-semibold">
          {dict.ui.indices.stateTitle}
        </h2>
        <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {indices.map((index) => {
            const s = mine.find((r) => r.level === "composite" && r.key === index.id);
            return (
              <li key={index.id} className="rounded-md border border-border bg-surface px-3 py-2">
                <Link href={`/${locale}/indices/${index.id}`} className="text-sm font-medium hover:underline">
                  {index.name}
                </Link>
                <div className="mt-1 flex items-center justify-between gap-2">
                  {s?.score != null ? (
                    <>
                      <ScoreBar score={s.score} locale={locale} />
                      <span className="text-xs text-muted tabular-nums">
                        #{s.rankPeer} {place.peerGroup ? `· ${dict.ui.peerGroups[place.peerGroup]}` : ""}
                      </span>
                    </>
                  ) : (
                    <span className="text-sm text-muted italic">{dict.ui.common.notAvailable}</span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <div className="mt-10 grid gap-8 sm:grid-cols-2">
        {[
          { title: dict.ui.state.strengths, rows: strengths },
          { title: dict.ui.state.weaknesses, rows: weaknesses },
        ].map(({ title, rows }) => (
          <section key={title} aria-label={title}>
            <h2 className="text-xl font-semibold">{title}</h2>
            <ul className="mt-3 space-y-2">
              {rows.map((s) => {
                const indicator = indicatorById.get(s.key);
                const value = usedValue(s.key, s.periodLabel);
                if (!indicator) return null;
                return (
                  <li key={s.key} className="rounded-md border border-border bg-surface px-3 py-2">
                    <Link href={`/${locale}/indicators/${s.key}`} className="font-medium hover:underline">
                      {indicator.name}
                    </Link>
                    <p className="text-sm text-muted">
                      {value ? `${formatValue(value.value, indicator, locale)} (${value.label})` : ""} ·{" "}
                      {dict.ui.common.score} {formatScore(s.score ?? 0, locale)}
                    </p>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>

      <Leaders dict={dict} leaders={leaders} year={dataYear} />

      <IndicatorTable
        dict={dict}
        locale={locale}
        scores={mine}
        observations={observations}
        indicators={indicators}
        pillars={pillars}
      />
    </div>
  );
}

function Leaders({
  dict,
  leaders,
  year,
}: {
  dict: Dictionary;
  leaders: Awaited<ReturnType<typeof getOfficeHolders>>;
  year: number;
}) {
  return (
    <section aria-labelledby="leaders" className="mt-10">
      <h2 id="leaders" className="text-xl font-semibold">
        {dict.ui.state.leadersTitle}
      </h2>
      <p className="mt-1 text-sm text-muted">{fill(dict.ui.state.leadersIntro, { period: year })}</p>
      {leaders.length === 0 ? (
        <p className="mt-3 text-muted">{dict.ui.state.noLeaders}</p>
      ) : (
        <ul className="mt-3 grid gap-3 sm:grid-cols-2">
          {leaders.map((l) => (
            <li key={`${l.title}-${l.person}-${l.start}`} className="rounded-md border border-border bg-surface px-3 py-2">
              <p className="text-sm text-muted">{l.title}</p>
              <p className="font-medium">{l.person}</p>
              <p className="text-sm text-muted">
                {l.start} – {l.end ?? "present"}
                {l.party ? ` · ${l.party}` : ""} ·{" "}
                <a href={l.sourceUrl} className="underline underline-offset-2" rel="noopener">
                  {dict.ui.common.source}
                </a>
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function IndicatorTable({
  dict,
  locale,
  scores,
  observations,
  indicators,
  pillars,
}: {
  dict: Dictionary;
  locale: Locale;
  scores: ScoreRow[];
  observations: Observation[];
  indicators: Awaited<ReturnType<typeof getIndicators>>;
  pillars: Awaited<ReturnType<typeof getPillars>>;
}) {
  const latest = new Map<string, Observation>();
  for (const o of observations) latest.set(o.indicatorId, o);
  const groups = [
    ...pillars.map((p) => ({ id: p.id, name: dict.pillars[p.id as keyof Dictionary["pillars"]]?.name ?? p.name })),
    { id: "", name: dict.ui.indicators.title },
  ];
  return (
    <section aria-labelledby="all-indicators" className="mt-10">
      <h2 id="all-indicators" className="text-xl font-semibold">
        {dict.ui.state.indicatorsTitle}
      </h2>
      {groups.map((g) => {
        const rows = indicators.filter((i) => (i.pillarId ?? "") === g.id && latest.has(i.id));
        if (!rows.length) return null;
        return (
          <div key={g.id || "other"} className="mt-5">
            <h3 className="font-semibold">{g.name}</h3>
            <div className="mt-2 overflow-x-auto rounded-lg border border-border bg-surface">
              <table className="w-full min-w-[34rem] text-sm">
                <tbody>
                  {rows.map((i) => {
                    const s = scores.find((r) => r.level === "indicator" && r.key === i.id);
                    const newest = latest.get(i.id) as Observation;
                    // Show the value the score used; mention a newer one if the score is on a common
                    // older period (e.g. NFHS-5 while some states already have NFHS-6).
                    const scored = s?.periodLabel
                      ? observations.find((x) => x.indicatorId === i.id && x.label === s.periodLabel)
                      : undefined;
                    const o = scored ?? newest;
                    return (
                      <tr key={i.id} className="border-b border-border last:border-0">
                        <th scope="row" className="w-1/2 px-3 py-2 text-left font-normal">
                          <Link href={`/${locale}/indicators/${i.id}`} className="hover:underline">
                            {i.name}
                          </Link>
                        </th>
                        <td className="px-3 py-2 tabular-nums">
                          {formatValue(o.value, i, locale)}
                          {o.provisional ? ` (${dict.ui.common.provisional})` : ""}
                        </td>
                        <td className="px-3 py-2 text-muted">
                          {o.label}
                          {scored && newest.label !== scored.label
                            ? ` · ${newest.label}: ${formatValue(newest.value, i, locale)}`
                            : ""}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-muted">
                          {s?.score != null ? formatScore(s.score, locale) : ""}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </section>
  );
}
