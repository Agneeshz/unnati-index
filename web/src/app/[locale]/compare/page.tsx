import type { Metadata } from "next";
import Link from "next/link";
import { locale as rootLocale } from "next/root-params";
import { Suspense } from "react";
import { BandLabel, ScoreBar } from "@/components/score";
import { isLocale, type Locale } from "@/i18n/config";
import { type Dictionary, getDictionary } from "@/i18n/dictionaries";
import { bestIndex, compareHref, MAX_COMPARE, neighbours, parseSelection, POPULAR } from "@/lib/compare";
import {
  COMPOSITE,
  getCategories,
  getIndicators,
  getIndices,
  getLatestEdition,
  getPillars,
  getPlaceObservations,
  getPlaces,
  getScores,
  type Observation,
  type Place,
  type ScoreRow,
} from "@/lib/data";
import { fill, formatScore, formatValue } from "@/lib/present";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.ui.compare.title, description: dict.ui.compare.intro };
}

export default function ComparePage(props: PageProps<"/[locale]/compare">) {
  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <Suspense fallback={<p className="text-muted">…</p>}>
        <Compare searchParams={props.searchParams} />
      </Suspense>
    </div>
  );
}

function name(place: Place, locale: Locale) {
  return locale === "hi" && place.nameHi ? place.nameHi : place.name;
}

/** Marks the best cell in a row with weight and a star, plus words for screen readers. */
function Best({ on, dict, children }: { on: boolean; dict: Dictionary; children: React.ReactNode }) {
  if (!on) return <>{children}</>;
  return (
    <span className="font-semibold">
      {children}{" "}
      <span aria-hidden="true" className="text-accent" title={dict.ui.compare.best}>
        ★
      </span>
      <span className="sr-only">({dict.ui.compare.best})</span>
    </span>
  );
}

async function Compare({ searchParams }: { searchParams: PageProps<"/[locale]/compare">["searchParams"] }) {
  const [dict, lang, places, query] = await Promise.all([getDictionary(), rootLocale(), getPlaces(), searchParams]);
  const locale: Locale = isLocale(lang) ? lang : "en";
  const choosable = places.filter((p) => p.type !== "country");
  const bySlug = new Map(places.map((p) => [p.slug, p]));
  const selected = parseSelection(query.e, choosable.map((p) => p.slug));
  const chosen = selected.map((s) => bySlug.get(s) as Place);

  return (
    <>
      <h1 className="text-3xl font-bold tracking-tight">{dict.ui.compare.title}</h1>
      <p className="mt-2 max-w-3xl text-muted">{dict.ui.compare.intro}</p>
      <Picker dict={dict} locale={locale} places={choosable} selected={selected} />
      {chosen.length < 2 ? (
        <Suggestions dict={dict} locale={locale} chosen={chosen} bySlug={bySlug} />
      ) : (
        <Comparison dict={dict} locale={locale} chosen={chosen} places={places} />
      )}
    </>
  );
}

function Picker({
  dict,
  locale,
  places,
  selected,
}: {
  dict: Dictionary;
  locale: Locale;
  places: Place[];
  selected: string[];
}) {
  const sorted = [...places].sort((a, b) => name(a, locale).localeCompare(name(b, locale), locale));
  return (
    <form action={`/${locale}/compare`} method="get" className="mt-6 flex flex-wrap items-end gap-3">
      {Array.from({ length: MAX_COMPARE }, (_, i) => (
        <label key={i} className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{fill(dict.ui.compare.pick, { n: i + 1 })}</span>
          <select
            name="e"
            defaultValue={selected[i] ?? ""}
            className="min-w-44 rounded-md border border-border bg-surface px-2 py-1.5"
          >
            <option value="">{dict.ui.compare.none}</option>
            {sorted.map((p) => (
              <option key={p.slug} value={p.slug}>
                {name(p, locale)}
              </option>
            ))}
          </select>
        </label>
      ))}
      <button type="submit" className="rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-surface hover:opacity-90">
        {dict.ui.compare.submit}
      </button>
    </form>
  );
}

