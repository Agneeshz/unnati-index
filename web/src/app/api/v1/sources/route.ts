import { apiResponse, apiSource } from "@/lib/api";
import { getDatasets } from "@/lib/data";

/** Every dataset: publisher, release cadence, when it was last checked and its status. */
export async function GET() {
  return apiResponse((await getDatasets()).map(apiSource));
}
