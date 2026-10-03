"""Current Chief Secretaries and police chiefs, from Wikipedia's maintained tables.

There is no official consolidated list online: DoPT's periodic "List of Chief Secretaries" PDFs
are removed after publication and not archived. So the current holder is read from the tables
in the "Chief secretary (India)" and "Director general of police" articles, keeping each row's
own citation where it has one, and labelled as such on the site.

Tenure is *observed*, not invented: a term starts on the day the pipeline first sees the person
listed and ends when it first sees someone else (see ``officials.load_observed_terms``).
Upgrade an entry to an official source by adding it to ``manual/officials.yaml``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from unnati.core.http import PoliteClient

RAW_URL = "https://en.wikipedia.org/w/index.php?title={title}&action=raw"
PAGE_URL = "https://en.wikipedia.org/wiki/{title}"

# (article, caption text identifying the table, office type)
TABLES = (
    ("Chief_secretary_(India)", "List of current Chief Secretaries in the States", "chief_secretary"),
    ("Chief_secretary_(India)", "List of current Chief Secretaries/Advisor", "chief_secretary"),
    ("Director_general_of_police", "State Police Chiefs", "dgp"),
    ("Director_general_of_police", "Police Chiefs of Union Territories", "dgp"),
)
MIN_ROWS = 50  # 36 Chief Secretaries + 36 police chiefs, give or take; fewer means a layout change


@dataclass(frozen=True)
class Listed:
    place: str
    office_type: str
    name: str
    acting: bool
    additional_charge: bool
    citation: str | None
    page_url: str


def _cells(row: str) -> list[str]:
    cells = []
    for line in row.strip("\n").split("\n"):
        if line.startswith("|") and not line.startswith(("|-", "|+", "|}")):
            cells.append(line[1:])
        elif cells:  # continuation of a multi-line cell
            cells[-1] += "\n" + line
    return cells


def _strip_attributes(cell: str) -> str:
    # "align=center|Name" -> "Name" (attributes come before a single pipe outside links)
    depth, last_pipe = 0, -1
    for i, ch in enumerate(cell):
        if cell.startswith(("[[", "{{"), i):
            depth += 1
        elif cell.startswith(("]]", "}}"), i):
            depth -= 1
        elif ch == "|" and depth == 0:
            last_pipe = i
    return cell[last_pipe + 1 :] if last_pipe >= 0 else cell


def clean_name(cell: str) -> tuple[str, bool, bool]:
    """'''Kamlesh Kumar Pant'' ''(additional charge)'', IAS<ref>..</ref>' -> name and flags."""
    text = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", cell, flags=re.S)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"<[^>]+>|'''|''|\{\{[^}]*\}\}", "", text)
    acting = bool(re.search(r"\bacting\b|in[- ]charge", text, re.I))
    additional = bool(re.search(r"additional charge", text, re.I))
    text = re.sub(r"\((?:acting|additional charge|in[- ]charge)\)", "", text, flags=re.I)
    text = re.sub(r",?\s*\b(?:IAS|IPS|Indian Police Service|Indian Administrative Service)\b\.?", "", text)
    text = re.sub(r"^(?:Dr|Shri|Smt)\.?\s+", "", text.strip())
    return re.sub(r"\s+", " ", text).strip(" ,"), acting, additional


def parse_table(wikitext: str, caption: str, office_type: str, article: str) -> list[Listed]:
    at = wikitext.find(caption)
    if at < 0:
        return []
    start = wikitext.rfind("{|", 0, at)
    table = wikitext[start : wikitext.find("\n|}", at)]
    chunks = table.split("\n|-")
    # Pick columns by header, not position: the states' table has an extra "List" column.
    headers = [_strip_attributes(h[1:]) for h in chunks[0].split("\n") if h.startswith("!")]
    try:
        place_col = next(i for i, h in enumerate(headers) if re.search(r"state|union territory", h, re.I))
        name_col = next(
            i for i, h in enumerate(headers) if re.search(r"chief secretary|police chief|name", h, re.I)
        )
    except StopIteration:
        return []
    found = []
    for row in chunks[1:]:
        cells = [_strip_attributes(c) for c in _cells(row)]
        if len(cells) <= max(place_col, name_col):
            continue
        place_match = re.search(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", cells[place_col])
        if not place_match:
            continue
        name, acting, additional = clean_name(cells[name_col])
        if not name or re.fullmatch(r"vacant|n/?a|-+", name, re.I):
            continue
        citation = re.search(r"\|\s*url\s*=\s*(https?://[^\s|}]+)", row)
        found.append(
            Listed(
                place=place_match[1].strip(),
                office_type=office_type,
                name=name,
                acting=acting,
                additional_charge=additional,
                citation=citation[1] if citation else None,
                page_url=PAGE_URL.format(title=article),
            )
        )
    return found


def fetch(http: PoliteClient) -> list[Listed]:
    pages: dict[str, str] = {}
    listed: list[Listed] = []
    for article, caption, office_type in TABLES:
        if article not in pages:
            pages[article] = http.get(RAW_URL.format(title=article)).text
        listed.extend(parse_table(pages[article], caption, office_type, article))
    return listed