function Suggestions({
  dict,
  locale,
  chosen,
  bySlug,
}: {
  dict: Dictionary;
  locale: Locale;
  chosen: Place[];
  bySlug: Map<string, Place>;
}) {
  const first = chosen[0];
  const pairs: [Place, Place][] = first
    ? neighbours(first.slug).flatMap((n) => (bySlug.has(n) ? [[first, bySlug.get(n) as Place]] : []))
    : POPULAR.flatMap(([a, b]) => (bySlug.has(a) && bySlug.has(b) ? [[bySlug.get(a), bySlug.get(b)] as [Place, Place]] : []));
  return (
    <section className="mt-8">
      <p>{dict.ui.compare.choose}</p>
      {pairs.length > 0 && (
        <>
          <h2 className="mt-6 text-xl font-semibold">
            {first ? fill(dict.ui.compare.neighbours, { name: name(first, locale) }) : dict.ui.compare.popular}
          </h2>
          <ul className="mt-3 flex flex-wrap gap-2">
            {pairs.map(([a, b]) => (
              <li key={`${a.slug}-${b.slug}`}>
                <Link
                  href={compareHref(locale, [a.slug, b.slug])}
                  className="block rounded-md border border-border bg-surface px-3 py-1.5 text-sm hover:bg-accent-soft"
                >
                  {name(a, locale)} – {name(b, locale)}
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

async function Comparison({
  dict,
  locale,
  chosen,
  places,
}: {
  dict: Dictionary;
  locale: Locale;
  chosen: Place[];
  places: Place[];
}) {
  const edition = await getLatestEdition();
  const [scores, pillars, indicators, categories, indices, observations] = await Promise.all([
    edition == null ? Promise.resolve([] as ScoreRow[]) : getScores(edition),
    getPillars(),
    getIndicators(),
    getCategories(),
    getIndices(),
    Promise.all(chosen.map((p) => getPlaceObservations(p.slug))),
  ]);
  const scoreOf = (slug: string, level: ScoreRow["level"], key: string) =>
    scores.find((s) => s.slug === slug && s.level === level && s.key === key);
  const peerTotal = (place: Place) => {
    const peers = new Set(places.filter((p) => p.peerGroup === place.peerGroup).map((p) => p.slug));
    return scores.filter((s) => s.level === "composite" && s.key === COMPOSITE && s.score != null && peers.has(s.slug))
      .length;
  };
  // Latest value of every indicator for each chosen place.
  const latest = observations.map((list) => {
    const map = new Map<string, Observation>();
    for (const o of list) map.set(o.indicatorId, o); // ordered by period end, so the last wins
    return map;
  });

  const scoreRow = (label: string, level: ScoreRow["level"], key: string, href?: string) => {
    const values = chosen.map((p) => scoreOf(p.slug, level, key)?.score ?? null);
    const best = bestIndex(values, "higher_better");
    return (
      <tr key={`${level}-${key}`} className="border-b border-border last:border-0">
        <th scope="row" className="px-3 py-2 text-left font-medium">
          {href ? (
            <Link href={href} className="hover:underline">
              {label}
            </Link>
          ) : (
            label
          )}
        </th>
        {values.map((v, i) => (
          <td key={chosen[i].slug} className="px-3 py-2">
            {v == null ? (
              <span className="text-sm text-muted">{dict.ui.common.noScore}</span>
            ) : (
              <Best on={best === i} dict={dict}>
                <ScoreBar score={v} locale={locale} />
              </Best>
            )}
          </td>
        ))}
      </tr>
    );
  };

  const header = (
    <thead className="border-b border-border text-left">
      <tr>
        <th scope="col" className="w-1/4 px-3 py-2" />
        {chosen.map((p) => (
          <th key={p.slug} scope="col" className="px-3 py-2 font-semibold">
            <Link href={`/${locale}/states/${p.slug}`} className="hover:underline">
              {name(p, locale)}
            </Link>
          </th>
        ))}
      </tr>
    </thead>
  );
  const tableClass = "w-full text-sm";
  const minWidth = { minWidth: `${12 + chosen.length * 11}rem` };

  return (
    <>
      <section aria-label={dict.site.name} className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {chosen.map((p) => {
          const c = scoreOf(p.slug, "composite", COMPOSITE);
          return (
            <div key={p.slug} className="rounded-lg border border-border bg-surface p-4">
              <Link href={`/${locale}/states/${p.slug}`} className="font-semibold hover:underline">
                {name(p, locale)}
              </Link>
              {c?.score != null ? (
                <>
                  <p className="mt-1 text-3xl font-bold tabular-nums">
                    {formatScore(c.score, locale)}
                    <span className="ml-1 text-sm font-normal text-muted">/ 100</span>
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
                    <BandLabel score={c.score} dict={dict} />
                    {p.peerGroup &&
                      fill(dict.ui.compare.rank, {
                        rank: c.rankPeer ?? "–",
                        total: peerTotal(p),
                        group: dict.ui.peerGroups[p.peerGroup],
                      })}
                  </div>
                </>
              ) : (
                <p className="mt-1 text-sm text-muted">{dict.ui.state.notScored}</p>
              )}
            </div>
          );
        })}
      </section>

      <section aria-labelledby="pillars" className="mt-10">
        <h2 id="pillars" className="text-xl font-semibold">
          {dict.ui.state.pillarsTitle}
        </h2>
        <div className="mt-3 overflow-x-auto rounded-lg border border-border bg-surface">
          <table className={tableClass} style={minWidth}>
            {header}
            <tbody>
              {scoreRow(dict.site.name, "composite", COMPOSITE, `/${locale}/rankings`)}
              {pillars.map((p) =>
                scoreRow(
                  dict.pillars[p.id as keyof Dictionary["pillars"]]?.name ?? p.name,
                  "pillar",
                  p.id,
                  `/${locale}/pillars/${p.id}`,
                ),
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="indices" className="mt-10">
        <h2 id="indices" className="text-xl font-semibold">
          {dict.ui.compare.indicesTitle}
        </h2>
        <div className="mt-3 overflow-x-auto rounded-lg border border-border bg-surface">
          <table className={tableClass} style={minWidth}>
            {header}
            <tbody>
              {indices.map((index) => scoreRow(index.name, "composite", index.id, `/${locale}/indices/${index.id}`))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="indicators" className="mt-10">
        <h2 id="indicators" className="text-xl font-semibold">
          {dict.ui.compare.indicatorsTitle}
        </h2>
        <p className="mt-1 text-sm text-muted">
          <span aria-hidden="true" className="text-accent">
            ★
          </span>{" "}
          {dict.ui.compare.best}. {dict.ui.compare.differentPeriods.replace(/^[^:]+:\s*/, "")}
        </p>
        {categories.map((category) => {
          const rows = indicators.filter(
            (i) => i.categoryId === category.id && latest.some((m) => m.has(i.id)),
          );
          if (!rows.length) return null;
          return (
            <div key={category.id} className="mt-5">
              <h3 className="font-semibold">{category.name}</h3>
              <div className="mt-2 overflow-x-auto rounded-lg border border-border bg-surface">
                <table className={tableClass} style={minWidth}>
                  <tbody>
                    {rows.map((indicator) => {
                      const cells = latest.map((m) => m.get(indicator.id) ?? null);
                      const labels = new Set(cells.filter(Boolean).map((o) => (o as Observation).label));
                      const comparable = indicator.rankable && labels.size === 1;
                      const best = comparable
                        ? bestIndex(cells.map((o) => o?.value ?? null), indicator.direction)
                        : null;
                      return (
                        <tr key={indicator.id} className="border-b border-border last:border-0">
                          <th scope="row" className="w-1/4 px-3 py-2 text-left font-normal">
                            <Link href={`/${locale}/indicators/${indicator.id}`} className="hover:underline">
                              {indicator.name}
                            </Link>
                            {!comparable && labels.size > 1 && (
                              <span className="block text-xs text-muted">{dict.ui.compare.differentPeriods}</span>
                            )}
                          </th>
                          {cells.map((o, i) => (
                            <td key={chosen[i].slug} className="px-3 py-2 tabular-nums">
                              {o ? (
                                <>
                                  <Best on={best === i} dict={dict}>
                                    {formatValue(o.value, indicator, locale)}
                                  </Best>
                                  <span className="block text-xs text-muted">
                                    {o.label}
                                    {o.provisional ? ` · ${dict.ui.common.provisional}` : ""}
                                  </span>
                                </>
                              ) : (
                                <span className="text-muted italic">{dict.ui.common.notAvailable}</span>
                              )}
                            </td>
                          ))}
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
    </>
  );
}
