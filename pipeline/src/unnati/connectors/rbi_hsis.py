"""RBI Handbook of Statistics on Indian States: state finances, power, environment and more.

The handbook's index page (rbi.org.in) lists every table with an XLSX link, but the files on
rbidocs.rbi.org.in sit behind a JavaScript bot challenge. The challenge is not bypassed: the
maintainer downloads the needed files in a browser once per edition into
`pipeline/manual-downloads/rbi_hsis/<edition>/` (`unnati manual rbi-links` prints the links), and the
files are committed. RBI names each file after its table ("164T_<id>.XLSX"), so the importer
finds tables by that prefix. The daily run reads the index page to notice a newer edition."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

from unnati.core.http import PoliteClient

INDEX_URL = "https://www.rbi.org.in/Scripts/AnnualPublications.aspx?head=Handbook%20of%20Statistics%20on%20Indian%20States"
MANUAL_DIR = Path(__file__).resolve().parents[3] / "manual-downloads" / "rbi_hsis"

# Tables the importer reads, by number in the 2024-25 edition (titles are checked on import,
# since numbering can shift between editions).
TABLES = {
    10: "Poverty Estimates - Multi-dimensional Poverty Index",
    16: "Health Infrastructure - Doctors and Specialists",
    17: "Number of Government Hospitals and Beds",
    99: "Forest Cover",
    107: "Status of Ground Water Extraction",
    138: "Per Capita Availability of Power",
    140: "Installed Capacity of Power",
    143: "Installed Capacity of Grid Interactive Renewable Power",
    149: "Telephones per 100 Population",
    153: "Credit-Deposit Ratio of Scheduled Commercial Banks",
    164: "Gross Fiscal Deficit",
    166: "Revenue Expenditure",
    168: "Own Tax Revenue",
    173: "Capital Expenditure",
    174: "Capital Outlay",
    176: "Composition of Outstanding Liabilities",
    181: "State-wise Exports",
}


@dataclass(frozen=True)
class Listed:
    number: int
    title: str
    url: str


def edition_of(page: str) -> str:
    match = re.search(r"Handbook of Statistics on Indian States (\d{4}-\d{2})", page)
    if not match:
        raise RuntimeError("RBI handbook index: edition not found")
    return match.group(1)


def listed_tables(page: str) -> list[Listed]:
    out = []
    for title, rest in re.findall(r"PublicationsView\.aspx\?id=\d+>([^<]+)</a>(.{0,600})", page, re.S):
        number = re.match(r"\s*Table\s*(\d+)\s*:", html.unescape(title))
        links = re.findall(r"href=['\"]?([^'\" >]+\.xlsx)", rest, re.I)
        if number and links:
            out.append(Listed(int(number.group(1)), html.unescape(title).strip(), links[0]))
    return out


def index(http: PoliteClient) -> tuple[str, list[Listed]]:
    page = http.get(INDEX_URL).text
    return edition_of(page), listed_tables(page)


def local_files(edition: str) -> dict[int, Path]:
    """Table number -> downloaded file, from RBI's "<n>T_" file-name prefix."""
    folder = MANUAL_DIR / edition
    found = {}
    for path in folder.glob("*"):
        match = re.match(r"(?i)^(\d+)T_.*\.xlsx$", path.name)
        if match:
            found[int(match.group(1))] = path
    return found
