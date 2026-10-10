/**
 * A Postgres `date` as "YYYY-MM-DD". The driver turns dates into Dates at local midnight, so the
 * local calendar fields are the date; toISOString() would shift it a day back east of UTC (IST).
 */
export function iso(d: unknown): string {
  if (!(d instanceof Date)) return String(d);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
