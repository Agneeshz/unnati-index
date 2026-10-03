# Unnati Index — notes for coding agents

Public website ranking Indian states/UTs (later cities, districts) on official data, refreshed
automatically. Monorepo: `pipeline/` (Python), `web/` (Next.js), `db/migrations/` (SQL), `geo/`.

## Commands

- Repo root: `npm install`, `npm run db:check` (migrations up/down/up on PGlite),
  `npm run db:local` (PGlite server :5432), `npm run db:migrate`, `npm run geo:build`.
- `pipeline/`: `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`,
  `uv run unnati check|seed|resolve "<name>" --period 2023-24`.
- `web/`: `npm run dev|build|lint|typecheck|test`.

## Conventions

- **Postgres driver is pg8000 (pure Python), not psycopg.** The maintainer's Windows machine
  blocks psycopg-binary's unsigned DLLs (Application Control). Use `pg8000.native` with named
  `:params`; `unnati.db.connect/transaction/scalar` wrap it.
- **Next.js 16.3 with `cacheComponents`.** Read `web/node_modules/next/dist/docs/` before writing
  web code. Locale comes from `next/root-params` (`[locale]` root layout); `proxy.ts`, not
  middleware; `revalidateTag(tag, "max")`.
- Schema changes go in a new `db/migrations/<timestamp>_<name>.sql` with `-- migrate:up` and
  `-- migrate:down`; `npm run db:check` must pass.
- Reference data (`pipeline/src/unnati/reference/`, `pipeline/src/unnati/registry.yaml`) is
  validated on load; keep `uv run unnati check` and `test_reference.py` green.
- Place names from sources go through `EntityResolver`: unknown names are errors, never guesses.
  Add aliases to `aliases.csv`.
- Ranked indicators must be rates/shares/per-person values. Office-holders are always tied to the
  data period. Never add party-vs-party rankings.
- Source URLs in the registry must be verified before a connector is enabled.
- Never commit secrets; configuration comes from env vars (see `.env.example`).
