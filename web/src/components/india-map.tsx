import { MapTooltip } from "@/components/map-tooltip";
import { locale } from "next/root-params";
import { getDictionary } from "@/i18n/dictionaries";
import { getPlaces } from "@/lib/data";
import { breaks, classOf, indiaShapes, MAP_HEIGHT, MAP_WIDTH, RAMP, SMALL_PLACES } from "@/lib/map";

export type MapDatum = { value: number; label: string };

/**
 * Choropleth of the states and UTs: one sequential hue, quantile classes, hatched grey for
 * places without data, markers for places too small to see. Every value is also in the table
 * beside the map, so the map is never the only way to read it.
 */
export async function IndiaMap({
  data,
  title,
  formatBreak,
  notAvailable,
  note,
  hrefFor,
}: {
  data: Record<string, MapDatum | undefined>;
  title: string;
  formatBreak: (value: number) => string;
  notAvailable: string;
  note?: string;
  hrefFor?: (slug: string) => string;
}) {
  const [dict, places, lang] = await Promise.all([getDictionary(), getPlaces(), locale()]);
  const hindi = lang === "hi";
  const placeName = new Map(places.map((p) => [p.slug, hindi && p.nameHi ? p.nameHi : p.name]));
  const shapes = indiaShapes().map((s) => ({ ...s, name: placeName.get(s.slug) ?? s.name }));
  const values = Object.values(data).filter((d): d is MapDatum => d != null).map((d) => d.value);
  const cuts = breaks(values);
  const fill = (slug: string) => {
    const d = data[slug];
    return d ? RAMP[classOf(d.value, cuts)] : "url(#no-data)";
  };
  const legend = [
    ...(cuts.length
      ? [
          { color: RAMP[classOf(-Infinity, cuts)], text: `< ${formatBreak(cuts[0])}` },
          ...cuts.map((cut, i) => ({
            color: RAMP[classOf(cut, cuts)],
            text: i + 1 < cuts.length ? `${formatBreak(cut)} – ${formatBreak(cuts[i + 1])}` : `≥ ${formatBreak(cut)}`,
          })),
        ]
      : values.length
        ? [{ color: RAMP[RAMP.length - 1], text: formatBreak(values[0]) }]
        : []),
    { color: "url(#no-data)", text: notAvailable },
  ];

  return (
    <figure className="rounded-lg border border-border bg-surface p-3">
      <MapTooltip>
        <svg
          viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
          role="img"
          aria-label={title}
          className="mx-auto h-auto w-full max-w-md"
        >
          <defs>
            <pattern id="no-data" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="6" height="6" className="fill-surface" />
              <line x1="1" y1="0" x2="1" y2="6" className="stroke-muted" strokeWidth="1.2" strokeOpacity="0.55" />
            </pattern>
          </defs>
          {[...shapes].sort((a, b) => Number(!data[a.slug]) - Number(!data[b.slug])).map((s) => {
            const d = data[s.slug];
            const tip = `${s.name}: ${d ? d.label : notAvailable}`;
            const shape = (
              <path
                d={s.d}
                fill={fill(s.slug)}
                // No-data shapes get a visible outline so India's border stays complete (e.g. Ladakh).
                className={d ? "stroke-surface" : "stroke-muted"}
                strokeWidth={d ? 0.8 : 1}
                data-tip={tip}
                tabIndex={0}
                aria-label={tip}
              >
                <title>{tip}</title>
              </path>
            );
            return hrefFor ? (
              <a key={s.slug} href={hrefFor(s.slug)} aria-label={tip}>
                {shape}
              </a>
            ) : (
              <g key={s.slug}>{shape}</g>
            );
          })}
          {/* Markers for places too small to see, with a surface ring so they read over neighbours. */}
          {shapes
            .filter((s) => SMALL_PLACES.has(s.slug))
            .map((s) => {
              const d = data[s.slug];
              const tip = `${s.name}: ${d ? d.label : notAvailable}`;
              return (
                <circle
                  key={`m-${s.slug}`}
                  cx={s.cx}
                  cy={s.cy}
                  r={6}
                  fill={fill(s.slug)}
                  className="stroke-fg"
                  strokeWidth={1}
                  data-tip={tip}
                >
                  <title>{tip}</title>
                </circle>
              );
            })}
        </svg>
      </MapTooltip>
      <figcaption className="mt-2 space-y-2 text-xs text-muted">
        <ul className="flex flex-wrap gap-x-3 gap-y-1" aria-label={dict.ui.map.legend}>
          {legend.map((item) => (
            <li key={item.text} className="flex items-center gap-1.5">
              <svg aria-hidden="true" width="14" height="14" className="shrink-0">
                <rect width="14" height="14" rx="3" fill={item.color} className="stroke-border" />
              </svg>
              {item.text}
            </li>
          ))}
        </ul>
        {note && <p>{note}</p>}
        <p>{dict.ui.map.disclaimer}</p>
      </figcaption>
    </figure>
  );
}
