# Unnati Index

**India's progress, state by state.** Unnati Index ranks and compares India's states and Union
Territories on the economy, jobs, trade, health, education, crime and safety, governance,
infrastructure, environment and inclusion. It refreshes itself from official sources on each
source's real release schedule and shows how fresh every number is.

> **Status:** early development. The foundations are in place: database schema, reference data,
> the site skeleton and CI. Data connectors come next. See the [roadmap](#roadmap).

## What it will do

- **Rankings that are fair.** Every ranked indicator is a rate, share or per-person value, never a
  raw total. States are ranked within peer groups (large states, North-East & Himalayan states,
  UTs) as well as overall.
- **Progress, not just position.** Scores use fixed goalposts, so a state's score rises only when
  its own numbers improve. Every leaderboard has a "most improved" view.
- **Fresh, and honest about it.** Each figure shows the period it covers, when it was fetched and
  when the next official release is due. Only genuinely live feeds (such as air quality) are
  called live.
- **Accountability without partisanship.** Each state shows its office-holders (Governor, Chief
  Minister, relevant ministers, Chief Secretary, DGP and department secretaries), always matched
  to the period a number describes rather than to whoever holds office today.
- **Open.** Methodology, code and derived data are public.

## How it works

```
Official sources ──► Python pipeline (scheduled) ──► Postgres ──► Next.js website
 (APIs, Excel, PDF)   fetch → archive → parse →       (every       (cached pages,
                      match places → validate →        revision     refreshed when
                      load → score → refresh site      kept)        data changes)
```

| Folder | What's inside |
|---|---|
| [`pipeline/`](pipeline) | Python 3.12 (uv): connectors, entity matching, validation, scoring, CLI `unnati` |
| [`web/`](web) | Next.js 16 site (App Router, Cache Components, Tailwind), English with Hindi built in |
| [`db/migrations/`](db/migrations) | Postgres schema as plain SQL (dbmate) |
| [`geo/`](geo) | Builds the official-boundary state map used by the site |
| [`docs/`](docs) | Methodology and contributor guides |

## Development

Prerequisites: Node.js 22+ (24 recommended), Python 3.12 and [uv](https://docs.astral.sh/uv/).
No Postgres install or Docker is needed locally: tests run on
[PGlite](https://pglite.dev) (Postgres compiled to WebAssembly).

```bash
npm install                 # repo tooling: PGlite, dbmate, mapshaper
npm run db:check            # migrations apply, roll back and re-apply

cd pipeline
uv sync
uv run unnati check         # validate reference data (entities, taxonomy, registry)
uv run pytest               # unit + database tests

cd ../web
npm install
npm run dev                 # http://localhost:3000
npm test && npm run lint && npm run typecheck
```

To try the pipeline against a local database:

```bash
npm run db:local            # PGlite server on 127.0.0.1:5432 (keep it running)
npm run db:migrate:local    # in another terminal
cd pipeline && uv run unnati seed --database-url "postgresql://postgres:postgres@127.0.0.1:5432/postgres?sslmode=disable"
```

The hosted database is [Neon](https://neon.com). Maintainers link it with the
[Neon CLI](https://www.npmjs.com/package/neon), which writes the connection variables to the
git-ignored `.env.local`:

```bash
neon link --project-id <project-id> --branch production -y
npm run db:migrate          # direct (unpooled) connection from .env.local
cd pipeline && uv run --env-file ../.env.local unnati seed
```

## Roadmap

1. **Foundations** (done): schema, 36 states/UTs with boundary history, taxonomy of 16
   categories and 8 pillars, dataset registry, site skeleton, map, CI.
2. **Pipeline + anchor data**: connectors for RBI, MoSPI, NCRB, SRS, NFHS-6, UDISE+, GST,
   DGCI&S trade, live air quality, power, PhonePe Pulse, and office-holders.
3. **Scoring + website**: rankings, state report cards, indicator pages, compare, map.
4. **All categories, then public launch.**
5. **Cities**, then **districts**, Hindi, and a public API.

## Data, licences and corrections

Code is [MIT](LICENSE). Derived data is [CC BY 4.0](DATA_LICENSE.md); source data stays under
its publisher's terms, listed per dataset. Found a wrong number or office-holder?
[Open an issue](https://github.com/Agneeshz/unnati-index/issues) with a link to the official source.

Unnati Index is independent and non-partisan.
