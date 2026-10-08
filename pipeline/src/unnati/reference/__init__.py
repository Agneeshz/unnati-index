"""Reference data shipped with the pipeline: entities, aliases, lineage, the taxonomy and the
dataset registry. Everything is validated on load so a typo fails fast, before it reaches the
database."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from functools import cache
from importlib.resources import files
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from unnati.core.entities import Alias, Entity, EntityResolver

_REFERENCE = files(__package__)
_REGISTRY = files("unnati").joinpath("registry.yaml")

Direction = Literal["higher_better", "lower_better", "neutral"]
Cadence = Literal["hourly", "daily", "weekly", "monthly", "quarterly", "annual", "biennial", "irregular"]
PeerGroup = Literal["large_state", "ne_himalayan_state", "ut", "city_million_plus", "city_other"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EntityRow(_Model):
    slug: str
    name: str
    name_hi: str | None = None
    type: Literal["country", "state", "ut", "city", "district"]
    lgd_code: int | None = None
    census2011_code: str | None = None
    parent_slug: str | None = None
    peer_group: PeerGroup | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    wikidata_qid: str | None = Field(default=None, pattern=r"^Q\d+$")
    latitude: float | None = None
    longitude: float | None = None
    population_2011: int | None = None

    def to_entity(self) -> Entity:
        return Entity(
            slug=self.slug,
            name=self.name,
            type=self.type,
            peer_group=self.peer_group,
            valid_from=self.valid_from,
            valid_to=self.valid_to,
        )


class LineageRow(_Model):
    predecessor_slug: str
    successor_slug: str
    event_date: date
    kind: Literal["split", "merge", "reorganisation", "rename"]
    note: str | None = None


class AliasRow(_Model):
    alias: str
    entity_slug: str
    period_from: date | None = None
    period_to: date | None = None


class Category(_Model):
    id: str
    name: str
    name_hi: str | None = None
    description: str
    ranked: bool = True


class Pillar(_Model):
    id: str
    name: str
    name_hi: str | None = None
    description: str


class Indicator(_Model):
    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    name: str
    name_hi: str | None = None
    description: str
    unit: str
    direction: Direction
    category: str
    pillar: str | None = None
    dataset: str
    frequency: str
    decimals: int = 1
    rankable: bool = True
    derived: str | None = None
    caveat: str | None = None
    target: float | None = None
    scale: Literal["linear", "log"] = "linear"
    valid_min: float | None = None
    valid_max: float | None = None

    @model_validator(mode="after")
    def _check(self) -> Indicator:
        if self.pillar and (self.direction == "neutral" or not self.rankable):
            raise ValueError(f"{self.id}: composite indicators must be rankable with a direction")
        if self.valid_min is not None and self.valid_max is not None and self.valid_min >= self.valid_max:
            raise ValueError(f"{self.id}: valid_min must be below valid_max")
        return self


class ThematicIndex(_Model):
    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    name: str
    name_hi: str | None = None
    inspired_by: str | None = None
    description: str
    method: str
    caveat: str | None = None
    kind: Literal["mean", "hdi"]
    components: dict[str, list[str]]

    def indicator_ids(self) -> list[str]:
        return [i for members in self.components.values() for i in members]


class HindiText(_Model):
    name: str
    description: str
    caveat: str | None = None


class HindiIndex(_Model):
    name: str
    description: str
    inspired_by: str | None = None
    method: str
    caveat: str | None = None
    dimensions: dict[str, str]


class Hindi(_Model):
    """reference/hi.yaml: Hindi text for indicators, units and thematic indices."""

    units: dict[str, str] = {}
    indicators: dict[str, HindiText] = {}
    indices: dict[str, HindiIndex] = {}


class Source(_Model):
    id: str
    name: str
    publisher: str
    url: str
    license: str
    attribution: str


class Dataset(_Model):
    id: str
    source: str
    title: str
    connector: str
    cadence: Cadence
    landing_url: str | None = None
    enabled: bool = False


class Registry(_Model):
    sources: list[Source]
    datasets: list[Dataset]


def _csv_rows(name: str) -> list[dict[str, str | None]]:
    with _REFERENCE.joinpath(name).open(encoding="utf-8", newline="") as fh:
        return [{k: (v if v != "" else None) for k, v in row.items()} for row in csv.DictReader(fh)]


def _yaml(resource) -> object:
    with resource.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class ReferenceData(_Model):
    entities: list[EntityRow]
    lineage: list[LineageRow]
    aliases: list[AliasRow]
    categories: list[Category]
    pillars: list[Pillar]
    indicators: list[Indicator]
    indices: list[ThematicIndex] = []
    registry: Registry
    hindi: Hindi = Hindi()

    @model_validator(mode="after")
    def _cross_check(self) -> ReferenceData:
        problems: list[str] = []

        def unique(kind: str, ids: list[str]) -> set[str]:
            seen: set[str] = set()
            for i in ids:
                if i in seen:
                    problems.append(f"duplicate {kind} id {i!r}")
                seen.add(i)
            return seen

        slugs = unique("entity", [e.slug for e in self.entities])
        categories = unique("category", [c.id for c in self.categories])
        pillars = unique("pillar", [p.id for p in self.pillars])
        sources = unique("source", [s.id for s in self.registry.sources])
        datasets = unique("dataset", [d.id for d in self.registry.datasets])
        indicator_ids = unique("indicator", [i.id for i in self.indicators])
        unique("index", [x.id for x in self.indices])
        directions = {i.id: i.direction for i in self.indicators}
        for x in self.indices:
            for member in x.indicator_ids():
                if member not in indicator_ids:
                    problems.append(f"index {x.id}: unknown indicator {member!r}")
                elif directions[member] == "neutral":
                    problems.append(f"index {x.id}: {member} has no direction")

        for e in self.entities:
            if e.parent_slug and e.parent_slug not in slugs:
                problems.append(f"entity {e.slug}: unknown parent {e.parent_slug!r}")
        for row in self.lineage:
            for slug in (row.predecessor_slug, row.successor_slug):
                if slug not in slugs:
                    problems.append(f"lineage: unknown entity {slug!r}")
        for a in self.aliases:
            if a.entity_slug not in slugs:
                problems.append(f"alias {a.alias!r}: unknown entity {a.entity_slug!r}")
        for d in self.registry.datasets:
            if d.source not in sources:
                problems.append(f"dataset {d.id}: unknown source {d.source!r}")
        for i in self.indicators:
            if i.category not in categories:
                problems.append(f"indicator {i.id}: unknown category {i.category!r}")
            if i.pillar and i.pillar not in pillars:
                problems.append(f"indicator {i.id}: unknown pillar {i.pillar!r}")
            if i.dataset not in datasets:
                problems.append(f"indicator {i.id}: unknown dataset {i.dataset!r}")
        if problems:
            raise ValueError("reference data problems:\n  " + "\n  ".join(problems))
        return self

    def resolver(self) -> EntityResolver:
        return EntityResolver(
            (e.to_entity() for e in self.entities),
            (Alias(a.alias, a.entity_slug, a.period_from, a.period_to) for a in self.aliases),
        )


@dataclass(frozen=True)
class Population:
    persons: int
    male: int
    female: int


@cache
def population() -> dict[tuple[str, int], Population]:
    """Projected population as on 1 July of each year, 2011-2036 (MoHFW Technical Group, July
    2020), keyed by (entity slug, year). Built from the report by `unnati population build`."""
    return {
        (row["entity_slug"], int(row["year"])): Population(
            int(row["persons_000"]) * 1000, int(row["male_000"]) * 1000, int(row["female_000"]) * 1000
        )
        for row in _csv_rows("population.csv")
    }


@cache
def city_names(source: Literal["ncrb", "cpcb"]) -> dict[str, str]:
    """Normalised name a source uses for a city -> the city's slug (reference/cities.csv)."""
    from unnati.core.entities import normalize_name

    return {
        normalize_name(row[f"{source}_name"]): row["slug"]
        for row in _csv_rows("cities.csv")
        if row[f"{source}_name"]
    }


