"""The city roster (reference/cities.csv): which cities the site covers, where they are and what
each source calls them. Built by `unnati cities build`, then reviewed like any reference file.

- Cities: every city with at least MIN_POPULATION people in the 2011 Census, from Wikipedia's
  "List of cities in India by population" (which reproduces the Census city figures and
  coordinates), plus state and UT capitals below that size (CAPITALS), so every state map has
  at least its capital.
- Names: current official names (RENAMES) where the list still uses old ones; Hindi names and
  missing coordinates from Wikidata (CC0), found through each city's Wikipedia article.
- Source names: `ncrb_name` and `cpcb_name` say what NCRB's metropolitan-city tables and CPCB's
  daily AQI bulletin call the city. Existing values are kept; CPCB names are otherwise matched
  automatically against reference/cpcb_cities.csv."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import asdict, dataclass

from unnati.core.entities import EntityResolver, normalize_name
from unnati.core.http import PoliteClient
from unnati.core.periods import calendar_year

LIST_URL = "https://en.wikipedia.org/w/index.php?title=List_of_cities_in_India_by_population&action=raw"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
MIN_POPULATION = 400_000
MILLION_PLUS = 1_000_000

# Capitals under MIN_POPULATION (or missing from the list): Wikipedia title -> state/UT slug.
CAPITALS = {
    "Panaji": "goa",
    "Shillong": "meghalaya",
    "Kohima": "nagaland",
    "Gangtok": "sikkim",
    "Itanagar": "arunachal-pradesh",
    "Sri Vijaya Puram": "andaman-and-nicobar-islands",
    "Leh": "ladakh",
    "Kavaratti": "lakshadweep",
    "Silvassa": "dadra-and-nagar-haveli-and-daman-and-diu",
    "Gandhinagar": "gujarat",
    "Shimla": "himachal-pradesh",
    "Imphal": "manipur",
    "Aizawl": "mizoram",
    "Puducherry": "puducherry",
}
# Current official names where the list uses an older one.
RENAMES = {
    "Allahabad": "Prayagraj",
    "Aurangabad": "Chhatrapati Sambhajinagar",
    "Ahmednagar": "Ahilyanagar",
    "Bellary": "Ballari",
    "Belgaum": "Belagavi",
    "Gulbarga": "Kalaburagi",
    "Gurgaon": "Gurugram",
    "Hubli–Dharwad": "Hubballi-Dharwad",
    "Mangalore": "Mangaluru",
    "Mysore": "Mysuru",
    "Bokaro Steel City": "Bokaro",
    "South Dumdum": "South Dum Dum",
}
# Listed places that are no longer separate cities.
EXCLUDE = {
    "Ambattur": "merged into Greater Chennai Corporation in 2011",
    "Gopalpur": "Rajarhat-Gopalpur merged into Bidhannagar Municipal Corporation in 2015",
}
# Hindi names where Wikidata has an old name or a non-standard spelling.
HI_NAMES = {
    "chhatrapati-sambhajinagar": "छत्रपति संभाजीनगर",
    "hubballi-dharwad": "हुब्बल्ली-धारवाड़",
    "kozhikode": "कोझिकोड",
    "mysuru": "मैसूरु",
    "mangaluru": "मंगलुरु",
    "belagavi": "बेलगावी",
    "kalaburagi": "कलबुर्गी",
}
# Other spellings sources use (EnviStats especially), matched within the city's state.
ALT_NAMES = {
    "vijayawada": ["Vijaywada"],
    "bareilly": ["Bareily"],
    "bhubaneswar": ["Bhubneshwar"],
    "mira-bhayandar": ["Mira Bhayander"],
    "gorakhpur": ["Gorakpur"],
    "tiruchirappalli": ["Trichy"],
    "tiruppur": ["Tirupur"],
    "hubballi-dharwad": ["Hubli-Dharwad"],
    "kalaburagi": ["Gulburga", "Gulbarga"],
    "malegaon": ["Malegao"],
    "asansol": ["Asansol+Raniganj"],
    "sri-vijaya-puram": ["Port Blair"],
    # Swachh Survekshan names the municipal body.
    "mumbai": ["Greater Mumbai"],
    "hyderabad": ["Greater Hyderabad"],
    "bengaluru": ["Bangalore", "Bruhat Bengaluru Mahanagara Palike"],
    "delhi-city": ["Municipal Corporation of Delhi"],
    "visakhapatnam": ["Vishakhapatnam", "GVMC Visakhapatnam"],
    "kalyan-dombivli": ["Kalyan Dombivali"],
    "bhilai": ["Bhilai Nagar"],
    "bhiwandi": ["Bhiwandi Nizampur"],
}
# CPCB bulletin names that automatic matching cannot find.
CPCB_NAMES = {"chhatrapati-sambhajinagar": "Aurangabad (Maharashtra)"}
COLUMNS = [
    "slug", "name", "name_hi", "state_slug", "population_2011", "latitude", "longitude",
    "wikidata_qid", "ncrb_name", "cpcb_name",
]  # fmt: skip


@dataclass
class CityRow:
    slug: str
    name: str
    name_hi: str | None
    state_slug: str
    population_2011: int | None
    latitude: float
    longitude: float
    wikidata_qid: str | None
    ncrb_name: str | None = None
    cpcb_name: str | None = None


@dataclass(frozen=True)
class Listed:
    title: str
    name: str
    state: str
    population: int
    latitude: float | None
    longitude: float | None


_LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_COORD = re.compile(r"\{\{Coord\|(-?[\d.]+)\|(-?[\d.]+)", re.I)


def parse_list(text: str) -> list[Listed]:
    """Rows of the list's first table: name, state, 2011 and 2001 populations, coordinates."""
    start = text.index("{|")
    table = text[start : text.index("\n|}", start)]
    out = []
    for row in table.split("\n|-")[1:]:
        links = _LINK.findall(row)
        population = re.search(r"\|\|\s*([\d,]{6,})\s*\|\|", row)
        if len(links) < 2 or not population:
            continue
        coord = _COORD.search(row)
        (title, label), (state, state_label) = links[0], links[1]
        out.append(
            Listed(
                title=title.strip(),
                name=(label or title).split(",")[0].strip(),
                state=(state_label or state).strip(),
                population=int(population.group(1).replace(",", "")),
                latitude=float(coord.group(1)) if coord else None,
                longitude=float(coord.group(2)) if coord else None,
            )
        )
    return out


