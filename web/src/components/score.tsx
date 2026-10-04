import type { Dictionary } from "@/i18n/dictionaries";
import type { Locale } from "@/i18n/config";
import { band, fill, formatScore, rankChange } from "@/lib/present";

/**
 * A 0-100 score as a thin single-hue bar with the number beside it. The number is always
 * printed, so the bar is a visual aid, never the only carrier of the value.
 */
export function ScoreBar({ score, locale, label }: { score: number | null; locale: Locale; label?: string }) {
  if (score == null) return <span className="text-sm text-muted">–</span>;
  return (
    <span className="flex items-center gap-2" title={label}>
      <span aria-hidden="true" className="relative h-2 w-20 shrink-0 rounded-full bg-border sm:w-28">
        <span
          className="absolute inset-y-0 left-0 rounded-full bg-accent"
          style={{ width: `${Math.max(2, Math.min(100, score))}%` }}
        />
      </span>
      <span className="tabular-nums">{formatScore(score, locale)}</span>
    </span>
  );
}

export function BandLabel({ score, dict }: { score: number | null; dict: Dictionary }) {
  if (score == null) return null;
  return (
    <span className="rounded-sm border border-border px-1.5 py-0.5 text-xs text-muted">
      {dict.ui.bands[band(score)]}
    </span>
  );
}

/** ▲3 / ▼2 / – with an accessible description; arrows and words, not colour, carry meaning. */
export function RankChange({ rank, previous, dict }: { rank: number | null; previous: number | null; dict: Dictionary }) {
  const change = rankChange(rank, previous);
  if (change == null) return <span className="text-sm text-muted">{dict.ui.common.new}</span>;
  if (change === 0)
    return (
      <span className="text-sm text-muted" title={dict.ui.common.unchanged}>
        <span aria-hidden="true">–</span>
        <span className="sr-only">{dict.ui.common.unchanged}</span>
      </span>
    );
  const text = fill(change > 0 ? dict.ui.common.up : dict.ui.common.down, { n: Math.abs(change) });
  return (
    <span className="text-sm tabular-nums" title={text}>
      <span aria-hidden="true">
        {change > 0 ? "▲" : "▼"}
        {Math.abs(change)}
      </span>
      <span className="sr-only">{text}</span>
    </span>
  );
}
