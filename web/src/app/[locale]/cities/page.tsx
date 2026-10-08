import type { Metadata } from "next";
import Link from "next/link";
import { locale as rootLocale } from "next/root-params";
import { Suspense } from "react";
import { CityMap } from "@/components/city-map";
import { isLocale, type Locale } from "@/i18n/config";
import { getDictionary } from "@/i18n/dictionaries";
import { aqiSummary, CITY_CRIME, cityName, cityPoints, latestFor } from "@/lib/cities";
import { getCities, getCityObservations, getIndicators, getPlaces } from "@/lib/data";
import { formatNumber } from "@/lib/format";
import { aqiCategory, fill } from "@/lib/present";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.ui.cities.title, description: dict.ui.cities.mapNote };
}

export default function CitiesPage(props: PageProps<"/[locale]/cities">) {
  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <Suspense fallback={<p className="text-muted">…</p>}>
        <Cities searchParams={props.searchParams} />
      </Suspense>
    </div>
  );
}

async function Cities({ searchParams }: { searchParams: PageProps<"/[locale]/cities">["searchParams"] }) {
  const [dict, lang, cities, places, indicators, observations, query] = await Promise.all([
    getDictionary(),
    rootLocale(),
    getCities(),
    getPlaces(),
    getIndicators(),
    getCityObservations(["aqi-daily-mean", "pm25-annual", ...CITY_CRIME]),
    searchParams,
  ]);
  const locale: Locale = isLocale(lang) ? lang : "en";
  const stateName = new Map(places.map((p) => [p.slug, locale === "hi" && p.nameHi ? p.nameHi : p.name]));
  const byId = new Map(indicators.map((i) => [i.id, i]));
  const state = typeof query.state === "string" && stateName.has(query.state) ? query.state : "";
  const size = query.size === "million" ? "million" : "";
  const shown = cities.filter((c) => (!state || c.stateSlug === state) && (!size || c.millionPlus));
  const states = [...new Set(cities.map((c) => c.stateSlug))].sort((a, b) =>
    (stateName.get(a) ?? a).localeCompare(stateName.get(b) ?? b, locale),
  );
  const metros = cities.filter((c) => observations.some((o) => o.slug === c.slug && o.indicatorId === "murder-rate"));
  const crimeYear = observations.filter((o) => o.indicatorId === "murder-rate").at(-1)?.label;

  return (
    <>
      <h1 className="text-3xl font-bold tracking-tight">{dict.ui.cities.title}</h1>
      <p className="mt-2 max-w-3xl text-muted">{fill(dict.ui.cities.intro, { n: cities.length })}</p>

      <form action={`/${locale}/cities`} method="get" className="mt-6 flex flex-wrap items-end gap-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="text-muted">{dict.ui.cities.state}</span>
          <select name="state" defaultValue={state} className="rounded-md border border-border bg-surface px-2 py-1.5">
            <option value="">{dict.ui.cities.allStates}</option>
            {states.map((s) => (
              <option key={s} value={s}>
                {stateName.get(s)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-muted">{dict.ui.cities.population}</span>
          <select name="size" defaultValue={size} className="rounded-md border border-border bg-surface px-2 py-1.5">
            <option value="">{dict.ui.cities.allSizes}</option>
            <option value="million">{dict.ui.cities.millionPlus}</option>
          </select>
        </label>
        <button type="submit" className="rounded-md bg-accent px-4 py-1.5 font-medium text-surface hover:opacity-90">
          {dict.ui.cities.filter}
        </button>
        <span className="pb-1.5 text-muted">{fill(dict.ui.cities.shown, { n: shown.length, total: cities.length })}</span>
      </form>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <CityMap
          view={state || "india"}
          points={cityPoints(shown, observations, locale)}
          title={state ? fill(dict.ui.cities.stateMapTitle, { state: stateName.get(state) ?? state }) : dict.ui.cities.mapTitle}
          hrefFor={(slug) => `/${locale}/cities/${slug}`}
          labels={state ? 8 : 6}
        />
        <div className="overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="w-full min-w-[36rem] text-sm">
            <thead className="border-b border-border text-left text-muted">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">
                  {dict.ui.cities.city}
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  {dict.ui.cities.population}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {dict.ui.cities.aqi30}
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  <Link href={`/${locale}/indicators/pm25-annual`} className="hover:underline">
                    {dict.ui.cities.pm25}
                  </Link>
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((c) => {
                const aqi = aqiSummary(observations, c.slug);
                const pm = latestFor(observations, c.slug, "pm25-annual");
                return (
                  <tr key={c.slug} className="border-b border-border last:border-0">
                    <th scope="row" className="px-3 py-2 text-left font-medium">
                      <Link href={`/${locale}/cities/${c.slug}`} className="hover:underline">
                        {cityName(c, locale)}
                      </Link>
                      <span className="block text-xs font-normal text-muted">{stateName.get(c.stateSlug)}</span>
                    </th>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {c.population ? formatNumber(c.population, 0, locale) : "–"}
                    </td>
                    <td className="px-3 py-2">
                      {aqi ? (
                        <>
                          <span className="tabular-nums">{formatNumber(aqi.mean, 0, locale)}</span>{" "}
                          <span className="text-muted">· {dict.ui.aqi[aqiCategory(aqi.mean)]}</span>
                        </>
                      ) : (
                        <span className="text-xs text-muted italic">{dict.ui.common.notAvailable}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {pm ? (
                        <>
                          {formatNumber(pm.value, 0, locale)} <span className="text-xs text-muted">({pm.label})</span>
                        </>
                      ) : (
                        "–"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <section aria-labelledby="crime" className="mt-12">
        <h2 id="crime" className="text-xl font-semibold">
          {dict.ui.cities.crimeTitle}
        </h2>
        <p className="mt-1 text-sm text-muted">{dict.ui.cities.crimeIntro}</p>
        <div className="mt-3 overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="w-full min-w-[44rem] text-sm">
            <thead className="border-b border-border text-left text-muted">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">
                  {dict.ui.cities.city}
                </th>
                {CITY_CRIME.map((id) => (
                  <th key={id} scope="col" className="px-3 py-2 text-right font-medium">
                    <Link href={`/${locale}/indicators/${id}`} className="hover:underline">
                      {byId.get(id)?.name ?? id}
                    </Link>
                    {crimeYear && <span className="block text-xs font-normal">{crimeYear}</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metros.map((c) => (
                <tr key={c.slug} className="border-b border-border last:border-0">
                  <th scope="row" className="px-3 py-2 text-left font-medium">
                    <Link href={`/${locale}/cities/${c.slug}`} className="hover:underline">
                      {cityName(c, locale)}
                    </Link>
                  </th>
                  {CITY_CRIME.map((id) => {
                    const o = latestFor(observations, c.slug, id);
                    const indicator = byId.get(id);
                    return (
                      <td key={id} className="px-3 py-2 text-right tabular-nums">
                        {o && indicator ? formatNumber(o.value, indicator.decimals, locale) : "–"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <aside className="mt-4 max-w-3xl rounded-md border border-border bg-accent-soft px-4 py-3 text-sm">
          <strong>{dict.ui.indicators.caveat}:</strong> {dict.ui.cities.crimeCaveat}
        </aside>
      </section>
    </>
  );
}
