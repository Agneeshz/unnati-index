from __future__ import annotations

from collections import Counter
from datetime import date

import typer

from unnati.core.entities import AmbiguousEntityError, UnknownEntityError
from unnati.core.periods import parse_period
from unnati.reference import load_reference

app = typer.Typer(help="Unnati Index data pipeline.", no_args_is_help=True)
officials_app = typer.Typer(help="Office-holders: politicians and bureaucrats.", no_args_is_help=True)
app.add_typer(officials_app, name="officials")
manual_app = typer.Typer(help="Sources that need a manual download.", no_args_is_help=True)
app.add_typer(manual_app, name="manual")
population_app = typer.Typer(help="Population denominators.", no_args_is_help=True)
app.add_typer(population_app, name="population")


@app.command()
def check() -> None:
    """Validate the reference data (entities, aliases, taxonomy, registry)."""
    ref = load_reference()
    current = [e for e in ref.entities if e.type in ("state", "ut") and e.valid_to is None]
    groups = Counter(e.peer_group for e in current)
    composite = Counter(i.pillar for i in ref.indicators if i.pillar)
    typer.echo(f"entities: {len(current)} current states/UTs; peer groups {dict(groups)}")
    typer.echo(f"aliases: {len(ref.aliases)}; lineage events: {len(ref.lineage)}")
    typer.echo(f"categories: {len(ref.categories)}; pillars: {len(ref.pillars)}")
    typer.echo(
        f"indicators: {len(ref.indicators)} ({sum(composite.values())} in the composite: {dict(composite)})"
    )
    sources, datasets = ref.registry.sources, ref.registry.datasets
    enabled = sum(d.enabled for d in datasets)
    typer.echo(f"registry: {len(sources)} sources, {len(datasets)} datasets ({enabled} enabled)")


@app.command()
def seed(
    database_url: str = typer.Option(
        None, help="Postgres URL. Defaults to $DATABASE_URL_UNPOOLED, then $DATABASE_URL."
    ),
) -> None:
    """Upsert the reference data into the database."""
    from unnati.db import connect
    from unnati.seed import seed as run_seed

    conn = connect(database_url)
    try:
        counts = run_seed(conn, load_reference())
    finally:
        conn.close()
    typer.echo("seeded " + ", ".join(f"{n} {k}" for k, n in counts.items()))


@officials_app.command("sync")
def officials_sync(
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch and check, but don't write."),
    force: bool = typer.Option(False, help="Load even if unchanged or much smaller than before."),
    database_url: str = typer.Option(
        None, help="Postgres URL. Defaults to $DATABASE_URL_UNPOOLED, then $DATABASE_URL."
    ),
) -> None:
    """Import Chief Ministers, Governors, Lieutenant Governors and Administrators from Wikidata."""
    from unnati.connectors.wikidata_officials import PARTY_OFFICES
    from unnati.core.http import PoliteClient
    from unnati.sync_officials import build, load

    today = date.today()
    with PoliteClient() as http:
        report = build(http, today)
    if not dry_run:
        from unnati.db import connect

        conn = connect(database_url)
        try:
            load(conn, report, today, force=force)
        finally:
            conn.close()

    by_type = Counter(t.office_type for t in report.terms)
    covered = {t: len({x.entity_slug for x in report.terms if x.office_type == t}) for t in by_type}
    typer.echo(f"status: {report.status}")
    typer.echo(f"terms: {len(report.terms)} since 2000 ({dict(by_type)})")
    typer.echo(f"entities covered per office type: {covered}")
    if report.counts:
        typer.echo("loaded: " + ", ".join(f"{n} {k}" for k, n in report.counts.items()))
    typer.echo(f"held for review: {len(report.flagged)}")
    for t in sorted(report.flagged, key=lambda t: (t.entity_slug, t.office_type, t.start)):
        end = t.end or "now"
        typer.echo(f"  - {t.entity_slug} | {t.title} | {t.person_name} ({t.start} to {end})")
        typer.echo(f"    id: {t.external_id}")
        for note in t.conflicts + t.notes:
            typer.echo(f"    * {note}")
    confirmed = [t for t in report.terms if any(a.startswith("confirmed current") for a in t.advisories)]
    typer.echo(f"current office-holders confirmed by the Wikipedia cross-check: {len(confirmed)}")
    blank_party = [
        t
        for t in report.terms
        if t.party_qid is None and t.office_type in PARTY_OFFICES and not t.needs_review
    ]
    typer.echo(f"shown with party left blank (sources unclear): {len(blank_party)}")
    for t in sorted(blank_party, key=lambda t: (t.entity_slug, t.start)):
        reasons = [a for a in t.advisories if "part" in a] or ["no party recorded"]
        typer.echo(f"  - {t.entity_slug} | {t.person_name} ({t.start}): {'; '.join(reasons)}")
    for problem in report.problems:
        typer.echo(f"problem: {problem}")
    for key in report.unused_overrides:
        typer.echo(f"warning: override {key!r} matched no term")


