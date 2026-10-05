import type { Dictionary } from "@/i18n/dictionaries";
import type { Locale } from "@/i18n/config";
import { formatNumber } from "@/lib/format";
import type { Indicator, PeerGroup } from "@/lib/data";

export const PEER_GROUPS: PeerGroup[] = ["large_state", "ne_himalayan_state", "ut"];

export type Band = keyof Dictionary["ui"]["bands"];

/** NITI Aayog's familiar bands: Achiever 100, Front Runner 65-99, Performer 50-64, Aspirant <50. */
export function band(score: number): Band {
  if (score >= 100) return "achiever";
  if (score >= 65) return "frontRunner";
  if (score >= 50) return "performer";
  return "aspirant";
}

/** "Up 3 from last edition" etc.; null when there is no previous rank. */
export function rankChange(rank: number | null, previous: number | null): number | null {
  if (rank == null || previous == null) return null;
  return previous - rank; // positive = moved up
}

export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? `{${key}}`));
}

/** An indicator value with its unit, Indian digit grouping and the indicator's decimals. */
export function formatValue(value: number, indicator: Pick<Indicator, "unit" | "decimals">, locale: Locale): string {
  const number = formatNumber(value, indicator.decimals, locale);
  const unit = indicator.unit;
  if (unit === "%" || unit.startsWith("% ")) return `${number}%`;
  if (unit === "persons") return number;
  return `${number} ${unit}`;
}

/**
 * A release summary ("110 new and 155 revised figures across 3 indicators", as the pipeline
 * writes it) in the page's language; unrecognised text is returned unchanged.
 */
export function releaseSummary(summary: string, dict: Dictionary): string {
  const m = summary.match(/^(?:([\d,]+) new)?(?: and )?(?:([\d,]+) revised)? figures across (\d+) indicators?$/);
  if (!m) return summary;
  const parts = [
    m[1] ? fill(dict.ui.updates.new, { n: m[1] }) : "",
    m[2] ? fill(dict.ui.updates.revised, { n: m[2] }) : "",
  ].filter(Boolean);
  const changes = parts.join(dict.ui.updates.and);
  return m[3] === "1" ? fill(dict.ui.updates.summaryOne, { changes }) : fill(dict.ui.updates.summary, { changes, n: m[3] });
}

export function formatScore(score: number, locale: Locale): string {
  return formatNumber(score, 1, locale);
}
