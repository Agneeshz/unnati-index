# Unnati Index — website

Next.js 16 (App Router, Cache Components, Turbopack) with Tailwind CSS 4.

- `src/app/[locale]/`: all pages, under a `[locale]` root layout (`en`, `hi`). The locale is read
  anywhere on the server with `next/root-params`; UI strings live in `src/i18n/dictionaries/`.
- `src/proxy.ts`: sends un-prefixed URLs to the visitor's language. Hindi is opt-in until its
  translation is complete (`launchedLocales` in `src/i18n/config.ts`).
- `src/app/api/revalidate/route.ts`: the data pipeline calls this with
  `Authorization: Bearer $REVALIDATE_SECRET` and `{"tags": [...]}` after loading new data.
- `public/geo/india-states.topo.json`: official-boundary state map, built by `npm run geo:build`
  at the repo root (see `geo/README.md`).

```bash
npm install
npm run dev          # http://localhost:3000
npm test             # vitest
npm run lint && npm run typecheck && npm run build
```

Before changing framework code, read the bundled docs in `node_modules/next/dist/docs/`
(this Next.js version differs from older ones).