def resolve_titles(http: PoliteClient, titles: list[str]) -> dict[str, str]:
    """Wikipedia title -> the article it redirects to (or itself)."""
    out = {t: t for t in titles}
    for chunk in (titles[i : i + 50] for i in range(0, len(titles), 50)):
        response = http.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "titles": "|".join(chunk), "redirects": 1, "format": "json"},
        )
        query = response.json().get("query", {})
        steps = {s["from"]: s["to"] for s in query.get("normalized", []) + query.get("redirects", [])}
        for title in chunk:
            target = title
            while target in steps:
                target = steps[target]
            out[title] = target
    return out


def wikidata_details(http: PoliteClient, titles: list[str]) -> dict[str, dict]:
    """Wikipedia title -> {qid, name_hi, latitude, longitude} from Wikidata."""
    targets = resolve_titles(http, titles)
    found = _wikidata_by_target(http, sorted(set(targets.values())))
    return {title: found[target] for title, target in targets.items() if target in found}


def _wikidata_by_target(http: PoliteClient, titles: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for chunk in (titles[i : i + 50] for i in range(0, len(titles), 50)):
        data = http.get(
            WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "sites": "enwiki",
                "titles": "|".join(chunk),
                "props": "labels|claims|sitelinks",
                "languages": "hi|en",
                "sitefilter": "enwiki",
                "redirects": "yes",
                "format": "json",
            },
        ).json()
        for qid, entity in data.get("entities", {}).items():
            if "missing" in entity:
                continue
            title = entity.get("sitelinks", {}).get("enwiki", {}).get("title")
            coord = entity.get("claims", {}).get("P625", [{}])[0].get("mainsnak", {}).get("datavalue", {})
            value = coord.get("value", {}) if coord else {}
            out[title] = {
                "qid": qid,
                "name_hi": entity.get("labels", {}).get("hi", {}).get("value"),
                "latitude": value.get("latitude"),
                "longitude": value.get("longitude"),
            }
    return out


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize_name(name).replace("&", "and")).strip("-")


