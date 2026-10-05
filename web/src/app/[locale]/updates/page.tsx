import type { Metadata } from "next";
import Link from "next/link";
import { locale as rootLocale } from "next/root-params";
import { Suspense } from "react";
import { isLocale, type Locale } from "@/i18n/config";
import { type Dictionary, getDictionary } from "@/i18n/dictionaries";
import { getIndicators, getReleases } from "@/lib/data";
import { fill, releaseSummary } from "@/lib/present";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  const lang = await rootLocale();
  return {
    title: dict.ui.updates.title,
    description: dict.ui.updates.intro,
    alternates: { types: { "application/rss+xml": `/${lang}/updates/rss.xml` } },
  };
}

export default function UpdatesPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <Suspense fallback={<p className="text-muted">…</p>}>
        <Updates />
      </Suspense>
    </div>
  );
}

/** "4 Oct 2026" in Indian time, for grouping releases by day. */
function day(iso: string, locale: Locale) {
  return new Intl.DateTimeFormat(locale === "hi" ? "hi-IN" : "en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Kolkata",
  }).format(new Date(iso));
}

async function Updates() {
  const [dict, lang, releases, indicators] = await Promise.all([
    getDictionary(),
    rootLocale(),
    getReleases(150),
    getIndicators(),
  ]);
  const locale: Locale = isLocale(lang) ? lang : "en";
  const names = new Map(indicators.map((i) => [i.id, i.name]));
  const days = new Map<string, typeof releases>();
  for (const r of releases) {
    const key = day(r.happenedAt, locale);
    days.set(key, [...(days.get(key) ?? []), r]);
  }
  return (
    <>
      <h1 className="text-3xl font-bold tracking-tight">{dict.ui.updates.title}</h1>
      <p className="mt-2 max-w-3xl text-muted">{dict.ui.updates.intro}</p>
      <p className="mt-3 text-sm">
        <a href={`/${locale}/updates/rss.xml`} className="underline underline-offset-2">
          {dict.ui.updates.rss}
        </a>
      </p>
      {[...days].map(([date, items]) => (
        <section key={date} aria-label={date} className="mt-8">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">{date}</h2>
          <ul className="mt-2 space-y-3">
            {items.map((r) => (
              <Release key={r.id} release={r} dict={dict} locale={locale} names={names} />
            ))}
          </ul>
        </section>
      ))}
    </>
  );
}

function Release({
  release: r,
  dict,
  locale,
  names,
}: {
  release: Awaited<ReturnType<typeof getReleases>>[number];
  dict: Dictionary;
  locale: Locale;
  names: Map<string, string>;
}) {
  const shown = r.periods.slice(0, 3);
  return (
    <li id={`release-${r.id}`} className="rounded-lg border border-border bg-surface px-4 py-3">
      <p className="font-medium">
        {r.title} <span className="font-normal text-muted">· {r.source}</span>
      </p>
      {r.summary && <p className="mt-1 text-sm">{releaseSummary(r.summary, dict)}</p>}
      {shown.length > 0 && (
        <p className="mt-1 text-sm text-muted">
          {dict.ui.common.period}: {shown.join(", ")}
          {r.periods.length > shown.length ? ` ${fill(dict.ui.updates.more, { n: r.periods.length - shown.length })}` : ""}
        </p>
      )}
      <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-sm">
        {r.indicators.map((id) => (
          <li key={id}>
            <Link href={`/${locale}/indicators/${id}`} className="underline underline-offset-2">
              {names.get(id) ?? id}
            </Link>
          </li>
        ))}
        {r.sourceUrl && (
          <li>
            <a href={r.sourceUrl} rel="noopener" className="text-muted underline underline-offset-2">
              {dict.ui.common.source}
            </a>
          </li>
        )}
      </ul>
    </li>
  );
}
