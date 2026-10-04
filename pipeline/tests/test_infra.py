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


def test_density_per_area_skips_old_years_carried_cells_and_places_without_area(tmp_path):
    import openpyxl

    from unnati.connectors import rbi_hsis

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append([None, "TABLE 144: STATE-WISE LENGTH OF NATIONAL HIGHWAYS"])
    ws.append([None, "State/Union Territory", 2014, 2021, "2024*"])
    ws.append([None, "Kerala", 1000, 1500, "2000"])
    ws.append([None, "Goa", 100, "200*", 300])
    ws.append([None, "Jammu & Kashmir", 1, 2, 3])
    path = tmp_path / "144T.xlsx"
    wb.save(path)
    b = rbi_hsis._Builder("2024-25", load_reference().resolver())
    area = {"keralam": 40_000.0, "goa": 3_000.0}
    rbi_hsis._densities(b, path, 144, "national-highway-density", 1000, "national highways", area)
    found = {(o.entity_slug, o.period.label): o.value for o in b.out}
    # end-March 2021 closes FY 2020-21; the end-December 2024 figure falls in FY 2024-25.
    assert found == {("keralam", "2020-21"): 37.5, ("keralam", "2024-25"): 50.0, ("goa", "2024-25"): 100.0}
