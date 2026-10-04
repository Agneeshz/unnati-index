from datetime import date

from unnati.connectors import aai, mospi
from unnati.reference import Population, load_reference


def _vehicles(year: str, state: str, transport: str, other: str) -> list[dict]:
    row = {"year": year, "state": state, "indicator": "Status of registered Motor Vehicles"}
    return [
        {**row, "sub_indicator": "Transport", "value": transport},
        {**row, "sub_indicator": "Non-Transport", "value": other},
    ]


def test_vehicles_per_1000_sums_both_kinds_and_skips_premerger_combined_name():
    rows = {
        mospi.ENV_VEHICLES: [
            *_vehicles("2022(P)", "Delhi", "1000", "9000"),
            *_vehicles("2022(P)", "Daman and Diu and Dadra Nagar Haveli", "100", "900"),
            *_vehicles("2018", "Daman and Diu and Dadra Nagar Haveli", "10", "90"),
        ]
    }
    population = {
        ("delhi", 2022): Population(20_000, 10_000, 10_000),
        ("dadra-and-nagar-haveli-and-daman-and-diu", 2022): Population(1_000, 500, 500),
    }
    found, problems = mospi.envstats_observations(rows, load_reference().resolver(), population)
    values = {(o.entity_slug, o.period.start.year): o.value for o in found}
    assert values == {("delhi", 2022): 500, ("dadra-and-nagar-haveli-and-daman-and-diu", 2022): 1000}
    assert problems == []


def test_air_passengers_scale_fiscal_year_to_date_to_a_year():
    population = {
        ("goa", 2026): Population(1_000_000, 500_000, 500_000),
        ("india", 2026): Population(10_000_000, 5_000_000, 5_000_000),
    }
    by_airport = {"GOA (DABOLIM)": 1_000_000, "GOA (MOPA)": 1_000_000, "NOWHERE": 5}
    found, problems = aai.observations(by_airport, date(2026, 8, 31), population)
    values = {o.entity_slug: o.value for o in found}
    # 2,000,000 in five months (Apr-Aug) -> 4.8 million a year, per 100 of 1 million people.
    assert values["goa"] == 480.0
    assert found[0].period.label == "Apr–Aug 2026 (FY 2026-27 to date)"
    assert problems == ["AAI: airport 'NOWHERE' has no state in aai_airports.csv"]
