import en from "@/i18n/dictionaries/en.json";
import hi from "@/i18n/dictionaries/hi.json";
import { getIndicators, getReleases } from "@/lib/data";

const SITE = process.env.SITE_URL ?? "https://unnati-index.vercel.app";

function xml(text: string) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** RSS 2.0 feed of data releases: one item per load that added or revised figures. */
export async function GET(_request: Request, { params }: RouteContext<"/[locale]/updates/rss.xml">) {
  const { locale } = await params;
  // Route handlers can't read the locale root param yet, so the dictionary is picked directly.
  const dict = locale === "hi" ? hi : en;
  const [releases, indicators] = await Promise.all([getReleases(50), getIndicators(locale)]);
  const names = new Map(indicators.map((i) => [i.id, i.name]));
  const page = `${SITE}/${locale}/updates`;
  const items = releases
    .map((r) => {
      const periods = r.periods.length ? ` (${r.periods.slice(0, 3).join(", ")})` : "";
      const what = r.indicators.map((id) => names.get(id) ?? id).join(", ");
      const description = [r.summary, what].filter(Boolean).join(": ");
      return `    <item>
      <title>${xml(`${r.title}${periods}`)}</title>
      <link>${page}#release-${r.id}</link>
      <guid isPermaLink="false">unnati-release-${r.id}</guid>
      <pubDate>${new Date(r.happenedAt).toUTCString()}</pubDate>
      <category>${xml(r.source)}</category>
      <description>${xml(description)}</description>
    </item>`;
    })
    .join("\n");
  const body = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>${xml(`${dict.site.name}: ${dict.ui.updates.title}`)}</title>
    <link>${page}</link>
    <atom:link href="${page}/rss.xml" rel="self" type="application/rss+xml"/>
    <description>${xml(dict.ui.updates.intro)}</description>
    <language>${locale === "hi" ? "hi-IN" : "en-IN"}</language>
${items}
  </channel>
</rss>
`;
  return new Response(body, { headers: { "Content-Type": "application/rss+xml; charset=utf-8" } });
}