@officials_app.command("observe")
def officials_observe(
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch and parse, but don't write."),
    database_url: str = typer.Option(
        None, help="Postgres URL. Defaults to $DATABASE_URL_UNPOOLED, then $DATABASE_URL."
    ),
) -> None:
    """Record current Chief Secretaries and police chiefs (tenure is observed, not invented)."""
    from unnati.connectors import wikipedia_bureaucrats as wb
    from unnati.core.http import PoliteClient
    from unnati.core.periods import day

    today = date.today()
    ref = load_reference()
    resolver = ref.resolver()
    with PoliteClient() as http:
        listed = wb.fetch(http)
    rows, problems = [], []
    for item in listed:
        try:
            entity = resolver.resolve(item.place, day(today))
        except (UnknownEntityError, AmbiguousEntityError) as err:
            problems.append(str(err))
            continue
        if entity is None:
            continue
        flags = [
            f for f, on in (("acting", item.acting), ("additional charge", item.additional_charge)) if on
        ]
        note = "; ".join([*flags, f"per Wikipedia's current list ({item.page_url})"])
        rows.append((entity.slug, item.office_type, item.name, item.citation or item.page_url, note))
    by_type = Counter(r[1] for r in rows)
    typer.echo(f"listed: {len(rows)} ({dict(by_type)})")
    for problem in problems:
        typer.echo(f"problem: {problem}")
    if dry_run:
        return

    from unnati.db import connect
    from unnati.officials import load_observed_terms
    from unnati.runs import finish_run, start_run

    conn = connect(database_url)
    try:
        run_id = start_run(conn, "wikipedia_bureaucrats")
        try:
            names = {e.slug: e.name for e in ref.entities}
            ranked = [c.id for c in ref.categories if c.ranked]
            counts = load_observed_terms(conn, rows, names, ranked, today)
        except Exception as err:
            finish_run(conn, run_id, "failed", error=str(err))
            raise
        finish_run(conn, run_id, "loaded", rows_loaded=len(rows), validation={"problems": problems})
    finally:
        conn.close()
    typer.echo("terms: " + ", ".join(f"{n} {k}" for k, n in counts.items()))


@manual_app.command("rbi-links")
def manual_rbi_links() -> None:
    """Print the RBI handbook files to download, and which are already in the repo."""
    from unnati.connectors import rbi_hsis
    from unnati.core.http import PoliteClient

    with PoliteClient() as http:
        edition, listed = rbi_hsis.index(http)
    have = rbi_hsis.local_files(edition)
    folder = rbi_hsis.MANUAL_DIR / edition
    typer.echo(f"Edition {edition}. Save into: {folder}")
    by_number = {t.number: t for t in listed}
    missing = 0
    for number, expected in rbi_hsis.TABLES.items():
        table = by_number.get(number)
        if table is None or expected.lower() not in table.title.lower():
            typer.echo(f"  table {number}: '{expected}' not found at this number; check the index page")
            continue
        status = "have" if number in have else "GET "
        missing += number not in have
        typer.echo(f"  [{status}] {table.title}\n         {table.url}")
    typer.echo(f"{missing} file(s) to download.")


@population_app.command("build")
def population_build(
    pdf: str = typer.Option(None, help="A local copy of the report; downloaded when omitted."),
) -> None:
    """Rebuild reference/population.csv from the MoHFW Technical Group report."""
    import csv
    from pathlib import Path

    from unnati.connectors import population_projections as pp

    if pdf:
        raw = Path(pdf).read_bytes()
    else:
        from unnati.core.http import PoliteClient

        with PoliteClient(timeout=300) as http:
            raw = http.get(pp.REPORT_URL).content
    rows = pp.rows(pp.parse(raw), load_reference().entities)
    out = Path(__file__).parent / "reference" / "population.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    typer.echo(f"wrote {len(rows)} rows to {out}")


