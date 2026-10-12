import type { MetadataRoute } from "next";
import { locales } from "@/i18n/config";
import { getCities, getIndicators, getIndices, getPillars, getPlaces } from "@/lib/data";
import { SITE_URL } from "@/lib/site";

const PAGES = [
  "",
  "/rankings",
  "/cities",
  "/indicators",
  "/indices",
  "/compare",
  "/updates",
  "/sources",
  "/methodology",
  "/data",
];

/** Every page in both languages, each listing its other-language version. */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [places, cities, indicators, pillars, indices] = await Promise.all([
    getPlaces(),
    getCities(),
    getIndicators("en"),
    getPillars(),
    getIndices("en"),
  ]);
  const paths = [
    ...PAGES,
    ...places.filter((p) => p.type !== "country").map((p) => `/states/${p.slug}`),
    ...cities.map((c) => `/cities/${c.slug}`),
    ...indicators.map((i) => `/indicators/${i.id}`),
    ...pillars.map((p) => `/pillars/${p.id}`),
    ...indices.map((i) => `/indices/${i.id}`),
  ];
  return paths.flatMap((path) => {
    const languages = Object.fromEntries(locales.map((l) => [l, `${SITE_URL}/${l}${path}`]));
    return locales.map((l) => ({ url: `${SITE_URL}/${l}${path}`, alternates: { languages } }));
  });
}
