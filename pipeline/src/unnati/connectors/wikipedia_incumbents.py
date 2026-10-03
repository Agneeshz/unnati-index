"""Who holds each office *now*, according to Wikipedia's incumbent tables.

Wikidata's office-holder statements often lag months behind appointments, while Wikipedia's
"Chief minister (India)" and "Governor (India)" articles are updated within days. Each sync
compares the two, matching people by Wikidata ID (via the article links), never by spelling:

* both agree  -> a long-serving incumbent is confirmed, so the staleness flag is cleared;
* they differ -> our incumbent is hidden and the report names the current holder, to be added
  to ``manual/officials.yaml`` from an official source.

Wikipedia is used only as a cross-check signal, never as the published source of a term.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from unnati.core.entities import EntityResolver, UnknownEntityError
from unnati.core.http import PoliteClient
from unnati.core.periods import day

RAW_URL = "https://en.wikipedia.org/w/index.php?title={title}&action=raw"
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"

# (article, section heading, office type)
TABLES = (
    ("Chief_minister_(India)", "List of chief ministers", "chief_minister"),
    ("Governor_(India)", "List of incumbent governors", "governor"),
    ("Governor_(India)", "List of incumbent lieutenant governors", "lieutenant_governor"),
    ("Governor_(India)", "List of incumbent Administrators", "administrator"),
)
MIN_ROWS = 30  # fewer than this means the page layout changed; skip the cross-check

_LINK = r"\[\[([^\]|#]+)(?:\|([^\]]*))?\]\]"


@dataclass(frozen=True)
class Incumbent:
    place: str
    office_type: str
    article: str
    person: str
    start: date | None


def _dts(row: str) -> date | None:
    m = re.search(r"\{\{dts\|(?:format=dmy\|)?(\d{4})\|(\d{1,2})\|(\d{1,2})", row)
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def parse_table(wikitext: str, heading: str, office_type: str) -> list[Incumbent]:
    start = wikitext.find(heading)
    if start < 0:
        return []
    line_start = wikitext.rfind("\n", 0, start) + 1
    if wikitext[line_start:start].lstrip().startswith("|+"):  # a caption: the table began above it
        table_start = wikitext.rfind("{|", 0, start)
    else:
        table_start = wikitext.find("{|", start)
    table = wikitext[table_start : wikitext.find("\n|}", table_start)]
    found = []
    for row in table.split("\n|-")[1:]:
        place = re.search(r"^\|\s*" + _LINK, row.strip("\n"), re.M)
        # The officeholder cell is a header cell ("! [[Name]]") or bold ("'''[[Name]]'''").
        person = re.search(r"^!\s*" + _LINK, row, re.M) or re.search(
            r"'''\s*" + _LINK + r"\s*'''|" + r"\[\[([^\]|#]+)\|'''([^']+)'''\]\]", row
        )
        if not (place and person):
            continue
        groups = [g for g in person.groups() if g]
        found.append(
            Incumbent(place[1].strip(), office_type, groups[0].strip(), groups[-1].strip(), _dts(row))
        )
    return found


def fetch(http: PoliteClient) -> tuple[list[Incumbent], dict[str, str]]:
    """Incumbents from Wikipedia plus a map of article title -> Wikidata ID."""
    pages: dict[str, str] = {}
    incumbents: list[Incumbent] = []
    for article, heading, office_type in TABLES:
        if article not in pages:
            pages[article] = http.get(RAW_URL.format(title=article)).text
        incumbents.extend(parse_table(pages[article], heading, office_type))
    return incumbents, resolve_articles(http, {i.article for i in incumbents})


def resolve_articles(http: PoliteClient, titles: Iterable[str]) -> dict[str, str]:
    """Article title -> Wikidata ID, following Wikipedia redirects (links often use old titles)."""
    titles = sorted(titles)
    qids: dict[str, str] = {}
    for chunk in (titles[i : i + 50] for i in range(0, len(titles), 50)):
        payload = http.get(
            WIKIPEDIA_API_URL,
            params={
                "action": "query",
                "prop": "pageprops",
                "ppprop": "wikibase_item",
                "redirects": "1",
                "titles": "|".join(chunk),
                "format": "json",
            },
        ).json()
        qids.update(parse_pageprops(payload))
    return qids


def parse_pageprops(payload: Mapping) -> dict[str, str]:
    query = payload.get("query", {})
    found = {
        page["title"]: page["pageprops"]["wikibase_item"]
        for page in query.get("pages", {}).values()
        if "wikibase_item" in page.get("pageprops", {})
    }
    # Map the titles as linked (normalised, then redirected) onto the resolved article.
    for step in ("redirects", "normalized"):
        for hop in reversed(query.get(step, [])):
            if hop["to"] in found:
                found[hop["from"]] = found[hop["to"]]
    return found


def cross_check(
    terms: list,
    incumbents: list[Incumbent],
    article_qids: Mapping[str, str],
    resolver: EntityResolver,
    today: date,
    stale_note_suffix: str = "possibly out of date",
) -> list[str]:
    """Confirm or contradict our current office-holders. Returns report lines."""
    if len(incumbents) < MIN_ROWS:
        return [f"Wikipedia cross-check skipped: only {len(incumbents)} incumbents parsed"]
    report = []
    for inc in incumbents:
        try:
            entity = resolver.resolve(inc.place, day(today))
        except UnknownEntityError as err:
            report.append(f"Wikipedia cross-check: {err}")
            continue
        if entity is None:
            continue
        qid = article_qids.get(inc.article) or article_qids.get(inc.article.replace("_", " "))
        current = [
            t
            for t in terms
            if (t.entity_slug, t.office_type) == (entity.slug, inc.office_type) and t.end is None
        ]
        if qid and any(t.person_qid == qid for t in current):
            for t in current:
                if t.person_qid == qid:
                    t.notes = [n for n in t.notes if not n.endswith(stale_note_suffix)]
                    t.advisories.append(f"confirmed current by Wikipedia on {today}")
            continue
        since = f" since {inc.start}" if inc.start else ""
        message = f"Wikipedia lists {inc.person} ({qid or 'no Wikidata ID'}) as current{since}"
        for t in current:
            t.conflicts.append(message)
        report.append(f"needs a curated term: {entity.slug} {inc.office_type}: {message}")
    return report
