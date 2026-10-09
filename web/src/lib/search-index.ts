import "server-only";
import type { Locale } from "@/i18n/config";
import en from "@/i18n/dictionaries/en.json";
import hi from "@/i18n/dictionaries/hi.json";
import { getCategories, getIndicators, getIndices, getPillars, getSearchPlaces } from "@/lib/data";
import { normalize, type SearchEntry } from "@/lib/search";

const PAGES = ["rankings", "cities", "compare", "indices", "indicators", "updates", "methodology", "sources"] as const;

/**
 * Everything the site search can find, titled in `locale` but matched in both languages (a
 * Hindi query finds an English page's states and vice versa), with places' other names.
 */
export async function buildSearchIndex(locale: Locale): Promise<SearchEntry[]> {
  const dict = locale === "hi" ? hi : en;
  const [places, indicatorsEn, indicatorsHi, indicesEn, indicesHi, pillars, categories] = await Promise.all([
    getSearchPlaces(),
    getIndicators("en"),
    getIndicators("hi"),
    getIndices("en"),
    getIndices("hi"),
    getPillars(),
    getCategories(locale),
  ]);
  const local = (name: string, nameHi: string | null) => (locale === "hi" && nameHi ? nameHi : name);
  const both = (...names: (string | null | undefined)[]) => [...new Set(names.filter(Boolean).map((n) => normalize(n as string)))];
  const stateNames = new Map(places.filter((p) => p.type !== "city").map((p) => [p.slug, local(p.name, p.nameHi)]));
  const categoryName = new Map(categories.map((c) => [c.id, c.name]));
  const hiIndicator = new Map(indicatorsHi.map((i) => [i.id, i]));
  const hiIndex = new Map(indicesHi.map((i) => [i.id, i]));

  const entries: SearchEntry[] = [];
  for (const p of places) {
    entries.push({
      type: p.type,
      title: local(p.name, p.nameHi),
      subtitle: p.type === "city" ? stateNames.get(p.stateSlug ?? "") : dict.ui.search.types[p.type],
      href: `/${locale}/${p.type === "city" ? "cities" : "states"}/${p.slug}`,
      names: both(p.name, p.nameHi),
      aliases: p.aliases,
    });
  }
  for (const p of pillars) {
    const id = p.id as keyof typeof en.pillars;
    entries.push({
      type: "pillar",
      title: dict.pillars[id]?.name ?? p.name,
      subtitle: dict.ui.search.types.pillar,
      href: `/${locale}/pillars/${p.id}`,
      names: both(p.name, en.pillars[id]?.name, hi.pillars[id]?.name),
      text: normalize(`${en.pillars[id]?.description ?? ""} ${hi.pillars[id]?.description ?? ""}`),
    });
  }
  for (const x of indicesEn) {
    const h = hiIndex.get(x.id);
    entries.push({
      type: "index",
      title: locale === "hi" && h ? h.name : x.name,
      subtitle: dict.ui.search.types.index,
      href: `/${locale}/indices/${x.id}`,
      names: both(x.name, h?.name),
      text: normalize(`${x.description} ${h?.description ?? ""}`),
    });
  }
  for (const i of indicatorsEn) {
    const h = hiIndicator.get(i.id);
    entries.push({
      type: "indicator",
      title: locale === "hi" && h ? h.name : i.name,
      subtitle: categoryName.get(i.categoryId) ?? dict.ui.search.types.indicator,
      href: `/${locale}/indicators/${i.id}`,
      names: both(i.name, h?.name),
      text: normalize(`${i.description} ${h?.description ?? ""}`),
    });
  }
  for (const page of PAGES) {
    entries.push({
      type: "page",
      title: dict.ui.nav[page],
      subtitle: dict.ui.search.types.page,
      href: `/${locale}/${page}`,
      names: both(en.ui.nav[page], hi.ui.nav[page]),
    });
  }
  return entries;
}