def build(
    http: PoliteClient,
    resolver: EntityResolver,
    taken_slugs: set[str],
    existing: list[dict],
    cpcb_cities: dict[str, str],
) -> tuple[list[CityRow], list[str]]:
    """The roster, plus problems to review. `taken_slugs` are state/UT slugs a city must not
    reuse; `existing` is the current cities.csv (its source names are kept); `cpcb_cities` maps
    normalised CPCB city names to their state slug."""
    problems: list[str] = []
    listed = parse_list(http.get(LIST_URL).text)
    today = calendar_year(2024)  # the list names today's states (Telangana, Ladakh)
    chosen: dict[str, tuple[Listed | None, str]] = {}
    for row in listed:
        if (row.population < MIN_POPULATION and row.name not in CAPITALS) or row.name in EXCLUDE:
            continue
        entity = resolver.resolve(row.state, today)
        if entity is None:
            problems.append(f"{row.name}: unknown state {row.state!r}")
            continue
        chosen.setdefault(row.title, (row, entity.slug))
    listed_names = {r.name for r, _ in chosen.values() if r}
    for title, state in CAPITALS.items():
        if title not in chosen and title not in listed_names:
            chosen[title] = (None, state)
    details = wikidata_details(http, sorted(chosen))
    previous = {row["slug"]: row for row in existing}
    by_name = {normalize_name(row.get("name") or row.get("ncrb_name") or ""): row for row in existing}
    rows: list[CityRow] = []
    for title, (listed_row, state) in chosen.items():
        info = details.get(title) or {}
        base = listed_row.name if listed_row else title.split(" (")[0]
        name = RENAMES.get(base, base)
        slug = slugify(name)
        if slug in taken_slugs:
            slug = f"{slug}-city"
        old = previous.get(slug) or by_name.get(normalize_name(name)) or {}
        latitude = (listed_row.latitude if listed_row else None) or info.get("latitude")
        longitude = (listed_row.longitude if listed_row else None) or info.get("longitude")
        if latitude is None or longitude is None:
            problems.append(f"{name}: no coordinates")
            continue
        cpcb = old.get("cpcb_name") or CPCB_NAMES.get(slug)
        if cpcb is None:
            # Twin cities ("Kalyan-Dombivli") appear in the bulletin under one of their names.
            parts = re.split(r"\s*[-–&]\s*", name)
            for candidate in (name, base, title.split(" (")[0], *parts):
                if cpcb_cities.get(normalize_name(candidate)) == state:
                    cpcb = candidate
                    break
        rows.append(
            CityRow(
                slug=slug,
                name=name,
                name_hi=HI_NAMES.get(slug) or old.get("name_hi") or info.get("name_hi"),
                state_slug=state,
                population_2011=listed_row.population if listed_row else None,
                latitude=round(float(latitude), 4),
                longitude=round(float(longitude), 4),
                wikidata_qid=info.get("qid"),
                ncrb_name=old.get("ncrb_name"),
                cpcb_name=cpcb,
            )
        )
    missing_metros = {r["slug"] for r in existing if r.get("ncrb_name")} - {r.slug for r in rows}
    problems += [f"NCRB city {slug} is no longer in the roster" for slug in sorted(missing_metros)]
    rows.sort(key=lambda r: (-(r.population_2011 or 0), r.name))
    return rows, problems


def to_csv(rows: list[CityRow]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if v is None else v) for k, v in asdict(row).items()})
    return buffer.getvalue()
