import type { Metadata } from "next";
import Link from "next/link";
import { locale as rootLocale } from "next/root-params";
import { Suspense } from "react";
import { isLocale, type Locale } from "@/i18n/config";
import { getDictionary } from "@/i18n/dictionaries";
import { aqiSummary, CITY_CRIME } from "@/lib/cities";
import { type City, getCities, getCityObservations, getIndicators, getPlaces } from "@/lib/data";
import { formatNumber } from "@/lib/format";
import { aqiCategory } from "@/lib/present";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.ui.cities.title, description: dict.ui.cities.intro };
}

export default function CitiesPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <Suspense fallback={<p className="text-muted">…</p>}>
        <Cities />
      </Suspense>
    </div>
  );
}

async function Cities() {
  const [dict, lang, cities, places, indicators, observations] = await Promise.all([
    getDictionary(),
    rootLocale(),
    getCities(),
    getPlaces(),
    getIndicators(),
    getCityObservations(["aqi-daily-mean", ...CITY_CRIME]),
  ]);
  const locale: Locale = isLocale(lang) ? lang : "en";
  const stateName = new Map(places.map((p) => [p.slug, locale === "hi" && p.nameHi ? p.nameHi : p.name]));
  const byId = new Map(indicators.map((i) => [i.id, i]));
  const name = (c: City) => (locale === "hi" && c.nameHi ? c.nameHi : c.name);
  const sorted = [...cities].sort((a, b) => name(a).localeCompare(name(b), locale));
  const latestOf = (slug: string, id: string) => observations.filter((o) => o.slug === slug && o.indicatorId === id).at(-1);
  const crimeYear = observations.filter((o) => o.indicatorId === "murder-rate").at(-1)?.label;

  return (
    <>
      <h1 className="text-3xl font-bold tracking-tight">{dict.ui.cities.title}</h1>
      <p className="mt-2 max-w-3xl text-muted">{dict.ui.cities.intro}</p>
      <div className="mt-6 overflow-x-auto rounded-lg border border-border bg-surface">
        <table className="w-full min-w-[60rem] text-sm">
          <thead className="border-b border-border text-left text-muted">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">
                {dict.ui.cities.city}
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                {dict.ui.cities.aqiToday}
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                {dict.ui.cities.aqi30}
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
            {sorted.map((c) => {
              const aqi = aqiSummary(observations, c.slug);
              return (
                <tr key={c.slug} className="border-b border-border last:border-0">
                  <th scope="row" className="px-3 py-2 text-left font-medium">
                    <Link href={`/${locale}/cities/${c.slug}`} className="hover:underline">
                      {name(c)}
                    </Link>
                    <span className="block text-xs font-normal text-muted">{stateName.get(c.stateSlug)}</span>
                  </th>
                  <td className="px-3 py-2">
                    {aqi ? (
                      <>
                        <span className="tabular-nums">{formatNumber(aqi.latest.value, 0, locale)}</span>{" "}
                        <span className="text-muted">· {dict.ui.aqi[aqiCategory(aqi.latest.value)]}</span>
                        <span className="block text-xs text-muted">{aqi.latest.label}</span>
                      </>
                    ) : (
                      <span className="text-xs text-muted italic">{dict.ui.common.notAvailable}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {aqi ? formatNumber(aqi.mean, 0, locale) : "–"}
                  </td>
                  {CITY_CRIME.map((id) => {
                    const o = latestOf(c.slug, id);
                    const indicator = byId.get(id);
                    return (
                      <td key={id} className="px-3 py-2 text-right tabular-nums">
                        {o && indicator ? formatNumber(o.value, indicator.decimals, locale) : "–"}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <aside className="mt-4 max-w-3xl rounded-md border border-border bg-accent-soft px-4 py-3 text-sm">
        <strong>{dict.ui.indicators.caveat}:</strong> {dict.ui.cities.crimeCaveat}
      </aside>
    </>
  );
}
