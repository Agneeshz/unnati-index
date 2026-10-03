export const locales = ["en", "hi"] as const;

export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "en";

// Locales offered automatically from the browser's language. Hindi pages exist and can be
// opened directly, but visitors are only sent there by default once translation is complete.
export const launchedLocales: readonly Locale[] = ["en"];

export function isLocale(value: string | undefined): value is Locale {
  return (locales as readonly string[]).includes(value ?? "");
}

/** Pick the best launched locale from an Accept-Language header such as "hi-IN,hi;q=0.9,en;q=0.8". */
export function negotiateLocale(acceptLanguage: string | null): Locale {
  const ranked = (acceptLanguage ?? "")
    .split(",")
    .map((part) => {
      const [tag, ...params] = part.trim().split(";");
      const q = params.find((p) => p.trim().startsWith("q="));
      return { lang: tag.toLowerCase().split("-")[0], q: q ? Number(q.trim().slice(2)) : 1 };
    })
    .filter(({ lang, q }) => lang && q > 0)
    .sort((a, b) => b.q - a.q);
  for (const { lang } of ranked) {
    if (isLocale(lang) && launchedLocales.includes(lang)) return lang;
  }
  return defaultLocale;
}
