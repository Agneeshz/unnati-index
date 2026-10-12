/** Suspense fallback. Fills the screen so the footer starts below the fold and doesn't jump
 *  when the content streams in (layout shift). */
export function Loading({ wide = false }: { wide?: boolean }) {
  return (
    <div role="status" className={`min-h-screen text-muted ${wide ? "mx-auto max-w-5xl px-4 py-12" : ""}`}>
      …
    </div>
  );
}
