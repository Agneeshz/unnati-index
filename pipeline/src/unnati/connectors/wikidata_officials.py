"""Office-holders from Wikidata: Chief Ministers and the heads of states and UTs (Governors,
Lieutenant Governors, Administrators).

* Positions come from an explicit, reviewed map (``reference/wikidata_positions.csv``), not class
  discovery: Wikidata models UT heads inconsistently, and a wrong match would attach people to
  the wrong state.
* Terms are clipped to each entity's validity, so a Chief Minister of undivided Andhra Pradesh
  is never attached to today's state, and vice versa.
* Wikidata contains mistakes and lags behind events. A term that fails the automatic checks is
  loaded with ``needs_review`` set (the site hides it) until a maintainer settles it in
  ``manual/officials_overrides.yaml`` with a source link.
* Party is recorded only for elected heads of government, never for constitutional posts.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from importlib.resources import files
from itertools import pairwise

import yaml

from unnati.core.entities import Entity
from unnati.core.http import PoliteClient
from unnati.core.wikidata import qid, sparql, to_date, values_clause

DATASET_ID = "wikidata_officials"
EARLIEST_RELEVANT = date(2000, 1, 1)
# An assembly's term is five years; an incumbent older than this is probably out of date.
STALE_AFTER = timedelta(days=round(365.25 * 5.5))
OVERLAP_TOLERANCE = timedelta(days=2)
PARTY_OFFICES = frozenset({"chief_minister", "deputy_chief_minister"})
HEAD_OF_GOVERNMENT = frozenset({"chief_minister"})
# In these UTs police and public order rest with the Lieutenant Governor, not the elected government.
POLICE_UNDER_LIEUTENANT_GOVERNOR = frozenset({"delhi", "jammu-and-kashmir"})

TERMS_QUERY = """
SELECT ?statement ?position ?person ?personLabel ?nameHi ?start ?end ?group ?groupLabel WHERE {{
  VALUES ?position {{ {positions} }}
  ?person p:P39 ?statement .
  ?statement ps:P39 ?position ;
             wikibase:rank ?rank .
  FILTER(?rank != wikibase:DeprecatedRank)
  OPTIONAL {{ ?statement pq:P580 ?start }}
  OPTIONAL {{ ?statement pq:P582 ?end }}
  OPTIONAL {{ ?statement pq:P4100 ?group }}
  OPTIONAL {{ ?person rdfs:label ?nameHi . FILTER(LANG(?nameHi) = "hi") }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{languages}". }}
}}
"""

# Many person items now carry their name only as a language-neutral "mul" label.
LABEL_LANGUAGES = "en,mul"

PARTIES_QUERY = """
SELECT ?person ?party ?partyLabel ?start ?end WHERE {{
  VALUES ?person {{ {persons} }}
  ?person p:P102 ?statement .
  ?statement ps:P102 ?party ;
             wikibase:rank ?rank .
  FILTER(?rank != wikibase:DeprecatedRank)
  OPTIONAL {{ ?statement pq:P580 ?start }}
  OPTIONAL {{ ?statement pq:P582 ?end }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{languages}". }}
}}
"""


@dataclass(frozen=True)
class PositionMapping:
    position_qid: str
    entity_slug: str
    office_type: str
    title: str


@dataclass(frozen=True)
class RawTerm:
    statement_id: str
    position_qid: str
    person_qid: str
    person_name: str
    person_name_hi: str | None
    start: date | None
    end: date | None
    group_parties: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class PartyMembership:
    person_qid: str
    party_qid: str
    party_label: str
    start: date | None
    end: date | None

    def covers(self, day: date) -> bool:
        return (self.start is None or self.start <= day) and (self.end is None or day <= self.end)


@dataclass
class Term:
    external_id: str
    entity_slug: str
    office_type: str
    title: str
    person_qid: str
    person_name: str
    person_name_hi: str | None
    start: date
    end: date | None
    party_qid: str | None = None
    party_label: str | None = None
    source_url: str = ""
    source_type: str = "wikidata"
    # Problems with who held the office or when: the term is hidden until reviewed.
    notes: list[str] = field(default_factory=list)
    # Disagreement with an independent source about who holds the office now. Always hides
    # the term: a maintainer's earlier "reviewed" cannot outlive a change of office-holder.
    conflicts: list[str] = field(default_factory=list)
    # Problems that only blank out a detail (an unverified party is never shown); still shown.
    advisories: list[str] = field(default_factory=list)
    reviewed: bool = False

    @property
    def needs_review(self) -> bool:
        return bool(self.conflicts) or (bool(self.notes) and not self.reviewed)

    @property
    def review_note(self) -> str | None:
        return "; ".join(self.conflicts + self.notes + self.advisories) or None


@dataclass
class BuildResult:
    terms: list[Term]
    problems: list[str]


def load_position_map() -> list[PositionMapping]:
    resource = files("unnati.reference").joinpath("wikidata_positions.csv")
    with resource.open(encoding="utf-8", newline="") as fh:
        return [PositionMapping(**row) for row in csv.DictReader(fh)]


def load_overrides() -> dict[str, dict]:
    resource = files("unnati.manual").joinpath("officials_overrides.yaml")
    with resource.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


# --- Fetching ------------------------------------------------------------------------------


def fetch(http: PoliteClient, mappings: list[PositionMapping]) -> tuple[list[RawTerm], list[PartyMembership]]:
    positions = sorted({m.position_qid for m in mappings})
    query = TERMS_QUERY.format(positions=values_clause(positions), languages=LABEL_LANGUAGES)
    raw_terms = parse_terms(sparql(http, query))
    people = sorted({t.person_qid for t in raw_terms})
    memberships: list[PartyMembership] = []
    for chunk in (people[i : i + 200] for i in range(0, len(people), 200)):
        rows = sparql(http, PARTIES_QUERY.format(persons=values_clause(chunk), languages=LABEL_LANGUAGES))
        memberships.extend(parse_memberships(rows))
    return raw_terms, memberships


def parse_terms(rows: Iterable[Mapping[str, str]]) -> list[RawTerm]:
    statements: dict[str, dict] = {}
    for row in rows:
        statement_id = row["statement"].rsplit("/", 1)[-1]
        entry = statements.setdefault(
            statement_id,
            {
                "position_qid": qid(row["position"]),
                "person_qid": qid(row["person"]),
                "person_name": row.get("personLabel", qid(row["person"])),
                "person_name_hi": row.get("nameHi"),
                "start": to_date(row.get("start")),
                "end": to_date(row.get("end")),
                "groups": {},
            },
        )
        if "group" in row:
            entry["groups"][qid(row["group"])] = row.get("groupLabel", qid(row["group"]))
    return [
        RawTerm(
            statement_id=statement_id,
            position_qid=e["position_qid"],
            person_qid=e["person_qid"],
            person_name=e["person_name"],
            person_name_hi=e["person_name_hi"],
            start=e["start"],
            end=e["end"],
            group_parties=tuple(sorted(e["groups"].items())),
        )
        for statement_id, e in statements.items()
    ]


def parse_memberships(rows: Iterable[Mapping[str, str]]) -> list[PartyMembership]:
    found = {
        PartyMembership(
            person_qid=qid(row["person"]),
            party_qid=qid(row["party"]),
            party_label=row.get("partyLabel", qid(row["party"])),
            start=to_date(row.get("start")),
            end=to_date(row.get("end")),
        )
        for row in rows
    }
    return sorted(found, key=lambda m: (m.person_qid, m.party_qid, m.start or date.min))


# --- Building and checking terms --------------------------------------------------------------


def resolve_party(
    raw: RawTerm, memberships: list[PartyMembership]
) -> tuple[str | None, str | None, str | None]:
    """Party during the term: the statement's own party qualifier and the person's membership at
    the start of the term must agree. Returns (qid, label, problem)."""
    assert raw.start is not None
    groups = dict(raw.group_parties)
    members = {m.party_qid: m.party_label for m in memberships if m.covers(raw.start)}
    if groups and members:
        agreed = groups.keys() & members.keys()
        if len(agreed) == 1:
            party = agreed.pop()
            return party, groups[party], None
        return (
            None,
            None,
            (
                f"party sources disagree: term says {', '.join(groups.values())}; "
                f"membership says {', '.join(members.values())}"
            ),
        )
    candidates = groups or members
    if len(candidates) == 1:
        party, label = next(iter(candidates.items()))
        return party, label, None
    if not candidates:
        return None, None, "no party recorded"
    return None, None, f"several possible parties: {', '.join(sorted(candidates.values()))}"


def build_terms(
    raw_terms: Iterable[RawTerm],
    memberships: Iterable[PartyMembership],
    mappings: Iterable[PositionMapping],
    entities: Mapping[str, Entity],
    today: date,
) -> BuildResult:
    by_position: dict[str, list[PositionMapping]] = defaultdict(list)
    for mapping in mappings:
        if mapping.entity_slug not in entities:
            raise ValueError(f"position map refers to unknown entity {mapping.entity_slug!r}")
        by_position[mapping.position_qid].append(mapping)
    memberships_by_person: dict[str, list[PartyMembership]] = defaultdict(list)
    for m in memberships:
        memberships_by_person[m.person_qid].append(m)

    terms: list[Term] = []
    problems: list[str] = []
    seen: set[tuple] = set()
    for raw in sorted(raw_terms, key=lambda r: r.statement_id):
        key = (raw.position_qid, raw.person_qid, raw.start, raw.end)
        if key in seen:  # Wikidata sometimes holds the same term twice
            continue
        seen.add(key)
        if raw.end is not None and raw.end < EARLIEST_RELEVANT:
            continue
        if raw.start is None:
            problems.append(f"{raw.person_name} ({raw.person_qid}): term has no start date; skipped")
            continue
        for mapping in by_position.get(raw.position_qid, []):
            entity = entities[mapping.entity_slug]
            window_start = entity.valid_from or date.min
            window_end = entity.valid_to or date.max
            if (raw.end or today) < window_start or raw.start > window_end:
                continue  # the term belongs to the other entity sharing this position
            end = raw.end
            if entity.valid_to is not None and (end is None or end > entity.valid_to):
                end = entity.valid_to
            term = Term(
                external_id=f"wikidata:{raw.statement_id}:{mapping.entity_slug}",
                entity_slug=mapping.entity_slug,
                office_type=mapping.office_type,
                title=mapping.title,
                person_qid=raw.person_qid,
                person_name=raw.person_name,
                person_name_hi=raw.person_name_hi,
                start=max(raw.start, window_start),
                end=end,
                source_url=f"https://www.wikidata.org/wiki/{raw.person_qid}",
            )
            if raw.end is not None and raw.end < raw.start:
                term.notes.append("term ends before it starts")
            if raw.person_name == raw.person_qid:
                term.notes.append("no English name in Wikidata")
            if mapping.office_type in PARTY_OFFICES:
                party, label, problem = resolve_party(raw, memberships_by_person[raw.person_qid])
                term.party_qid, term.party_label = party, label
                if problem:  # the party stays blank; the person and tenure are still shown
                    term.advisories.append(problem)
            if term.end is None and today - term.start > STALE_AFTER:
                term.notes.append(STALE_NOTE.format(start=term.start))
            terms.append(term)

    return BuildResult(terms, problems)


STALE_NOTE = "in office since {start} with no end date; possibly out of date"


def flag_overlaps(terms: list[Term], today: date) -> None:
    """Run last, after overrides, curated terms and cross-checks have settled the dates."""
    by_office: dict[tuple[str, str], list[Term]] = defaultdict(list)
    for t in terms:
        by_office[(t.entity_slug, t.office_type)].append(t)
    for group in by_office.values():
        group.sort(key=lambda t: t.start)
        for earlier, later in pairwise(group):
            if later.start < (earlier.end or today) - OVERLAP_TOLERANCE:
                earlier.notes.append(f"overlaps with {later.person_name} (from {later.start})")
                later.notes.append(f"overlaps with {earlier.person_name} (until {earlier.end or 'now'})")


def apply_overrides(terms: list[Term], overrides: Mapping[str, Mapping]) -> list[str]:
    """Apply maintainer decisions keyed by external_id. Returns override keys that matched nothing."""
    by_id = {t.external_id: t for t in terms}
    unused = []
    for external_id, override in overrides.items():
        term = by_id.get(external_id)
        if term is None:
            unused.append(external_id)
            continue
        if "source_url" not in override:
            raise ValueError(f"override {external_id!r} needs a source_url")
        if "party" in override:
            term.party_qid = override["party"]
            term.party_label = override.get("party_label", term.party_label)
            term.advisories = [a for a in term.advisories if "part" not in a]
        if "person_name" in override:  # e.g. a vandalised or mislabelled Wikidata item
            term.person_name = override["person_name"]
            term.notes = [n for n in term.notes if n != "no English name in Wikidata"]
        for attr in ("start", "end"):
            if attr in override:
                setattr(term, attr, override[attr])
        if term.end is not None:  # an end date settles the "possibly out of date" question
            term.notes = [n for n in term.notes if not n.endswith("possibly out of date")]
        term.source_url = override["source_url"]
        term.reviewed = bool(override.get("reviewed", False))
        if note := override.get("note"):
            term.advisories.append(f"maintainer: {note}")
    return unused


def load_curated() -> list[dict]:
    resource = files("unnati.manual").joinpath("officials.yaml")
    with resource.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or []


def curated_terms(entries: Iterable[Mapping], mappings: Iterable[PositionMapping]) -> list[Term]:
    """Officially sourced terms that Wikidata lacks (recent appointments, missing history)."""
    titles = {(m.entity_slug, m.office_type): m.title for m in mappings}
    terms = []
    for entry in entries:
        key = (entry["entity"], entry["office"])
        if key not in titles:
            raise ValueError(f"curated term for unknown office {key}")
        for required in ("person", "wikidata", "start", "source_url"):
            if not entry.get(required):
                raise ValueError(f"curated term {entry.get('person', key)} needs {required!r}")
        term = Term(
            external_id=f"curated:{entry['entity']}:{entry['office']}:{entry['wikidata']}:{entry['start']}",
            entity_slug=entry["entity"],
            office_type=entry["office"],
            title=titles[key],
            person_qid=entry["wikidata"],
            person_name=entry["person"],
            person_name_hi=entry.get("person_hi"),
            start=entry["start"],
            end=entry.get("end"),
            party_qid=entry.get("party") if entry["office"] in PARTY_OFFICES else None,
            party_label=entry.get("party_label") if entry["office"] in PARTY_OFFICES else None,
            source_url=entry["source_url"],
            source_type="curated",
            reviewed=True,
        )
        if entry.get("additional_charge"):
            term.advisories.append("additional charge")
        if note := entry.get("note"):
            term.advisories.append(f"maintainer: {note}")
        terms.append(term)
    return terms


def merge_curated(terms: list[Term], curated: list[Term]) -> tuple[list[Term], list[str]]:
    """Curated terms win over Wikidata duplicates (same office, person and start within 15 days),
    and say so, so that the curated entry can be retired once Wikidata has caught up."""
    notes = []
    kept = []
    for t in terms:
        twin = next(
            (
                c
                for c in curated
                if (c.entity_slug, c.office_type, c.person_qid)
                == (t.entity_slug, t.office_type, t.person_qid)
                and abs((c.start - t.start).days) <= 15
            ),
            None,
        )
        if twin:
            notes.append(f"Wikidata now has {twin.external_id}; the curated entry can be retired")
        else:
            kept.append(t)
    return kept + curated, notes


def categories_for(
    office_type: str, entity_slug: str, has_head_of_government: bool, ranked: list[str]
) -> list[str]:
    """Which topic categories an office answers for."""
    if office_type in HEAD_OF_GOVERNMENT:
        return list(ranked)
    if office_type in ("lieutenant_governor", "administrator") and not has_head_of_government:
        return list(ranked)  # UTs without an elected government are run by the LG/Administrator
    categories = ["governance"]
    if office_type == "lieutenant_governor" and entity_slug in POLICE_UNDER_LIEUTENANT_GOVERNOR:
        categories.append("crime")
    return categories


def fingerprint(terms: Iterable[Term]) -> str:
    payload = sorted(
        (t.external_id, t.person_qid, str(t.start), str(t.end), t.party_qid or "", t.needs_review)
        for t in terms
    )
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()
