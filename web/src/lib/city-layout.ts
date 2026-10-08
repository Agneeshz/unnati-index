/** Label placement and crowding detection for city maps (pure geometry, no rendering). */

export type LayoutDot = { slug: string; name: string; x: number; y: number; r: number };
export type Label = { x: number; y: number; anchor: "start" | "middle" | "end" };
type Box = { x0: number; y0: number; x1: number; y1: number };

const FONT_PX = 12;

/** Rough rendered width of a label: Latin averages ~0.58em a character, Devanagari a bit more. */
export function labelWidth(text: string): number {
  const perChar = /[ऀ-ॿ]/.test(text) ? 0.66 : 0.58;
  return Math.ceil(text.length * perChar * FONT_PX) + 2;
}

const overlaps = (a: Box, b: Box) => a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;

/**
 * Labels for as many dots as fit, in priority order (the order given): each tries right, left,
 * above and below its dot, then the diagonals, and is placed only where it stays inside the frame
 * and clear of every other label and dot.
 */
export function placeLabels(
  dots: LayoutDot[],
  width: number,
  height: number,
  max = Number.POSITIVE_INFINITY,
): Map<string, Label> {
  const placed = new Map<string, Label>();
  const taken: Box[] = [];
  const dotBox = (d: LayoutDot): Box => ({ x0: d.x - d.r, y0: d.y - d.r, x1: d.x + d.r, y1: d.y + d.r });
  for (const d of dots) {
    if (placed.size >= max) break;
    const w = labelWidth(d.name);
    const gap = 4;
    const candidates: (Label & { box: Box })[] = [
      { x: d.x + d.r + gap, y: d.y + 4, anchor: "start", box: { x0: d.x + d.r + gap - 1, y0: d.y - 9, x1: d.x + d.r + gap + w, y1: d.y + 5 } },
      { x: d.x - d.r - gap, y: d.y + 4, anchor: "end", box: { x0: d.x - d.r - gap - w, y0: d.y - 9, x1: d.x - d.r - gap + 1, y1: d.y + 5 } },
      { x: d.x, y: d.y - d.r - 5, anchor: "middle", box: { x0: d.x - w / 2, y0: d.y - d.r - 18, x1: d.x + w / 2, y1: d.y - d.r - 2 } },
      { x: d.x, y: d.y + d.r + 14, anchor: "middle", box: { x0: d.x - w / 2, y0: d.y + d.r + 2, x1: d.x + w / 2, y1: d.y + d.r + 17 } },
      // Diagonals, when all four sides are taken.
      { x: d.x + d.r, y: d.y - d.r - 3, anchor: "start", box: { x0: d.x + d.r - 1, y0: d.y - d.r - 16, x1: d.x + d.r + w, y1: d.y - d.r } },
      { x: d.x + d.r, y: d.y + d.r + 12, anchor: "start", box: { x0: d.x + d.r - 1, y0: d.y + d.r, x1: d.x + d.r + w, y1: d.y + d.r + 15 } },
      { x: d.x - d.r, y: d.y - d.r - 3, anchor: "end", box: { x0: d.x - d.r - w, y0: d.y - d.r - 16, x1: d.x - d.r + 1, y1: d.y - d.r } },
      { x: d.x - d.r, y: d.y + d.r + 12, anchor: "end", box: { x0: d.x - d.r - w, y0: d.y + d.r, x1: d.x - d.r + 1, y1: d.y + d.r + 15 } },
    ];
    const fits = candidates.find(
      (c) =>
        c.box.x0 >= 2 &&
        c.box.y0 >= 2 &&
        c.box.x1 <= width - 2 &&
        c.box.y1 <= height - 2 &&
        !taken.some((t) => overlaps(t, c.box)) &&
        !dots.some((o) => o !== d && overlaps(dotBox(o), c.box)),
    );
    if (fits) {
      placed.set(d.slug, { x: fits.x, y: fits.y, anchor: fits.anchor });
      taken.push(fits.box);
    }
  }
  return placed;
}

/** Groups of dots lying within `distance` pixels of each other (single linkage), largest first. */
export function clusters<T extends LayoutDot>(dots: T[], distance: number): T[][] {
  const parent = dots.map((_, i) => i);
  const find = (i: number): number => (parent[i] === i ? i : (parent[i] = find(parent[i])));
  for (let i = 0; i < dots.length; i++)
    for (let j = i + 1; j < dots.length; j++)
      if (Math.hypot(dots[i].x - dots[j].x, dots[i].y - dots[j].y) <= distance) parent[find(i)] = find(j);
  const groups = new Map<number, T[]>();
  dots.forEach((d, i) => groups.set(find(i), [...(groups.get(find(i)) ?? []), d]));
  return [...groups.values()].sort((a, b) => b.length - a.length);
}
