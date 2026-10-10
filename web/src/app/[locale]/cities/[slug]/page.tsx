import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { locale as rootLocale } from "next/root-params";
import { Suspense } from "react";
import { TrendChart } from "@/components/trend-chart";
import { isLocale, type Locale } from "@/i18n/config";
import { getDictionary } from "@/i18n/dictionaries";
import { CityMap } from "@/components/city-map";
import { aqiSummary, CITY_CRIME, cityPoints, latestFor } from "@/lib/cities";
import { getCities, getCityObservations, getIndicators, getPlaceObservations, getPlaces } from "@/lib/data";
import { formatNumber } from "@/lib/format";
import { aqiCategory, fill, formatValue } from "@/lib/present";

// Million-plus cities are prerendered; the rest render on first visit and are cached after that.
export async function generateStaticParams() {
  return (await getCities()).filter((c) => c.millionPlus).map((c) => ({ slug: c.slug }));
}

export async function generateMetadata({ params }: PageProps<"/[locale]/cities/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const city = (await getCities()).find((c) => c.slug === slug);
  return { title: city?.name ?? "City" };
}

export default function CityPage(props: PageProps<"/[locale]/cities/[slug]">) {
  return (
    <Suspense fallback={<div className="mx-auto max-w-5xl px-4 py-12 text-muted">…</div>}>
      <CityReport params={props.params} />
    </Suspense>
  );
}

