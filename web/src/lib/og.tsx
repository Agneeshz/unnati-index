import { ImageResponse } from "next/og";

/**
 * Share-card layout for next/og images (1200×630). Images are always in English: the built-in
 * font has no Devanagari glyphs. Colours are the site's light theme.
 */
export const OG_SIZE = { width: 1200, height: 630 };
export const OG_TYPE = "image/png";

const C = { bg: "#fafaf8", fg: "#1c1d1f", muted: "#55585e", border: "#e2e2dd", accent: "#0f766e", soft: "#e3f1ef" };

export type OgRow = { label: string; value: string };

export function ogCard({
  eyebrow,
  title,
  big,
  bigNote,
  lines = [],
  rows = [],
}: {
  eyebrow: string;
  title: string;
  big?: string;
  bigNote?: string;
  lines?: string[];
  rows?: OgRow[];
}) {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          background: C.bg,
          color: C.fg,
          padding: "56px 64px",
          fontSize: 32,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ display: "flex", alignItems: "flex-end", gap: 5, padding: 9, background: C.accent, borderRadius: 10 }}>
            <div style={{ width: 9, height: 16, background: "white", borderRadius: 2 }} />
            <div style={{ width: 9, height: 26, background: "white", borderRadius: 2 }} />
            <div style={{ width: 9, height: 36, background: "white", borderRadius: 2 }} />
          </div>
          <div style={{ fontSize: 30, fontWeight: 700 }}>Unnati Index</div>
          <div style={{ fontSize: 26, color: C.muted, marginLeft: 8 }}>{eyebrow}</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", flexGrow: 1, justifyContent: "center" }}>
          <div style={{ fontSize: title.length > 40 ? 52 : 68, fontWeight: 700, lineHeight: 1.1 }}>{title}</div>
          {big && (
            <div style={{ display: "flex", alignItems: "baseline", gap: 18, marginTop: 18 }}>
              <div style={{ fontSize: 120, fontWeight: 700, color: C.accent, lineHeight: 1 }}>{big}</div>
              {bigNote && <div style={{ fontSize: 34, color: C.muted }}>{bigNote}</div>}
            </div>
          )}
          {lines.map((line) => (
            <div key={line} style={{ marginTop: 14, fontSize: 36 }}>
              {line}
            </div>
          ))}
          {rows.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", marginTop: 22, gap: 10 }}>
              {rows.map((r, i) => (
                <div
                  key={r.label}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "10px 18px",
                    borderRadius: 10,
                    background: i === 0 ? C.soft : "white",
                    border: `1px solid ${C.border}`,
                    fontSize: 32,
                  }}
                >
                  <div style={{ display: "flex" }}>{r.label}</div>
                  <div style={{ display: "flex", fontWeight: 700 }}>{r.value}</div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 24, color: C.muted }}>
          <div>Official data, refreshed daily</div>
          <div>unnati-index.vercel.app</div>
        </div>
      </div>
    ),
    OG_SIZE,
  );
}
