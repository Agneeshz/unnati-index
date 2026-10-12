import { apiError, apiRankings, apiResponse } from "@/lib/api";
import { getLatestEdition, getScores, METHODOLOGY } from "@/lib/data";

/** Unnati Index and pillar scores with overall and peer-group ranks, latest edition by default. */
export async function GET(request: Request) {
  const requested = new URL(request.url).searchParams.get("edition");
  const edition = requested ? Number(requested) : await getLatestEdition();
  if (edition == null || !Number.isInteger(edition)) return apiError(400, "edition must be a year, e.g. 2026");
  const scores = await getScores(edition);
  if (scores.length === 0) return apiError(404, `No rankings for edition ${edition}.`);
  return apiResponse({ edition, methodology_version: METHODOLOGY, places: apiRankings(scores) });
}