async function CityReport({ params }: { params: PageProps<"/[locale]/cities/[slug]">["params"] }) {
  const { slug } = await params;
  const [dict, lang, cities, places, indicators] = await Promise.all([
    getDictionary(),
    rootLocale(),
    getCities(),
    getPlaces(),
    getIndicators(),
  ]);
  const locale: Locale = isLocale(lang) ? lang : "en";
  const city = cities.find((c) => c.slug === slug);
  if (!city) notFound();
  const byId = new Map(indicators.map((i) => [i.id, i]));
  const state = places.find((p) => p.slug === city.stateSlug);
  const [own, stateObs, cityAir] = await Promise.all([
    getPlaceObservations(slug),
    getPlaceObservations(city.stateSlug),
    getCityObservations(["aqi-daily-mean"]),
  ]);
  const neighbours = cities.filter((c) => c.stateSlug === city.stateSlug);
  const pm25 = latestFor(own, slug, "pm25-annual");
  const pm25Indicator = byId.get("pm25-annual");
  const clean = latestFor(own, slug, "swachh-survekshan-score");
  const league = latestFor(own, slug, "swachh-super-league");
  const cityName = locale === "hi" && city.nameHi ? city.nameHi : city.name;
  const stateName = state ? (locale === "hi" && state.nameHi ? state.nameHi : state.name) : "";
  const aqi = aqiSummary(own, slug);
  const aqiIndicator = byId.get("aqi-daily-mean");

  const crimeCharts = CITY_CRIME.flatMap((id) => {
    const indicator = byId.get(id);
    const series = own.filter((o) => o.indicatorId === id);
    if (!indicator || series.length < 2) return [];
    const periods = series.map((o) => o.label);
    const reference = stateObs.filter((o) => o.indicatorId === id && periods.includes(o.label));
    const tip = (label: string, v: number) => `${label}: ${formatValue(v, indicator, locale)}`;
    return [
      {
        id,
        indicator,
        latest: series[series.length - 1],
        periods,
        series: [
          {
            name: cityName,
            kind: "primary" as const,
            points: series.map((o) => ({ label: o.label, value: o.value, tip: tip(o.label, o.value) })),
          },
          ...(reference.length
            ? [
                {
                  name: stateName,
                  kind: "reference" as const,
                  points: reference.map((o) => ({ label: o.label, value: o.value, tip: tip(o.label, o.value) })),
                },
              ]
            : []),
        ],
      },
    ];
  });

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <p className="text-sm text-muted">
        <Link href={`/${locale}/cities`} className="underline underline-offset-2">
          {dict.ui.nav.cities}
        </Link>{" "}
        ·{" "}
        {state && (
          <Link href={`/${locale}/states/${state.slug}`} className="underline underline-offset-2">
            {stateName}
          </Link>
        )}
      </p>
      <h1 className="mt-1 text-3xl font-bold tracking-tight">{cityName}</h1>
      <p className="text-muted">
        {dict.ui.cities.eyebrow}
        {city.population ? ` · ${dict.ui.cities.population}: ${formatNumber(city.population, 0, locale)}` : ""}
      </p>

      <section aria-labelledby="air" className="mt-6 rounded-lg border border-border bg-surface p-5">
        <h2 id="air" className="text-sm text-muted">
          {aqiIndicator?.name}
        </h2>
        {aqi ? (
          <div className="mt-2 grid gap-6 sm:grid-cols-[auto_1fr] sm:items-center">
            <div>
              <p className="text-5xl font-bold tabular-nums">{formatNumber(aqi.latest.value, 0, locale)}</p>
              <p className="mt-1">
                {dict.ui.aqi[aqiCategory(aqi.latest.value)]} <span className="text-muted">· {aqi.latest.label}</span>
              </p>
              <p className="mt-1 text-sm text-muted">
                {dict.ui.cities.aqi30}: {formatNumber(aqi.mean, 0, locale)} (
                {dict.ui.aqi[aqiCategory(aqi.mean)]})
              </p>
            </div>
            {aqi.recent.length >= 2 && (
              <TrendChart
                title={dict.ui.cities.aqi30}
                periods={aqi.recent.map((o) => o.label)}
                format={(v) => formatNumber(v, 0, locale)}
                series={[
                  {
                    name: cityName,
                    kind: "primary",
                    points: aqi.recent.map((o) => ({
                      label: o.label,
                      value: o.value,
                      tip: `${o.label}: ${formatNumber(o.value, 0, locale)} (${dict.ui.aqi[aqiCategory(o.value)]})`,
                    })),
                  },
                ]}
              />
            )}
          </div>
        ) : (
          <p className="mt-2 text-muted">{dict.ui.cities.noAqi}</p>
        )}
      </section>

      <section aria-labelledby="where" className="mt-6">
        <h2 id="where" className="sr-only">
          {dict.ui.cities.whereTitle}
        </h2>
        <div className="grid items-start gap-4 md:grid-cols-2">
          {/* Close-up with full-detail borders: neighbouring cities, whichever state they are in. */}
          <CityMap
            view={{ around: slug, km: 45, state: city.stateSlug }}
            points={cityPoints(cities, cityAir, locale)}
            title={fill(dict.ui.cities.aroundTitle, { city: cityName })}
            highlight={slug}
            hrefFor={(c) => `/${locale}/cities/${c}`}
          />
          <CityMap
            view={{ state: city.stateSlug }}
            points={cityPoints(neighbours, cityAir, locale)}
            title={fill(dict.ui.cities.stateMapTitle, { state: stateName })}
            highlight={slug}
            hrefFor={(c) => `/${locale}/cities/${c}`}
          />
        </div>
      </section>

      <div className="mt-6 grid items-start gap-4 sm:grid-cols-2">
        {pm25 && pm25Indicator && (
          <section aria-labelledby="pm25" className="rounded-lg border border-border bg-surface p-5">
            <h2 id="pm25" className="text-sm text-muted">
              <Link href={`/${locale}/indicators/pm25-annual`} className="hover:underline">
                {pm25Indicator.name}
              </Link>
            </h2>
            <p className="mt-2 text-4xl font-bold tabular-nums">
              {formatNumber(pm25.value, 0, locale)} <span className="text-base font-normal text-muted">µg/m³</span>
              <span className="ml-2 text-sm font-normal text-muted">{pm25.label}</span>
            </p>
            <p className="mt-2 text-sm">{dict.ui.cities.pm25Note}</p>
          </section>
        )}
        {(clean || league) && (
          <section aria-labelledby="swachh" className="rounded-lg border border-border bg-surface p-5">
            <h2 id="swachh" className="text-sm text-muted">
              <Link href={`/${locale}/indicators/swachh-survekshan-score`} className="hover:underline">
                {dict.ui.cities.swachhCard}
              </Link>
            </h2>
            {clean ? (
              <p className="mt-2 text-4xl font-bold tabular-nums">
                {formatNumber(clean.value, 0, locale)}{" "}
                <span className="text-base font-normal text-muted">{fill(dict.ui.cities.outOf, { max: formatNumber(12500, 0, locale) })}</span>
              </p>
            ) : (
              <>
                <p className="mt-2 text-2xl font-bold text-accent">{dict.ui.cities.superLeague}</p>
                <p className="mt-2 text-sm">{dict.ui.cities.superLeagueNote}</p>
              </>
            )}
            {clean?.note?.includes("mean of") && <p className="mt-2 text-sm text-muted">{clean.note.split("; ")[1]}</p>}
          </section>
        )}
      </div>

      {crimeCharts.length > 0 && (
        <section aria-labelledby="crime" className="mt-10">
          <h2 id="crime" className="text-xl font-semibold">
            {dict.ui.cities.trendsTitle}
          </h2>
          <p className="mt-1 text-sm text-muted">{fill(dict.ui.cities.stateDashed, { state: stateName })}</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {crimeCharts.map((c) => (
              <div key={c.id}>
                <Link href={`/${locale}/indicators/${c.id}`} className="block hover:opacity-90">
                  <TrendChart
                    title={`${c.indicator.name} · ${formatValue(c.latest.value, c.indicator, locale)} (${c.latest.label})`}
                    periods={c.periods}
                    series={c.series}
                    format={(v) => formatNumber(v, c.indicator.decimals, locale)}
                  />
                </Link>
              </div>
            ))}
          </div>
          <aside className="mt-4 rounded-md border border-border bg-accent-soft px-4 py-3 text-sm">
            <strong>{dict.ui.indicators.caveat}:</strong> {dict.ui.cities.crimeCaveat}
          </aside>
        </section>
      )}
    </div>
  );
}
