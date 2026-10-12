import { apiResponse } from "@/lib/api";
import { METHODOLOGY } from "@/lib/data";
import { SITE_URL } from "@/lib/site";

/** Index of the public API. */
export async function GET() {
  const base = `${SITE_URL}/api/v1`;
  return apiResponse({
    version: "v1",
    methodology_version: METHODOLOGY,
    endpoints: {
      places: `${base}/places`,
      place: `${base}/places/{slug}`,
      indicators: `${base}/indicators`,
      indicator: `${base}/indicators/{id}`,
      rankings: `${base}/rankings`,
      sources: `${base}/sources`,
    },
    parameters: {
      lang: "hi for Hindi indicator text (indicators, indicator, place)",
      place: "indicator: only this place's values",
      edition: "rankings: a past edition (year)",
    },
  });
}
