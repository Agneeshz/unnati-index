from __future__ import annotations

from collections import Counter

import typer

from unnati.core.entities import AmbiguousEntityError, UnknownEntityError
from unnati.core.periods import parse_period
from unnati.reference import load_reference

app = typer.Typer(help="Unnati Index data pipeline.", no_args_is_help=True)


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
    database_url: str = typer.Option(None, envvar="DATABASE_URL", help="Postgres connection URL."),
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


@app.command()
def resolve(name: str, period: str = typer.Option("2024", help='e.g. "2024", "2023-24", "Jun 2026"')) -> None:
    """Show which entity a source's place name maps to for a given period."""
    try:
        entity = load_reference().resolver().resolve(name, parse_period(period))
    except (UnknownEntityError, AmbiguousEntityError) as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(1) from err
    typer.echo("skipped (aggregate row)" if entity is None else f"{entity.slug} ({entity.name})")
