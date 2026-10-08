from unnati.connectors import cities
from unnati.reference import city_lookup, city_names, load_reference

LIST = """
{|class="wikitable sortable"
!scope="col" rowspan=2| Name
!scope="col" rowspan=2| State or Union territory
|-
| style="width:1em" | [[Mumbai]] || [[Maharashtra]] || 12,442,373 || 11,978,450 || {{Coord|19.0760|72.8777}}
|-
| [[Gaya, India|Gaya]] || [[Bihar]] || 468,614 || 385,432 || {{change}} || {{Coord|24.75|85.01}}
|-
| colspan="2" |India |1,210,854,977 |1,028,737,436
|}
"""


def test_parse_list_reads_name_state_population_and_coordinates():
    rows = cities.parse_list(LIST)
    assert [(r.title, r.name, r.state, r.population) for r in rows] == [
        ("Mumbai", "Mumbai", "Maharashtra", 12_442_373),
        ("Gaya, India", "Gaya", "Bihar", 468_614),
    ]
    assert (rows[0].latitude, rows[0].longitude) == (19.076, 72.8777)


def test_slugs_avoid_state_names():
    assert cities.slugify("Sangli-Miraj & Kupwad") == "sangli-miraj-and-kupwad"


def test_roster_is_consistent():
    ref = load_reference()
    roster = [e for e in ref.entities if e.type == "city"]
    states = {e.slug for e in ref.entities if e.type in ("state", "ut") and e.valid_to is None}
    assert len(roster) >= 100
    assert len({c.slug for c in roster}) == len(roster)
    assert all(c.parent_slug in states for c in roster)
    # Every state and UT with a capital in the roster appears on its own map.
    assert len({c.parent_slug for c in roster}) >= 34
    # Inside India's bounding box.
    assert all(6 <= c.latitude <= 37 and 68 <= c.longitude <= 98 for c in roster)
    # NCRB's 19 metropolitan cities are all present.
    assert len(set(city_names("ncrb").values())) == 19


def test_lookup_knows_old_names_twin_cities_and_other_spellings():
    lookup = city_lookup()
    assert lookup[("haryana", "gurgaon")] == "gurugram"
    assert lookup[("maharashtra", "dombivli")] == "kalyan-dombivli"
    assert lookup[("karnataka", "bangalore")] == "bengaluru"
    assert ("bihar", "bangalore") not in lookup  # names only match within their state
