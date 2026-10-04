import type { Metadata } from "next";
import { getDictionary } from "@/i18n/dictionaries";
import { getDatasets } from "@/lib/data";

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return { title: dict.ui.sources.title };
}

export default async function SourcesPage() {
  const dict = await getDictionary();
  const datasets = await getDatasets();
  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <h1 className="text-3xl font-bold tracking-tight">{dict.ui.sources.title}</h1>
      <p className="mt-3 max-w-3xl text-muted">{dict.ui.sources.intro}</p>
      <div className="mt-6 overflow-x-auto rounded-lg border border-border bg-surface">
        <table className="w-full min-w-[44rem] text-sm">
          <thead className="border-b border-border text-left text-muted">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">
                {dict.ui.common.source}
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                {dict.ui.sources.cadence}
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                {dict.ui.sources.lastChanged}
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                {dict.ui.sources.lastChecked}
              </th>
            </tr>
          </thead>
          <tbody>
            {datasets.map((d) => (
              <tr key={d.id} className="border-b border-border last:border-0">
                <th scope="row" className="px-3 py-2 text-left font-normal">
                  {d.landingUrl ? (
                    <a href={d.landingUrl} className="font-medium hover:underline" rel="noopener">
                      {d.title}
                    </a>
                  ) : (
                    <span className="font-medium">{d.title}</span>
                  )}
                  <span className="block text-muted">{d.source}</span>
                </th>
                <td className="px-3 py-2">{d.cadence}</td>
                <td className="px-3 py-2 tabular-nums">{d.lastChanged?.slice(0, 10) ?? "–"}</td>
                <td className="px-3 py-2 tabular-nums">{d.lastChecked?.slice(0, 10) ?? "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
