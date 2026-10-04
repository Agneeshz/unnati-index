import type { Metadata } from "next";
import Link from "next/link";
import { locale as rootLocale } from "next/root-params";
import { isLocale, type Locale } from "@/i18n/config";
import { type Dictionary, getDictionary } from "@/i18n/dictionaries";
import { getCategories, getIndicators } from "@/lib/data";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.ui.indicators.title };
}

export default async function IndicatorsPage() {
  const dict = await getDictionary();
  const lang = await rootLocale();
  const locale: Locale = isLocale(lang) ? lang : "en";
  const [indicators, categoryList] = await Promise.all([getIndicators(), getCategories()]);
  const categories = categoryList.filter((c) => indicators.some((i) => i.categoryId === c.id));

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <h1 className="text-3xl font-bold tracking-tight">{dict.ui.indicators.title}</h1>
      <p className="mt-3 max-w-3xl text-muted">{dict.ui.indicators.intro}</p>
      {categories.map(({ id: category, name }) => (
        <section key={category} aria-labelledby={`cat-${category}`} className="mt-8">
          <h2 id={`cat-${category}`} className="text-xl font-semibold">
            {name}
          </h2>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {indicators
              .filter((i) => i.categoryId === category)
              .map((i) => (
                <li key={i.id} className="rounded-md border border-border bg-surface px-3 py-2">
                  <Link href={`/${locale}/indicators/${i.id}`} className="font-medium hover:underline">
                    {i.name}
                  </Link>
                  {i.pillarId && (
                    <p className="text-xs text-muted">
                      {dict.pillars[i.pillarId as keyof Dictionary["pillars"]]?.name ?? i.pillarId}
                    </p>
                  )}
                </li>
              ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
