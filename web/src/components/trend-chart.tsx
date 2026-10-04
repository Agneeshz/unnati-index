import { MapTooltip } from "@/components/map-tooltip";

export type TrendPoint = { label: string; value: number; tip: string };
export type TrendSeries = {
  name: string;
  points: TrendPoint[];
  kind: "primary" | "reference";
};

const W = 320;
const H = 150;
const PAD = { top: 14, right: 46, bottom: 26, left: 10 };

/**
 * A small line chart: one primary series (the state, in the accent colour) and an optional
 * reference series (India, dashed grey). One y-axis; the x-axis is the union of periods in
 * time order. Values are direct-labelled at the last point, and every point has a hover tip.
 */
export function TrendChart({
  title,
  series,
  periods,
  format,
}: {
  title: string;
  series: TrendSeries[];
  periods: string[]; // ordered x-axis labels
  format: (value: number) => string;
}) {
  const values = series.flatMap((s) => s.points.map((p) => p.value));
  if (values.length === 0 || periods.length < 2) return null;
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const span = max - min;
  min -= span * 0.12;
  max += span * 0.12;
  const x = (label: string) =>
    PAD.left +
    (periods.indexOf(label) / (periods.length - 1)) *
      (W - PAD.left - PAD.right);
  const y = (value: number) =>
    PAD.top + (1 - (value - min) / (max - min)) * (H - PAD.top - PAD.bottom);
  const path = (points: TrendPoint[]) =>
    points
      .filter((p) => periods.includes(p.label))
      .sort((a, b) => periods.indexOf(a.label) - periods.indexOf(b.label))
      .map(
        (p, i) =>
          `${i ? "L" : "M"}${x(p.label).toFixed(1)},${y(p.value).toFixed(1)}`,
      )
      .join("");
  const gridValues = [min + (max - min) * 0.25, min + (max - min) * 0.75];

  return (
    <figure className="rounded-lg border border-border bg-surface p-3">
      <figcaption className="text-sm font-medium">{title}</figcaption>
      <MapTooltip>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={title}
          className="mt-1 h-auto w-full"
        >
          {gridValues.map((g) => (
            <line
              key={g}
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(g)}
              y2={y(g)}
              className="stroke-border"
              strokeWidth={1}
            />
          ))}
          {[periods[0], periods[periods.length - 1]].map((label, i) => (
            <text
              key={`${label}-${i}`}
              x={x(label)}
              y={H - 6}
              textAnchor={i === 0 ? "start" : "end"}
              className="fill-muted text-[10px]"
            >
              {label}
            </text>
          ))}
          {series.map((s) => {
            const pts = s.points.filter((p) => periods.includes(p.label));
            if (pts.length === 0) return null;
            const last = pts.reduce((a, b) =>
              periods.indexOf(b.label) > periods.indexOf(a.label) ? b : a,
            );
            const primary = s.kind === "primary";
            return (
              <g key={s.name}>
                <path
                  d={path(pts)}
                  fill="none"
                  className={primary ? "stroke-accent" : "stroke-muted"}
                  strokeWidth={2}
                  strokeDasharray={primary ? undefined : "4 3"}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
                {pts.map((p) => (
                  <circle
                    key={p.label}
                    cx={x(p.label)}
                    cy={y(p.value)}
                    r={primary ? 3.5 : 2.5}
                    className={
                      primary
                        ? "fill-accent stroke-surface"
                        : "fill-muted stroke-surface"
                    }
                    strokeWidth={2}
                    data-tip={`${s.name}, ${p.tip}`}
                  >
                    <title>{`${s.name}, ${p.tip}`}</title>
                  </circle>
                ))}
                <text
                  x={x(last.label) + 6}
                  y={y(last.value) + 3}
                  className={
                    primary
                      ? "fill-fg text-[10px] font-semibold"
                      : "fill-muted text-[10px]"
                  }
                >
                  {format(last.value)}
                </text>
              </g>
            );
          })}
        </svg>
      </MapTooltip>
      {series.length > 1 && (
        <ul
          className="mt-1 flex flex-wrap gap-3 text-xs text-muted"
          aria-label="Legend"
        >
          {series.map((s) => (
            <li key={s.name} className="flex items-center gap-1.5">
              <svg aria-hidden="true" width="18" height="6">
                <line
                  x1="0"
                  x2="18"
                  y1="3"
                  y2="3"
                  strokeWidth="2"
                  className={
                    s.kind === "primary" ? "stroke-accent" : "stroke-muted"
                  }
                  strokeDasharray={s.kind === "primary" ? undefined : "4 3"}
                />
              </svg>
              {s.name}
            </li>
          ))}
        </ul>
      )}
    </figure>
  );
}
