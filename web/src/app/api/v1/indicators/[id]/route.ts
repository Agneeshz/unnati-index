import { apiError, apiIndicator, apiLang, apiObservation, apiResponse } from "@/lib/api";
import { getIndicatorObservations, getIndicatorSources, getIndicators } from "@/lib/data";

/** One indicator with every value (all places and periods), or one place's with ?place=. */
export async function GET(request: Request, { params }: RouteContext<"/api/v1/indicators/[id]">) {
  const { id } = await params;
  const [indicators, sources] = await Promise.all([getIndicators(apiLang(request)), getIndicatorSources()]);
  const indicator = indicators.find((i) => i.id === id);
  if (!indicator) return apiError(404, `No indicator "${id}". See /api/v1/indicators.`);
  const place = new URL(request.url).searchParams.get("place");
  const observations = (await getIndicatorObservations(id)).filter((o) => !place || o.slug === place);
  return apiResponse({
    ...apiIndicator(indicator, sources.find((s) => s.indicatorId === id)),
    observations: observations.map(apiObservation),
  });
}
