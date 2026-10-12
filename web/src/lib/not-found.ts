import "server-only";
import { notFound, permanentRedirect } from "next/navigation";
import { getSearchPlaces } from "@/lib/data";
import { renamedSlug } from "@/lib/redirects";

/** For an unknown place slug: redirect old names to the current page, otherwise 404. */
export async function placeNotFound(kind: "states" | "cities", slug: string, locale: string): Promise<never> {
  const current = renamedSlug(await getSearchPlaces(), slug, kind === "states" ? ["state", "ut"] : ["city"]);
  if (current) permanentRedirect(`/${locale}/${kind}/${current}`);
  notFound();
}
