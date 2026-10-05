import type { Observation } from "@/lib/data";

/** City indicators from NCRB's metropolitan-city tables, in display order. */
export const CITY_CRIME = ["murder-rate", "crime-rate-total", "crimes-against-women-rate", "chargesheeting-rate"];

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
