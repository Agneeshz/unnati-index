# Unnati Index — notes for coding agents

Public website ranking Indian states/UTs (later cities, districts) on official data, refreshed
automatically. Monorepo: `pipeline/` (Python), `web/` (Next.js), `db/migrations/` (SQL), `geo/`.

## Commands

- Repo root: `npm install`, `npm run db:check` (migrations up/down/up on PGlite),
  `npm run db:local` + `npm run db:migrate:local` (PGlite server :5432), `npm run geo:build`.
- Neon (hosted DB) runs in aws-ap-southeast-1 (Singapore, nearest to India); deploy Vercel
  functions to `sin1` when the site reads the DB. The repo is linked with `neon link` (`.neon`, git-ignored); connection vars
  are in `.env.local`. `npm run db:migrate` uses `DATABASE_URL_UNPOOLED`; the pipeline prefers it
  too (`uv run --env-file ../.env.local unnati seed`). `neon.ts` is the Neon config-as-code
  policy (Postgres only, `neon deploy`). Neon agent skill: `neon skills -s neon --agent claude-code -y`
  (git-ignored); `.mcp.json` adds the Neon MCP server via OAuth.
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
- Office-holders: `uv run unnati officials sync [--dry-run]` imports from Wikidata, applies
  `manual/officials_overrides.yaml` (fixes to Wikidata terms) and `manual/officials.yaml`
  (sourced terms Wikidata lacks), then cross-checks current holders against Wikipedia's incumbent
  tables by Wikidata ID. Every curated entry needs an official source URL; check person QIDs
  aren't disambiguation pages. Never publish a party that the sources don't agree on.
- Per-capita denominators come from `reference/population.csv` (MoHFW 1 July projections, the
  ones NCRB uses), rebuilt with `uv run unnati population build`. Connectors with large
  downloads register a cheap metadata probe in `ingest.PROBES` so unchanged runs skip the fetch.
- NCRB/MoRTH files are read from OpenCity's CKAN mirror (`data.opencity.in`); ncrb.gov.in lists
  files via JavaScript. Check that mirrored files are what their names say (2024 "Vol 3" is Vol 2).
- Never commit secrets; configuration comes from env vars (see `.env.example`).