@cache
def city_lookup() -> dict[tuple[str, str], str]:
    """(state slug, normalised name) -> city slug, for sources that name cities their own way:
    the roster name, its CPCB and NCRB names, each half of a twin city ("Kalyan-Dombivli") and
    the city's former name (Gurgaon, Mysore, Aurangabad...)."""
    import re

    from unnati.connectors.cities import ALT_NAMES, RENAMES
    from unnati.core.entities import normalize_name

    former = {new: old for old, new in RENAMES.items()}
    out: dict[tuple[str, str], str] = {}
    for row in _csv_rows("cities.csv"):
        names = [row["name"], row["cpcb_name"], row["ncrb_name"], former.get(row["name"])]
        names += re.split(r"\s*[-–&]\s*", row["name"])
        names += ALT_NAMES.get(row["slug"], [])
        for name in filter(None, names):
            out.setdefault((row["state_slug"], normalize_name(re.sub(r"\s*\(.*\)$", "", name))), row["slug"])
    return out


@cache
def state_area() -> dict[str, float]:
    """Geographical area in km² by entity slug: the sum of the land-cover classes in MoSPI's
    EnviStats (table 12, 2015-16), which matches the Census 2011 areas. Jammu & Kashmir and
    Ladakh are left out: their only official area (222,237 km² for the former state) includes
    territory India claims but does not administer, so a density over it would mislead."""
    return {row["slug"]: float(row["area_km2"]) for row in _csv_rows("state_area.csv")}


@cache
def load_reference() -> ReferenceData:
    return ReferenceData(
        entities=_csv_rows("entities.csv") + _city_entities(),
        lineage=_csv_rows("lineage.csv"),
        aliases=_csv_rows("aliases.csv"),
        categories=_yaml(_REFERENCE.joinpath("categories.yaml")),
        pillars=_yaml(_REFERENCE.joinpath("pillars.yaml")),
        indicators=_yaml(_REFERENCE.joinpath("indicators.yaml")),
        indices=_yaml(_REFERENCE.joinpath("indices.yaml")),
        registry=_yaml(_REGISTRY),
        hindi=_hindi(),
    )


def _city_entities() -> list[dict]:
    """Entity rows for the city roster (reference/cities.csv, built by `unnati cities build`)."""
    from unnati.connectors.cities import MILLION_PLUS

    state_qids = {row["slug"]: row["wikidata_qid"] for row in _csv_rows("entities.csv")}
    out = []
    for row in _csv_rows("cities.csv"):
        population = int(row["population_2011"]) if row["population_2011"] else None
        qid = row["wikidata_qid"]
        out.append(
            {
                "slug": row["slug"],
                "name": row["name"],
                "name_hi": row["name_hi"],
                "type": "city",
                "parent_slug": row["state_slug"],
                "peer_group": "city_million_plus" if (population or 0) >= MILLION_PLUS else "city_other",
                # Delhi and Chandigarh share their Wikidata item with the state/UT of the same name.
                "wikidata_qid": None if qid == state_qids.get(row["state_slug"]) else qid,
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "population_2011": population,
            }
        )
    return out


def _hindi() -> dict:
    data = dict(_yaml(_REFERENCE.joinpath("hi.yaml")))
    data.pop("_caveats", None)  # YAML anchors for shared caveats, already expanded
    return data
