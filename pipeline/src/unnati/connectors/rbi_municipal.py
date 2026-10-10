"""RBI's Report on Municipal Finances: how much of their revenue municipal corporations raise
themselves, by state.

The report's tables are published as web pages (www.rbi.org.in loads; the XLSX copies on
rbidocs are behind a bot check). Statement 3, "Own Revenue of Municipal Corporations – Key
Ratios", gives for each state the corporations' own revenue (own taxes such as property tax,
plus fees and charges) as a share of their revenue receipts, the rest being grants and assigned
revenue from the state. Figures cover municipal corporations only, summed by state: the report
has no figures for individual cities. Accounts are used, and revised estimates as provisional;
budget estimates are skipped, as for state finances."""

from __future__ import annotations

import html
import re

from unnati.core.entities import EntityResolver, UnknownEntityError
from unnati.core.http import PoliteClient
from unnati.core.periods import fiscal_year
from unnati.observations import Observation

LISTING = "https://www.rbi.org.in/Scripts/AnnualPublications.aspx?head=Report%20on%20Municipal%20Finances"
PAGE = "https://www.rbi.org.in/Scripts/PublicationsView.aspx?id={id}"
_STATEMENT = re.compile(
    r"PublicationsView\.aspx\?id=(\d+)[^>]*>\s*Statement 3: Own Revenue of Municipal", re.I
)
_STATUS = {"acc": "A", "rev": "RE", "bud": "BE"}  # Accounts, Revised / Budget Estimates
_YEAR = re.compile(r"(\d{4})-(?:\d{2}|\d{4})\s*\((\w+)")


def statement_url(http: PoliteClient) -> str:
    """The latest edition's Statement 3 page, found from the report's publication list."""
    match = _STATEMENT.search(http.get(LISTING).text)
    if not match:
        raise RuntimeError("RBI municipal finances: Statement 3 is no longer listed")
    return PAGE.format(id=match.group(1))


def _cells(row_html: str) -> list[tuple[int, str]]:
    """(colspan, text) for each cell of a table row."""
    out = []
    for attrs, body in re.findall(r"<t[dh]([^>]*)>(.*?)</t[dh]>", row_html, flags=re.S | re.I):
        span = re.search(r"colspan\s*=\s*['\"]?(\d+)", attrs, flags=re.I)
        text = html.unescape(re.sub(r"<[^>]+>", " ", body))
        out.append((int(span.group(1)) if span else 1, " ".join(text.split())))
    return out


def table(page_html: str) -> list[tuple[str, list[tuple[str, str, float | None]]]]:
    """(state, [(fiscal year start, status, own revenue / revenue receipts)]) per state row.

    The first column group of the statement is "Own Revenue / Revenue Receipts": one column per
    year, labelled like "2022-23 (Revised Estimates)"."""
    rows = [_cells(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", page_html, flags=re.S | re.I)]
    header = next((i for i, r in enumerate(rows) if r and re.match(r"(?i)state\s*/\s*ut", r[0][1])), None)
    if header is None:
        return []
    group = rows[header][1][0]  # the first group's width = number of years
    years = []
    for _, label in rows[header + 1][:group]:
        found = _YEAR.search(label.replace(" ", ""))
        if found:
            years.append((found.group(1), _STATUS.get(found.group(2).lower()[:3], "BE")))
    out = []
    for row in rows[header + 2 :]:
        if len(row) < 1 + len(years) or row[0][1].isdigit():  # the column-number row
            continue
        name = re.sub(r"^\d+\.\s*", "", row[0][1])
        values = []
        for (start, status), (_, text) in zip(years, row[1 : 1 + len(years)], strict=False):
            try:
                values.append((start, status, float(text.replace(",", ""))))
            except ValueError:
                values.append((start, status, None))
        out.append((name, values))
    return out


def observations(page_html: str, resolver: EntityResolver) -> tuple[list[Observation], list[str]]:
    out: list[Observation] = []
    problems: list[str] = []
    rows = table(page_html)
    if len(rows) < 20:
        problems.append(f"RBI municipal finances: only {len(rows)} state rows read")
    for name, values in rows:
        for start, status, ratio in values:
            if ratio is None or status == "BE":
                continue
            period = fiscal_year(int(start))
            try:
                entity = resolver.resolve("All India" if name.lower() == "total" else name, period)
            except UnknownEntityError as err:
                problems.append(str(err))
                continue
            if entity is None:
                continue
            kind = "accounts" if status == "A" else "revised estimates"
            note = (
                f"RBI Report on Municipal Finances, Statement 3 ({kind}): "
                "municipal corporations' own revenue / revenue receipts"
            )
            out.append(
                Observation(
                    "municipal-own-revenue-share",
                    entity.slug,
                    period,
                    round(ratio * 100, 1),
                    is_provisional=status == "RE",
                    note=note,
                )
            )
    return out, sorted(set(problems))