@app.command()
def ingest(
    dataset: str = typer.Argument(..., help="Dataset id from the registry, e.g. mospi_nas_state."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch and validate, but don't write."),
    force: bool = typer.Option(False, help="Load even if the source is unchanged."),
    trigger: str = typer.Option("manual", help="Recorded with the run: manual, schedule or backfill."),
    database_url: str = typer.Option(
        None, help="Postgres URL. Defaults to $DATABASE_URL_UNPOOLED, then $DATABASE_URL."
    ),
) -> None:
    """Fetch a dataset, validate it and load new or revised values."""
    from unnati import ingest as ingest_module

    today = date.today()
    if dry_run:
        report = ingest_module.check(dataset, today)
    else:
        from unnati.db import connect

        conn = connect(database_url)
        try:
            report = ingest_module.run(conn, dataset, today, trigger=trigger, force=force)
        finally:
            conn.close()

    per_indicator = Counter(o.indicator_id for o in report.fetched.observations)
    typer.echo(f"status: {report.status}")
    typer.echo(f"observations: {len(report.fetched.observations)} {dict(per_indicator)}")
    if report.counts:
        typer.echo("loaded: " + ", ".join(f"{n} {k}" for k, n in report.counts.items()))
    for line in report.validation.hard:
        typer.echo(f"REJECTED: {line}")
    for line in report.validation.soft:
        typer.echo(f"note: {line}")
    for line in report.fetched.problems:
        typer.echo(f"problem: {line}")
    if report.status == "rejected":
        raise typer.Exit(1)


@app.command()
def score(
    dry_run: bool = typer.Option(False, "--dry-run", help="Compute and print, but don't write."),
    database_url: str = typer.Option(
        None, help="Postgres URL. Defaults to $DATABASE_URL_UNPOOLED, then $DATABASE_URL."
    ),
) -> None:
    """Compute the Unnati Index (all editions) from the latest observations."""
    from unnati import score_store, scoring
    from unnati.db import connect

    today = date.today()
    conn = connect(database_url)
    try:
        if dry_run:
            spec = score_store.specs()
            values = score_store.load_values(conn, list(spec))
            posts = scoring.goalposts(values, spec)
            editions = score_store.compute(values, spec, posts, today)
        else:
            editions = score_store.run(conn, today)
    finally:
        conn.close()
    latest = editions[max(editions)]
    composite = sorted(
        (s for s in latest if s.key == scoring.COMPOSITE_KEY and s.score is not None and s.rank_overall),
        key=lambda s: s.rank_overall,
    )
    typer.echo(f"edition {max(editions)}: {len(composite)} places with an Unnati Index score")
    for s in composite:
        typer.echo(f"  {s.rank_overall:>2}. {s.entity:<42} {s.score:5.1f}  (peer #{s.rank_peer})")
    missing = [s.entity for s in latest if s.key == scoring.COMPOSITE_KEY and s.score is None]
    if missing:
        typer.echo("no score (too few pillars): " + ", ".join(sorted(missing)))


_REVALIDATE_TAGS = typer.Argument(None, help="Cache tags; default: everything data-driven.")


@app.command()
def revalidate(tags: list[str] = _REVALIDATE_TAGS) -> None:
    """Ask the website to refresh cached pages (POST $SITE_URL/api/revalidate)."""
    import os

    from unnati.core.http import PoliteClient

    site, secret = os.environ.get("SITE_URL"), os.environ.get("REVALIDATE_SECRET")
    if not site or not secret:
        typer.echo("SITE_URL and REVALIDATE_SECRET must be set", err=True)
        raise typer.Exit(1)
    body = {"tags": tags or ["scores", "observations", "officials", "places"]}
    with PoliteClient(timeout=30) as http:
        response = http.post(
            f"{site.rstrip('/')}/api/revalidate", json=body, headers={"Authorization": f"Bearer {secret}"}
        )
    typer.echo(f"revalidated: {', '.join(response.json()['revalidated'])}")


@app.command()
def resolve(name: str, period: str = typer.Option("2024", help='e.g. "2024", "2023-24", "Jun 2026"')) -> None:
    """Show which entity a source's place name maps to for a given period."""
    try:
        entity = load_reference().resolver().resolve(name, parse_period(period))
    except (UnknownEntityError, AmbiguousEntityError) as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(1) from err
    typer.echo("skipped (aggregate row)" if entity is None else f"{entity.slug} ({entity.name})")
