import { describe, expect, it } from "vitest";
import { apiRankings, apiSource } from "./api";
import type { DatasetStatus, ScoreRow } from "./data";

const row = (slug: string, level: ScoreRow["level"], key: string, score: number, rank: number): ScoreRow => ({
  slug,
  level,
  key,
  score,
  coverage: 1,
  rank,
  rankPeer: rank,
  rankPrev: null,
  rankPeerPrev: null,
  periodLabel: null,
});

describe("apiRankings", () => {
  it("groups each place's index and pillar scores, best rank first, without indicator rows", () => {
    const out = apiRankings([
      row("bihar", "composite", "composite", 40, 2),
      row("keralam", "pillar", "health", 90, 1),
      row("keralam", "composite", "composite", 75, 1),
      row("keralam", "indicator", "imr", 99, 1),
    ]);
    expect(out.map((p) => p.place_slug)).toEqual(["keralam", "bihar"]);
    expect(out[0].unnati_index).toMatchObject({ score: 75, rank: 1 });
    expect(Object.keys(out[0].pillars)).toEqual(["health"]);
  });
});

describe("apiSource", () => {
  const base: DatasetStatus = {
    id: "bprd_dopo",
    title: "Data on Police Organisations",
    source: "BPR&D",
    cadence: "annual",
    lastChecked: null,
    lastChanged: null,
    landingUrl: null,
    health: { status: "ok" },
  };

  it("carries the status and since when", () => {
    expect(apiSource(base)).toMatchObject({ status: "ok", status_since: null });
    const failing = apiSource({ ...base, health: { status: "failing", since: "2026-10-08T00:00:00.000Z" } });
    expect(failing).toMatchObject({ status: "failing", status_since: "2026-10-08T00:00:00.000Z" });
  });
});
