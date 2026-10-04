import type { Metadata } from "next";
import Link from "next/link";
import { locale as rootLocale } from "next/root-params";
import { ScoreBar } from "@/components/score";
import { isLocale, type Locale } from "@/i18n/config";
import { getDictionary } from "@/i18n/dictionaries";
import { getIndices, getLatestEdition, getPlaces, getScores } from "@/lib/data";
import { fill } from "@/lib/present";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.ui.indices.title };
}

export default async function IndicesPage() {
  const dict = await getDictionary();
  const lang = await rootLocale();
  const locale: Locale = isLocale(lang) ? lang : "en";
  const edition = await getLatestEdition();
  const [indices, places, scores] = await Promise.all([
    getIndices(),
    getPlaces(),
    edition != null ? getScores(edition, "composite") : Promise.resolve([]),
  ]);
  const placeBySlug = new Map(places.map((p) => [p.slug, p]));

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <h1 className="text-3xl font-bold tracking-tight">{dict.ui.indices.title}</h1>
      <p className="mt-3 max-w-3xl text-muted">{dict.ui.indices.intro}</p>

      <ul className="mt-8 grid gap-4 sm:grid-cols-2">
        {indices.map((index) => {
          const leaders = scores
            .filter((s) => s.key === index.id && s.score != null && s.rank != null)
            .sort((a, b) => (a.rank ?? 0) - (b.rank ?? 0))
            .slice(0, 3);
          return (
            <li key={index.id} className="flex flex-col rounded-lg border border-border bg-surface p-4">
              <h2 className="text-lg font-semibold">
                <Link href={`/${locale}/indices/${index.id}`} className="hover:underline">
                  {index.name}
                </Link>
              </h2>
              {index.inspiredBy && (
                <p className="text-xs text-muted">{fill(dict.ui.indices.inspiredBy, { name: index.inspiredBy })}</p>
              )}
              <p className="mt-2 text-sm text-muted">{index.description}</p>
              <p className="mt-3 text-xs font-medium tracking-wide text-muted uppercase">{dict.ui.indices.leaders}</p>
              <ol className="mt-1 space-y-1 text-sm">
                {leaders.map((s) => {
                  const place = placeBySlug.get(s.slug);
                  return (
                    <li key={s.slug} className="flex items-center justify-between gap-2">
                      <span className="truncate">
                        <span className="tabular-nums text-muted">{s.rank}.</span>{" "}
                        {locale === "hi" && place?.nameHi ? place.nameHi : place?.name}
                      </span>
                      <ScoreBar score={s.score} locale={locale} />
                    </li>
                  );
                })}
              </ol>
              <Link
                href={`/${locale}/indices/${index.id}`}
                className="mt-4 text-sm font-medium text-accent underline-offset-2 hover:underline"
              >
                {dict.ui.indices.open} →
              </Link>
            </li>
          );
        })}
      </ul>

      <section aria-labelledby="also" className="mt-12 grid gap-8 sm:grid-cols-2">
        <div>
          <h2 id="also" className="text-xl font-semibold">
            {dict.ui.indices.otherTitle}
          </h2>
          <p className="mt-2 text-sm text-muted">{dict.ui.indices.otherBody}</p>
          <ul className="mt-3 space-y-1 text-sm">
            <li>
              <Link href={`/${locale}/indicators/consumption-gini`} className="underline underline-offset-2">
                Consumption inequality (Gini)
              </Link>
            </li>
            <li>
              <Link href={`/${locale}/indicators/mpi-headcount`} className="underline underline-offset-2">
                Multidimensional Poverty Index (NITI Aayog)
              </Link>
            </li>
          </ul>
        </div>
        <div>
          <h2 className="text-xl font-semibold">{dict.ui.indices.notBuiltTitle}</h2>
          <p className="mt-2 text-sm text-muted">{dict.ui.indices.notBuiltBody}</p>
        </div>
      </section>
    </div>
  );
}
