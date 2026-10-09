import type { Metadata } from "next";
import Link from "next/link";
import { locale as rootLocale } from "next/root-params";
import { Suspense } from "react";
import { isLocale, type Locale } from "@/i18n/config";
import { getDictionary } from "@/i18n/dictionaries";
import { fill } from "@/lib/present";
import { search, type SearchType } from "@/lib/search";
import { buildSearchIndex } from "@/lib/search-index";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.ui.search.title, robots: { index: false } };
}

export default function SearchPage(props: PageProps<"/[locale]/search">) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <Suspense fallback={<p className="text-muted">…</p>}>
        <Results searchParams={props.searchParams} />
      </Suspense>
    </div>
  );
}

const ORDER: SearchType[] = ["state", "ut", "city", "pillar", "index", "indicator", "page"];

async function Results({ searchParams }: { searchParams: PageProps<"/[locale]/search">["searchParams"] }) {
  const [dict, lang, query] = await Promise.all([getDictionary(), rootLocale(), searchParams]);
  const locale: Locale = isLocale(lang) ? lang : "en";
  const q = typeof query.q === "string" ? query.q.slice(0, 100) : "";
  const results = q.trim() ? search(await buildSearchIndex(locale), q, 60) : [];
  // Group by kind, the group with the best match first, keeping the ranking within each group.
  const groups = ORDER.map((type) => ({ type, items: results.filter((r) => r.type === type) }))
    .filter((g) => g.items.length)
    .sort((a, b) => b.items[0].score - a.items[0].score);

  return (
    <>
      <h1 className="text-3xl font-bold tracking-tight">{dict.ui.search.title}</h1>
      <p className="mt-2 text-muted">{dict.ui.search.intro}</p>
      <form action={`/${locale}/search`} method="get" role="search" className="mt-6 flex gap-2">
        <label htmlFor="search-page-q" className="sr-only">
          {dict.ui.search.label}
        </label>
        <input
          id="search-page-q"
          name="q"
          type="search"
          defaultValue={q}
          placeholder={dict.ui.search.placeholder}
          className="w-full rounded-md border border-border bg-surface px-3 py-2"
        />
        <button type="submit" className="rounded-md bg-accent px-4 py-2 font-medium text-surface hover:opacity-90">
          {dict.ui.search.label}
        </button>
      </form>
      {q.trim() && (
        <section aria-live="polite" className="mt-8">
          <h2 className="text-lg font-semibold">{fill(dict.ui.search.resultsFor, { q })}</h2>
          {groups.length === 0 ? (
            <p className="mt-3 text-muted">{fill(dict.ui.search.noResults, { q })}</p>
          ) : (
            groups.map((g) => (
              <div key={g.type} className="mt-5">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">{dict.ui.search.types[g.type]}</h3>
                <ul className="mt-2 divide-y divide-border rounded-lg border border-border bg-surface">
                  {g.items.map((r) => (
                    <li key={r.href}>
                      <Link
                        href={r.href}
                        className="flex items-baseline justify-between gap-3 px-4 py-2 hover:bg-accent-soft"
                      >
                        <span className="font-medium">{r.title}</span>
                        {r.subtitle && <span className="text-sm text-muted">{r.subtitle}</span>}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </section>
      )}
    </>
  );
}
