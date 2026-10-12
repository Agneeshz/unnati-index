import { apiCity, apiPlace, apiResponse } from "@/lib/api";
import { getCities, getPlaces } from "@/lib/data";

/** India, the states and UTs, and the cities. */
export async function GET() {
  const [places, cities] = await Promise.all([getPlaces(), getCities()]);
  return apiResponse([...places.map(apiPlace), ...cities.map(apiCity)]);
}
