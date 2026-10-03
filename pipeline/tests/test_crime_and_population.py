from datetime import date

from unnati.connectors import morth, ncrb
from unnati.reference import load_reference, population

REF = load_reference()

# Excerpt of Crime in India 2024, Table 2A.1, as pdfplumber extracts it.
MURDER = """TABLE 2A.1
Murder Cases - 2022-2024
SL State/UT 2022 2023 2024 Murder ng Rate
[1] [2] [3] [4] [5] [6] [7] [8]
STATES:
1 Andhra Pradesh 925 922 898 534.0 1.7 92.9
12 Kerala 334 352 338 359.7 0.9 97.6
TOTAL STATE(S) 27838 27056 26383 13641.9 1.9 84.7
UNION TERRITORIES:
D&N Haveli and
31 16 20 11 13.9 0.8 93.8
Daman & Diu
34 Ladakh 5 2 1 3.0 0.3 -
TOTAL UT(S) 684 665 666 407.2 1.6 87.0
TOTAL ALL INDIA 28522 27721 27049 14049.1 1.9 84.7
+' Crime Rate is calculated as Crime per one lakh of population. TABLE 2A.1 Page 1 of 1
"""


def test_rows_handle_wrapped_names_dashes_and_totals():
    found = dict(ncrb.rows(MURDER))
    assert found["Andhra Pradesh"][-2:] == ["1.7", "92.9"]
    assert found["D&N Haveli and Daman & Diu"] == ["16", "20", "11", "13.9", "0.8", "93.8"]
    assert found["Ladakh"][-1] == "-"
    assert found["All India"][-2] == "1.9"
    assert not any(name.startswith("TOTAL") for name in found)


def test_crime_observations_read_rate_and_chargesheeting_columns(monkeypatch):
    monkeypatch.setattr(ncrb, "table_text", lambda pdf, wanted: {"2A.1": MURDER, "1A.1": MURDER})
    observations, problems = ncrb.observations({2024: {1: b""}}, REF.resolver())
    values = {(o.indicator_id, o.entity_slug): o.value for o in observations}
    assert values[("murder-rate", "keralam")] == 0.9
    assert values[("murder-rate", "dadra-and-nagar-haveli-and-daman-and-diu")] == 0.8
    assert values[("murder-rate", "india")] == 1.9
    assert values[("chargesheeting-rate", "andhra-pradesh")] == 92.9
    assert ("chargesheeting-rate", "ladakh") not in values  # "-" is no value
    assert all(o.period.label == "2024" for o in observations)
    # Missing tables and short tables are reported, not silently skipped.
    assert any("table 1A.3 not found" in p for p in problems)
    assert any("table 2A.1: only 5 rows read" in p for p in problems)


def test_duplicate_volume_urls_are_ignored():
    package = {
        "resources": [
            {"name": "Crime in India 2024 - Vol 1", "url": "https://x/vol1.pdf"},
            {"name": "Crime in India 2024 - Vol 2", "url": "https://x/vol2.pdf"},
            {"name": "Crime in India 2024 - Vol 3", "url": "https://x/vol2.pdf"},
            {"name": "Total Cases Registered 2022-2024", "url": "https://x/table_1.1.xlsx"},
        ]
    }
    assert ncrb._volumes(package) == {1: "https://x/vol1.pdf"}


FATALITIES = (
    "\ufeffSl No,State,2020 Killed,2021 Killed,2024 Killed,% change from 2023 to 2024\n"
    '26,Uttar Pradesh,"19,149","21,227","24,118",1.97\n'
    "33,J & K #,728,774,831,-6.94\n"
    "34,Ladakh,NA,56,61,3.39\n"
    'Total,All India,"1,38,383","1,53,972","1,77,175",2.48\n'
    ",,,,,\n"
    "# includes Ladakh for 2020,,,,,\n"
)


def test_road_deaths_use_mid_year_population():
    observations, problems = morth.observations(FATALITIES, 2024, REF.resolver(), population())
    assert problems == []
    values = {(o.entity_slug, o.period.label): o.value for o in observations}
    up = population()[("uttar-pradesh", 2024)].persons
    assert values[("uttar-pradesh", "2024")] == round(24118 / up * 100_000, 2)
    assert ("jammu-and-kashmir", "2020") not in values  # includes Ladakh
    assert ("jammu-and-kashmir", "2021") in values
    assert ("ladakh", "2020") not in values  # NA
    assert 12 < values[("india", "2024")] < 13.5


def test_population_reference_is_complete_and_consistent():
    pop = population()
    current = [e.slug for e in REF.entities if e.type in ("state", "ut") and e.valid_to is None]
    for year in (2020, 2024, 2036):
        missing = [slug for slug in current if (slug, year) not in pop]
        assert missing == []
        states = sum(pop[(slug, year)].persons for slug in current)
        assert abs(states - pop[("india", year)].persons) / pop[("india", year)].persons < 0.001
    # Boundary changes: parts summed for entities that existed then.
    assert ("andhra-pradesh-undivided", 2013) in pop and ("andhra-pradesh", 2013) not in pop
    assert ("jammu-and-kashmir-state", 2019) in pop and ("ladakh", 2019) not in pop
    assert ("dadra-and-nagar-haveli", 2019) in pop and ("dadra-and-nagar-haveli", 2020) not in pop
    # Matches the denominators NCRB prints (lakh, 2024).
    assert round(pop[("keralam", 2024)].persons / 1e5, 1) == 359.7
    assert round(pop[("uttar-pradesh", 2024)].persons / 1e5, 1) == 2388.8
    for p in pop.values():
        assert abs(p.persons - p.male - p.female) <= 3000


def test_adsi_rows_stop_at_the_all_india_total(monkeypatch):
    text = (
        "Table – 2.2\nIncidence and Rate of Suicides – 2024\n(State/UT - wise)\nSTATES\n"
        "12 KERALA 10865 6.4 359.67 30.2\n32 DELHI (UT) 2905 1.7 218.84 13.3\n"
        "TOTAL (ALL INDIA) 170746 100.0 14049.11 12.2\nNote: # – Report\n"
        "1 Agra 100 0.1 20.0 5.0\n"
    )

    class FakePdf:
        def __init__(self):
            self.pages = [type("P", (), {"extract_text": lambda self: text})()]

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(ncrb.pdfplumber, "open", lambda _: FakePdf())
    observations, problems = ncrb.adsi_observations({2024: b""}, REF.resolver())
    values = {o.entity_slug: o.value for o in observations}
    assert values == {"keralam": 30.2, "delhi": 13.3, "india": 12.2}
    assert problems == ["ADSI 2024: only 3 rows read"]
    assert date(2024, 1, 1) <= observations[0].period.start
