import { describe, expect, it } from "vitest";
import { sourceHealth } from "./source-health";

const NOW = new Date("2026-10-10T09:00:00Z");
const daysAgo = (n: number) => new Date(NOW.getTime() - n * 86400_000);
const base = { cadence: "monthly", lastChanged: daysAgo(10), runStatus: "unchanged", runStarted: daysAgo(1) };

describe("sourceHealth", () => {
  it("is ok when the latest run worked and data is recent", () => {
    expect(sourceHealth({ ...base, failingSince: null }, NOW)).toEqual({ status: "ok" });
  });

  it("reports failing from the first failure of the streak", () => {
    const h = sourceHealth({ ...base, runStatus: "failed", failingSince: daysAgo(3) }, NOW);
    expect(h).toEqual({ status: "failing", since: daysAgo(3).toISOString() });
  });

  it("treats a run stuck in running for hours as failing, but not one in progress", () => {
    const stuck = { ...base, runStatus: "running", runStarted: new Date(NOW.getTime() - 5 * 3600_000) };
    expect(sourceHealth({ ...stuck, failingSince: stuck.runStarted }, NOW).status).toBe("failing");
    const live = { ...base, runStatus: "running", runStarted: new Date(NOW.getTime() - 600_000) };
    expect(sourceHealth({ ...live, failingSince: live.runStarted }, NOW).status).toBe("ok");
  });

  it("flags sources quiet for 1.5x their cadence, never irregular ones", () => {
    expect(sourceHealth({ ...base, lastChanged: daysAgo(46), failingSince: null }, NOW).status).toBe("stale");
    expect(sourceHealth({ ...base, lastChanged: daysAgo(44), failingSince: null }, NOW).status).toBe("ok");
    const irregular = { ...base, cadence: "irregular", lastChanged: daysAgo(900), failingSince: null };
    expect(sourceHealth(irregular, NOW).status).toBe("ok");
  });
});
