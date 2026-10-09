"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { type SearchEntry, search } from "@/lib/search";

type Labels = {
  label: string;
  placeholder: string;
  seeAll: string;
  hint: string;
  types: Record<SearchEntry["type"], string>;
};

const indexes = new Map<string, Promise<SearchEntry[]>>();

/** The search index for a locale, fetched once per page load (on first focus). */
function loadIndex(locale: string): Promise<SearchEntry[]> {
  if (!indexes.has(locale)) {
    indexes.set(
      locale,
      fetch(`/${locale}/search-index.json`)
        .then((r) => (r.ok ? r.json() : []))
        .catch(() => []),
    );
  }
  return indexes.get(locale) as Promise<SearchEntry[]>;
}

/**
 * Header search: an ARIA combobox with instant results (arrow keys, Enter, Escape; "/" focuses
 * it from anywhere). Without JavaScript it is a plain form that opens the /search page.
 */
export function SearchBox({ locale, labels }: { locale: string; labels: Labels }) {
  const router = useRouter();
  const listId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [entries, setEntries] = useState<SearchEntry[] | null>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const results = useMemo(() => (entries ? search(entries, query, 8) : []), [entries, query]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
      if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const prepare = () => {
    if (!entries) loadIndex(locale).then(setEntries);
  };
  const go = (href: string) => {
    setOpen(false);
    setQuery("");
    input.current?.blur();
    router.push(href);
  };
  const showList = open && query.trim().length > 0 && entries !== null;
  const allHref = `/${locale}/search?q=${encodeURIComponent(query.trim())}`;

  return (
    <form
      role="search"
      action={`/${locale}/search`}
      method="get"
      className="relative w-full sm:w-64"
      onSubmit={(e) => {
        e.preventDefault();
        if (active >= 0 && results[active]) go(results[active].href);
        else if (query.trim()) go(allHref);
      }}
    >
      <label htmlFor={`${listId}-input`} className="sr-only">
        {labels.label}
      </label>
      <input
        ref={input}
        id={`${listId}-input`}
        name="q"
        type="search"
        autoComplete="off"
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showList && active >= 0 ? `${listId}-${active}` : undefined}
        aria-keyshortcuts="/"
        placeholder={labels.placeholder}
        title={labels.hint}
        value={query}
        className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-sm placeholder:text-muted focus:outline-2 focus:outline-accent"
        onFocus={() => {
          prepare();
          setOpen(true);
        }}
        onBlur={() => setOpen(false)}
        onChange={(e) => {
          prepare();
          setQuery(e.target.value);
          setActive(-1);
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setOpen(true);
            setActive((a) => Math.min(a + 1, results.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, -1));
          } else if (e.key === "Escape") {
            if (showList) setOpen(false);
            else setQuery("");
          }
        }}
      />
      {showList && (
        <ul
          id={listId}
          role="listbox"
          aria-label={labels.label}
          className="absolute right-0 z-20 mt-1 max-h-96 w-full min-w-72 overflow-auto rounded-md border border-border bg-surface py-1 text-sm shadow-lg"
        >
          {results.map((r, i) => (
            <li
              key={r.href}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              // mousedown, not click: the input's blur would close the list first.
              onMouseDown={(e) => {
                e.preventDefault();
                go(r.href);
              }}
              onMouseMove={() => setActive(i)}
              className={`flex cursor-pointer items-baseline justify-between gap-3 px-3 py-1.5 ${i === active ? "bg-accent-soft" : ""}`}
            >
              <span className="font-medium">{r.title}</span>
              <span className="shrink-0 text-xs text-muted">{r.subtitle ?? labels.types[r.type]}</span>
            </li>
          ))}
          <li
            role="option"
            aria-selected={false}
            onMouseDown={(e) => {
              e.preventDefault();
              go(allHref);
            }}
            className="cursor-pointer border-t border-border px-3 py-1.5 text-accent hover:underline"
          >
            {labels.seeAll}
          </li>
        </ul>
      )}
    </form>
  );
}
