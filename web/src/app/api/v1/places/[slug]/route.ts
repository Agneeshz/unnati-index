import { apiCity, apiError, apiLang, apiObservation, apiPlace, apiRankings, apiResponse } from "@/lib/api";
import {
  getCities,
  getIndicators,
  getLatestEdition,
  getPlaceObservations,
  getPlaces,
  getScores,
} from "@/lib/data";

/** One place: its details, every indicator value and (states and UTs) its latest scores. */
export async function GET(request: Request, { params }: RouteContext<"/api/v1/places/[slug]">) {
  const { slug } = await params;
  const [places, cities, edition] = await Promise.all([getPlaces(), getCities(), getLatestEdition()]);
  const place = places.find((p) => p.slug === slug);
  const city = cities.find((c) => c.slug === slug);
  if (!place && !city) return apiError(404, `No place with slug "${slug}". See /api/v1/places.`);
  const [observations, indicators, scores] = await Promise.all([
    getPlaceObservations(slug),
    getIndicators(apiLang(request)),
    place && edition != null ? getScores(edition) : Promise.resolve([]),
  ]);
  const names = new Map(indicators.map((i) => [i.id, { name: i.name, unit: i.unit }]));
  return apiResponse({
    ...(place ? apiPlace(place) : apiCity(city!)),
    rankings: place && edition != null
      ? { edition, ...apiRankings(scores.filter((s) => s.slug === slug))[0] }
      : null,
    observations: observations.map((o) => ({
      ...apiObservation(o),
      indicator: names.get(o.indicatorId)?.name ?? null,
      unit: names.get(o.indicatorId)?.unit ?? null,
    })),
  });
}
