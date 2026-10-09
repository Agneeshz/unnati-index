import { isLocale } from "@/i18n/config";
import { buildSearchIndex } from "@/lib/search-index";

/** The search box's index (fetched once, on first focus). Changes only when the data does. */
export async function GET(_request: Request, { params }: RouteContext<"/[locale]/search-index.json">) {
  const { locale } = await params;
  const entries = await buildSearchIndex(isLocale(locale) ? locale : "en");
  return Response.json(entries, {
    headers: { "Cache-Control": "public, max-age=3600, s-maxage=86400, stale-while-revalidate=86400" },
  });
}
