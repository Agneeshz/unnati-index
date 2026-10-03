import { notFound } from "next/navigation";
import { locale } from "next/root-params";
import { isLocale, type Locale } from "./config";
import type en from "./dictionaries/en.json";

export type Dictionary = typeof en;

const dictionaries: Record<Locale, () => Promise<Dictionary>> = {
  en: () => import("./dictionaries/en.json").then((m) => m.default),
  hi: () => import("./dictionaries/hi.json").then((m) => m.default),
};

/** UI strings for the current route's locale (read from the `[locale]` root param). */
export async function getDictionary(): Promise<Dictionary> {
  const current = await locale();
  if (!isLocale(current)) notFound();
  return dictionaries[current]();
}
