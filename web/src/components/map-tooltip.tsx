"use client";

import { type ReactNode, useRef, useState } from "react";

/** Shows the `data-tip` of the hovered or focused map shape next to the pointer. */
export function MapTooltip({ children }: { children: ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null);

  const show = (el: Element | null, x: number, y: number) => {
    const text = el?.getAttribute("data-tip");
    const rect = box.current?.getBoundingClientRect();
    if (!text || !rect) return setTip(null);
    setTip({ text, x: x - rect.left, y: y - rect.top });
  };

  return (
    <div
      ref={box}
      className="relative"
      // Only the shape under the pointer: empty map space (the svg itself) shows nothing.
      onPointerMove={(e) => show((e.target as Element).closest("[data-tip]"), e.clientX, e.clientY)}
      onPointerLeave={() => setTip(null)}
      onFocus={(e) => {
        // A focused link holds its shape, which carries the tip.
        const target = e.target as Element;
        const shape = target.closest("[data-tip]") ?? (target.matches("a") ? target.querySelector("[data-tip]") : null);
        const r = target.getBoundingClientRect();
        show(shape, r.left + r.width / 2, r.top + r.height / 2);
      }}
      onBlur={() => setTip(null)}
    >
      {children}
      {tip && (
        <div
          role="status"
          className="pointer-events-none absolute z-10 max-w-56 -translate-x-1/2 -translate-y-full rounded-md border border-border bg-surface px-2 py-1 text-xs text-fg shadow-sm"
          style={{ left: tip.x, top: tip.y - 10 }}
        >
          {tip.text}
        </div>
      )}
    </div>
  );
}
