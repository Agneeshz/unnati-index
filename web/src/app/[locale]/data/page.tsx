import type { Metadata } from "next";
import Link from "next/link";
import { locale as rootLocale } from "next/root-params";
import { isLocale, type Locale } from "@/i18n/config";
import { getDictionary } from "@/i18n/dictionaries";
import { getCategories, getIndicatorSources, getIndicators } from "@/lib/data";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.ui.data.title, description: dict.ui.data.intro };
}

export default async function DataPage() {
  const [dict, lang] = await Promise.all([getDictionary(), rootLocale()]);
  const locale: Locale = isLocale(lang) ? lang : "en";
  const [indicators, categories, sources] = await Promise.all([
    getIndicators(),
    getCategories(),
    getIndicatorSources(),
  ]);
  const sourceOf = new Map(sources.map((s) => [s.indicatorId, s]));

  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <h1 className="text-3xl font-bold tracking-tight">{dict.ui.data.title}</h1>
      <p className="mt-2 max-w-3xl text-muted">{dict.ui.data.intro}</p>

      <section aria-labelledby="licence" className="mt-6 rounded-lg border border-border bg-accent-soft px-4 py-3 text-sm">
        <h2 id="licence" className="font-semibold">
          {dict.ui.data.licenceTitle}
        </h2>
        <p className="mt-1">{dict.ui.data.licence}</p>
        <p className="mt-2 font-mono text-xs">{dict.ui.data.citation}</p>
      </section>

      <section aria-labelledby="bulk" className="mt-8">
        <h2 id="bulk" className="text-xl font-semibold">
          {dict.ui.data.bulkTitle}
        </h2>
        <ul className="mt-3 space-y-2">
          <li>
            <a href="/data/all.csv" className="font-medium underline underline-offset-2" download>
              {dict.ui.data.all}
            </a>
            <span className="text-sm text-muted"> · {dict.ui.data.allNote}</span>
          </li>
          <li>
            <a href="/data/indicators.csv" className="font-medium underline underline-offset-2" download>
              {dict.ui.data.catalogue}
            </a>
            <span className="text-sm text-muted"> · {dict.ui.data.catalogueNote}</span>
          </li>
        </ul>
      </section>

      <section aria-labelledby="by-indicator" className="mt-10">
        <h2 id="by-indicator" className="text-xl font-semibold">
          {dict.ui.data.byIndicator}
        </h2>
        {categories.map((category) => {
          const items = indicators.filter((i) => i.categoryId === category.id);
          if (!items.length) return null;
          return (
            <div key={category.id} className="mt-5">
              <h3 className="font-semibold">{category.name}</h3>
              <ul className="mt-2 divide-y divide-border rounded-lg border border-border bg-surface text-sm">
                {items.map((i) => (
                  <li key={i.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 py-2">
                    <span>
                      <Link href={`/${locale}/indicators/${i.id}`} className="font-medium hover:underline">
                        {i.name}
                      </Link>
                      {sourceOf.get(i.id)?.source && (
                        <span className="text-muted"> · {sourceOf.get(i.id)?.source}</span>
                      )}
                    </span>
                    <a href={`/data/${i.id}.csv`} className="text-accent underline underline-offset-2" download>
                      CSV
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </section>
    </div>
  );
}
