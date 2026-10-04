import Link from "next/link";
import { locale as rootLocale } from "next/root-params";
import { BandLabel, ScoreBar } from "@/components/score";
import { isLocale, type Locale } from "@/i18n/config";
import { type Dictionary, getDictionary } from "@/i18n/dictionaries";
import {
  COMPOSITE,
  getCompositeHistory,
  getDatasets,
  getLatestEdition,
  getPlaces,
  getScores,
  type Place,
} from "@/lib/data";
import { formatNumber } from "@/lib/format";
import { fill, PEER_GROUPS } from "@/lib/present";

const PILLARS: (keyof Dictionary["pillars"])[] = [
  "economy-jobs",
  "health",
  "education",
  "safety-justice",
  "governance-fiscal",
  "infrastructure-digital",
  "environment",
  "inclusion",
];

export default async function HomePage() {
  const dict = await getDictionary();
  const lang = await rootLocale();
  const locale: Locale = isLocale(lang) ? lang : "en";
  const edition = await getLatestEdition();
  const [places, scores, history, datasets] = await Promise.all([
    getPlaces(),
    edition != null ? getScores(edition, "composite") : Promise.resolve([]),
    getCompositeHistory(),
    getDatasets(),
  ]);
  const name = (p: Place) => (locale === "hi" && p.nameHi ? p.nameHi : p.name);
  const placeBySlug = new Map(places.map((p) => [p.slug, p]));
  const composite = new Map(scores.filter((s) => s.key === COMPOSITE).map((s) => [s.slug, s]));

  // Most improved: change since the edition three years earlier (same methodology, same goalposts).
  const baseEdition = edition != null ? edition - 3 : null;
  const base = new Map(history.filter((h) => h.edition === baseEdition).map((h) => [h.slug, h.score]));
  const improved = history
    .filter((h) => h.edition === edition && base.has(h.slug) && placeBySlug.get(h.slug)?.type !== "country")
    .map((h) => ({ slug: h.slug, change: h.score - (base.get(h.slug) as number) }))
    .sort((a, b) => b.change - a.change)
    .slice(0, 5);

  return (
    <div className="mx-auto max-w-5xl px-4">
      <section className="py-12 sm:py-16">
        <h1 className="max-w-3xl text-3xl font-bold tracking-tight text-balance sm:text-5xl">
          {dict.site.tagline}
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-muted">{dict.site.description}</p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            href={`/${locale}/rankings`}
            className="rounded-md bg-accent px-4 py-2 font-medium text-surface hover:opacity-90"
          >
            {dict.ui.nav.rankings}
          </Link>
          <Link
            href={`/${locale}/indicators`}
            className="rounded-md border border-border px-4 py-2 font-medium hover:bg-accent-soft"
          >
            {dict.ui.nav.indicators}
          </Link>
        </div>
      </section>

      {edition != null && (
        <section aria-labelledby="leaders" className="border-t border-border py-10">
          <h2 id="leaders" className="text-2xl font-semibold">
            {fill(dict.ui.home.leadersTitle, { year: edition })}
          </h2>
          <p className="mt-2 max-w-3xl text-muted">{dict.ui.home.leadersIntro}</p>
          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            {PEER_GROUPS.map((group) => {
              const ranked = places
                .filter((p) => p.peerGroup === group && composite.get(p.slug)?.score != null)
                .sort((a, b) => (composite.get(a.slug)?.rankPeer ?? 0) - (composite.get(b.slug)?.rankPeer ?? 0));
              const top = ranked.slice(0, 3);
              const bottom = ranked.length > 6 ? ranked.slice(-3) : [];
              return (
                <div key={group} className="rounded-lg border border-border bg-surface p-4">
                  <h3 className="font-semibold">{dict.ui.peerGroups[group]}</h3>
                  {[
                    { label: dict.ui.home.top, list: top },
                    { label: dict.ui.home.bottom, list: bottom },
                  ]
                    .filter(({ list }) => list.length)
                    .map(({ label, list }) => (
                      <div key={label} className="mt-3">
                        <p className="text-xs font-medium tracking-wide text-muted uppercase">{label}</p>
                        <ol className="mt-1 space-y-1.5">
                          {list.map((p) => {
                            const s = composite.get(p.slug)!;
                            return (
                              <li key={p.slug} className="flex items-center justify-between gap-2 text-sm">
                                <Link href={`/${locale}/states/${p.slug}`} className="truncate hover:underline">
                                  <span className="tabular-nums text-muted">{s.rankPeer}.</span> {name(p)}
                                </Link>
                                <ScoreBar score={s.score} locale={locale} />
                              </li>
                            );
                          })}
                        </ol>
                      </div>
                    ))}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {improved.length > 0 && baseEdition != null && (
        <section aria-labelledby="improved" className="border-t border-border py-10">
          <h2 id="improved" className="text-2xl font-semibold">
            {fill(dict.ui.home.improvedTitle, { year: baseEdition })}
          </h2>
          <p className="mt-2 max-w-3xl text-muted">{dict.ui.home.improvedIntro}</p>
          <ol className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
            {improved.map((row) => {
              const place = placeBySlug.get(row.slug)!;
              const now = composite.get(row.slug)?.score ?? null;
              return (
                <li key={row.slug} className="rounded-lg border border-border bg-surface p-3">
                  <Link href={`/${locale}/states/${row.slug}`} className="font-medium hover:underline">
                    {name(place)}
                  </Link>
                  <p className="text-2xl font-semibold tabular-nums">
                    {row.change >= 0 ? "+" : "−"}
                    {formatNumber(Math.abs(row.change), 1, locale)}
                  </p>
                  <BandLabel score={now} dict={dict} />
                </li>
              );
            })}
          </ol>
        </section>
      )}

      <section aria-labelledby="pillars" className="border-t border-border py-10">
        <h2 id="pillars" className="text-2xl font-semibold">
          {dict.home.pillarsTitle}
        </h2>
        <p className="mt-2 max-w-3xl text-muted">{dict.home.pillarsIntro}</p>
        <ol className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PILLARS.map((id, index) => (
            <li key={id} className="rounded-lg border border-border bg-surface p-4">
              <span className="text-sm font-medium text-accent">{index + 1}</span>
              <h3 className="mt-1 font-semibold">{dict.pillars[id].name}</h3>
              <p className="mt-1 text-sm text-muted">{dict.pillars[id].description}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="updates" className="border-t border-border py-10">
        <h2 id="updates" className="text-2xl font-semibold">
          {dict.ui.home.updatesTitle}
        </h2>
        <ul className="mt-4 divide-y divide-border rounded-lg border border-border bg-surface">
          {datasets
            .filter((d) => d.lastChanged)
            .slice(0, 6)
            .map((d) => (
              <li key={d.id} className="flex flex-wrap items-baseline justify-between gap-2 px-4 py-2 text-sm">
                <span>
                  <span className="font-medium">{d.title}</span> <span className="text-muted">· {d.source}</span>
                </span>
                <time dateTime={d.lastChanged!} className="text-muted">
                  {d.lastChanged!.slice(0, 10)}
                </time>
              </li>
            ))}
        </ul>
        <p className="mt-3 text-sm">
          <Link href={`/${locale}/sources`} className="underline underline-offset-2">
            {dict.ui.nav.sources}
          </Link>
        </p>
      </section>

      <section aria-labelledby="principles" className="border-t border-border py-10">
        <h2 id="principles" className="text-2xl font-semibold">
          {dict.home.principlesTitle}
        </h2>
        <dl className="mt-6 grid gap-6 sm:grid-cols-2">
          {dict.home.principles.map((principle) => (
            <div key={principle.title}>
              <dt className="font-semibold">{principle.title}</dt>
              <dd className="mt-1 text-muted">{principle.body}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
