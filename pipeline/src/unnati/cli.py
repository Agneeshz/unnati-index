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
        for note in t.notes:
            typer.echo(f"    * {note}")
    blank_party = [t for t in report.terms if t.advisories and not t.needs_review]
    typer.echo(f"shown with party left blank (sources unclear): {len(blank_party)}")
    for t in sorted(blank_party, key=lambda t: (t.entity_slug, t.start)):
        typer.echo(f"  - {t.entity_slug} | {t.person_name} ({t.start}): {'; '.join(t.advisories)}")
    for problem in report.problems:
        typer.echo(f"problem: {problem}")
    for key in report.unused_overrides:
        typer.echo(f"warning: override {key!r} matched no term")


@app.command()
def resolve(name: str, period: str = typer.Option("2024", help='e.g. "2024", "2023-24", "Jun 2026"')) -> None:
    """Show which entity a source's place name maps to for a given period."""
    try:
        entity = load_reference().resolver().resolve(name, parse_period(period))
    except (UnknownEntityError, AmbiguousEntityError) as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(1) from err
    typer.echo("skipped (aggregate row)" if entity is None else f"{entity.slug} ({entity.name})")
