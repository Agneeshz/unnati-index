// Mirrors pipeline/src/unnati/health.py, which opens the GitHub issues for the same conditions.

// Typical days between releases; null = no regular schedule (never "stale").
const CADENCE_DAYS: Record<string, number | null> = {
  hourly: 1,
  daily: 2,
  weekly: 7,
  monthly: 30,
  quarterly: 92,
  annual: 365,
  biennial: 730,
  irregular: null,
};
const STALE_FACTOR = 1.5;
const ABANDONED_AFTER_MS = 2 * 3600_000;
const DAY_MS = 86400_000;

export type SourceHealth =
  | { status: "ok" }
  | { status: "failing"; since: string }
  | { status: "stale"; since: string | null }
  | { status: "unknown" };

export function sourceHealth(
  d: {
    cadence: string;
    lastChanged: Date | null;
    runStatus: string | null;
    runStarted: Date | null;
    failingSince: Date | null;
  },
  now: Date = new Date(),
): SourceHealth {
  const abandoned =
    d.runStatus === "running" && d.runStarted !== null && now.getTime() - d.runStarted.getTime() > ABANDONED_AFTER_MS;
  if (d.runStatus === "failed" || d.runStatus === "rejected" || abandoned) {
    return { status: "failing", since: (d.failingSince ?? d.runStarted ?? now).toISOString() };
  }
  if (d.runStatus === null) return { status: "unknown" };
  const days = CADENCE_DAYS[d.cadence];
  if (days == null) return { status: "ok" };
  if (d.lastChanged === null) return { status: "stale", since: null };
  if (now.getTime() - d.lastChanged.getTime() > days * STALE_FACTOR * DAY_MS) {
    return { status: "stale", since: d.lastChanged.toISOString() };
  }
  return { status: "ok" };
}
