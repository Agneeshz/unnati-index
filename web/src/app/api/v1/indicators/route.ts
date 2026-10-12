import { apiIndicator, apiLang, apiResponse } from "@/lib/api";
import { getIndicatorSources, getIndicators } from "@/lib/data";

/** The indicator catalogue: definitions, units, direction and source. */
export async function GET(request: Request) {
  const [indicators, sources] = await Promise.all([getIndicators(apiLang(request)), getIndicatorSources()]);
  const sourceOf = new Map(sources.map((s) => [s.indicatorId, s]));
  return apiResponse(indicators.map((i) => apiIndicator(i, sourceOf.get(i.id))));
}
