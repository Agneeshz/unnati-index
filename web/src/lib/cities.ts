import type { CityPoint } from "@/components/city-map";
import type { City, Observation } from "@/lib/data";

/** City indicators from NCRB's metropolitan-city tables, in display order. */
export const CITY_CRIME = ["murder-rate", "crime-rate-total", "crimes-against-women-rate", "chargesheeting-rate"];

export function cityName(city: Pick<City, "name" | "nameHi">, locale: string): string {
  return locale === "hi" && city.nameHi ? city.nameHi : city.name;
}

/** The latest value of one indicator for one place (observations are ordered by period end). */
export function latestFor(observations: Observation[], slug: string, indicatorId: string): Observation | undefined {
  let found: Observation | undefined;
  for (const o of observations) if (o.slug === slug && o.indicatorId === indicatorId) found = o;
  return found;
}

/** The latest daily AQI reading and the mean over the 30 days up to it. */
export function aqiSummary(observations: Observation[], slug: string) {
  const own = observations.filter((o) => o.slug === slug && o.indicatorId === "aqi-daily-mean");
  if (!own.length) return null;
  const latest = own[own.length - 1];
  const since = new Date(latest.end);
  since.setDate(since.getDate() - 29);
  const recent = own.filter((o) => new Date(o.end) >= since);
  return { latest, recent, mean: recent.reduce((a, o) => a + o.value, 0) / recent.length };
}

/** Map points for cities, coloured by their 30-day average AQI. */
export function cityPoints(cities: City[], observations: Observation[], locale: string): CityPoint[] {
  return cities.map((c) => ({
    slug: c.slug,
    name: cityName(c, locale),
    latitude: c.latitude,
    longitude: c.longitude,
    population: c.population,
    aqi: aqiSummary(observations, c.slug)?.mean ?? null,
  }));
}
