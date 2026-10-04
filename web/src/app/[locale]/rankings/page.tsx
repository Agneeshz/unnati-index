import type { Metadata } from "next";
import Link from "next/link";
import { locale as rootLocale } from "next/root-params";
import { BandLabel, RankChange, ScoreBar } from "@/components/score";
import { isLocale, type Locale } from "@/i18n/config";
import { getDictionary } from "@/i18n/dictionaries";
import { COMPOSITE, getLatestEdition, getPillars, getPlaces, getScores } from "@/lib/data";
import { fill, formatScore, PEER_GROUPS } from "@/lib/present";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.ui.nav.rankings };
}

export default async function RankingsPage() {
  const dict = await getDictionary();
  const lang = await rootLocale();
  const locale: Locale = isLocale(lang) ? lang : "en";
  const edition = await getLatestEdition();
  if (edition == null) return <p className="mx-auto max-w-5xl px-4 py-12">{dict.home.status}</p>;
  const [places, pillars, scores] = await Promise.all([getPlaces(), getPillars(), getScores(edition)]);
  const byKey = new Map(scores.map((s) => [`${s.slug}|${s.level}|${s.key}`, s]));

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <h1 className="text-3xl font-bold tracking-tight">{fill(dict.ui.rankings.title, { year: edition })}</h1>
      <p className="mt-3 max-w-3xl text-muted">{dict.ui.rankings.intro}</p>

      {PEER_GROUPS.map((group) => {
        const members = places
          .filter((p) => p.peerGroup === group)
          .map((p) => ({ place: p, composite: byKey.get(`${p.slug}|composite|${COMPOSITE}`) }))
          .sort(
            (a, b) =>
              (a.composite?.rankPeer ?? 999) - (b.composite?.rankPeer ?? 999) ||
              a.place.name.localeCompare(b.place.name),
          );
        return (
          <section key={group} aria-labelledby={`group-${group}`} className="mt-10">
            <h2 id={`group-${group}`} className="text-xl font-semibold">
              {dict.ui.peerGroups[group]}
            </h2>
            <div className="mt-3 overflow-x-auto rounded-lg border border-border bg-surface">
              <table className="w-full min-w-[56rem] text-sm">
                <caption className="sr-only">
                  {dict.ui.peerGroups[group]}: {fill(dict.ui.rankings.title, { year: edition })}
                </caption>
                <thead className="border-b border-border text-left text-muted">
                  <tr>
                    <th scope="col" className="px-3 py-2 font-medium">
                      {dict.ui.common.rank}
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      {dict.ui.common.place}
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      {dict.ui.rankings.overall}
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      {dict.ui.common.change}
                    </th>
                    {pillars.map((p) => (
                      <th key={p.id} scope="col" className="px-2 py-2 text-right font-medium" title={p.name}>
                        {dict.pillars[p.id as keyof typeof dict.pillars]?.name ?? p.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {members.map(({ place, composite }) => (
                    <tr key={place.slug} className="border-b border-border last:border-0 hover:bg-accent-soft/40">
                      <td className="px-3 py-2 tabular-nums">{composite?.rankPeer ?? "–"}</td>
                      <th scope="row" className="px-3 py-2 text-left font-medium">
                        <Link
                          href={`/${locale}/states/${place.slug}`}
                          className="underline-offset-2 hover:underline"
                        >
                          {locale === "hi" && place.nameHi ? place.nameHi : place.name}
                        </Link>
                      </th>
                      <td className="px-3 py-2">
                        {composite?.score != null ? (
                          <span className="flex flex-wrap items-center gap-2">
                            <ScoreBar score={composite.score} locale={locale} />
                            <BandLabel score={composite.score} dict={dict} />
                          </span>
                        ) : (
                          <span className="text-muted">{dict.ui.common.noScore}</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {composite?.score != null && (
                          <RankChange rank={composite.rankPeer} previous={composite.rankPeerPrev} dict={dict} />
                        )}
                      </td>
                      {pillars.map((p) => {
                        const s = byKey.get(`${place.slug}|pillar|${p.id}`);
                        return (
                          <td key={p.id} className="px-2 py-2 text-right tabular-nums">
                            {s?.score != null ? formatScore(s.score, locale) : <span className="text-muted">–</span>}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
    </div>
  );
}
