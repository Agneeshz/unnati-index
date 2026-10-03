"""Match the place names used by sources ("Orissa", "J&K", "A & N Islands") to our canonical
entities, taking boundary changes into account: the same name can mean different entities in
different periods (e.g. "Andhra Pradesh" before and after the 2014 split).

Unknown names are an error, never a guess — a wrong match would silently corrupt rankings."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from unnati.core.periods import Period

STATE_LEVEL = frozenset({"country", "state", "ut"})

# Aggregate rows that appear in state tables and must be dropped, not matched.
DEFAULT_SKIP_LABELS = frozenset(
    {
        "total states",
        "states total",
        "total state",
        "total uts",
        "uts total",
        "total ut",
        "total union territories",
        "union territories total",
    }
)

_NON_ALPHA = re.compile(r"[^a-z ]+")
_SPACES = re.compile(r"\s+")


def normalize_name(raw: str) -> str:
    """Lower-case, ASCII-fold, turn ``&`` into ``and``, drop punctuation, digits and footnote
    markers, and a leading "the"."""
    text = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    text = text.lower().replace("&", " and ")
    text = _NON_ALPHA.sub(" ", text)
    text = _SPACES.sub(" ", text).strip()
    return text.removeprefix("the ")


@dataclass(frozen=True)
class Entity:
    slug: str
    name: str
    type: str
    peer_group: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    id: int | None = None

    def valid_on(self, day: date) -> bool:
        return (self.valid_from is None or self.valid_from <= day) and (
            self.valid_to is None or day <= self.valid_to
        )


@dataclass(frozen=True)
class Alias:
    alias: str
    slug: str
    period_from: date | None = None
    period_to: date | None = None

    def applies_on(self, day: date) -> bool:
        return (self.period_from is None or self.period_from <= day) and (
            self.period_to is None or day <= self.period_to
        )


class UnknownEntityError(LookupError):
    pass


class AmbiguousEntityError(LookupError):
    pass


class EntityResolver:
    """Resolves source names to entities valid at the midpoint of the data period."""

    def __init__(
        self,
        entities: Iterable[Entity],
        aliases: Iterable[Alias] = (),
        skip_labels: Iterable[str] = DEFAULT_SKIP_LABELS,
    ) -> None:
        self._entities = {e.slug: e for e in entities}
        self._skip = {normalize_name(label) for label in skip_labels}
        self._index: dict[str, list[Alias]] = defaultdict(list)
        for entity in self._entities.values():
            for name in {entity.name, entity.slug.replace("-", " ")}:
                self._add(Alias(name, entity.slug))
        for alias in aliases:
            if alias.slug not in self._entities:
                raise ValueError(f"alias {alias.alias!r} points to unknown entity {alias.slug!r}")
            self._add(alias)

    def _add(self, alias: Alias) -> None:
        key = normalize_name(alias.alias)
        if alias not in self._index[key]:
            self._index[key].append(alias)

    @property
    def entities(self) -> dict[str, Entity]:
        return dict(self._entities)

    def resolve(self, raw_name: str, period: Period, *, types: frozenset[str] = STATE_LEVEL) -> Entity | None:
        """Return the matching entity, or ``None`` for aggregate rows such as "Total (States)".

        Raises :class:`UnknownEntityError` if nothing matches and
        :class:`AmbiguousEntityError` if more than one entity matches.
        """
        key = normalize_name(raw_name)
        if key in self._skip:
            return None
        day = period.midpoint
        named = self._index.get(key, [])
        matches = {
            self._entities[a.slug]
            for a in named
            if a.applies_on(day)
            and self._entities[a.slug].type in types
            and self._entities[a.slug].valid_on(day)
        }
        if len(matches) == 1:
            return matches.pop()
        if matches:
            slugs = ", ".join(sorted(e.slug for e in matches))
            raise AmbiguousEntityError(f"{raw_name!r} in {period.label} matches several: {slugs}")
        if named:
            slugs = ", ".join(sorted({a.slug for a in named}))
            raise UnknownEntityError(f"{raw_name!r} matches {slugs}, but none is valid for {period.label}")
        raise UnknownEntityError(f"unknown place name {raw_name!r} (normalised: {key!r})")
