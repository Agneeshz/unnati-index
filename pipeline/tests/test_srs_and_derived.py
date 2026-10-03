from datetime import date

from unnati.connectors import mospi, srs, srs_bulletins
from unnati.core.periods import fiscal_year
from unnati.observations import Observation
from unnati.reference import load_reference

REF = load_reference()

SRB = """Table 16: Sex Ratio at Birth (female per 1000 male) by Residence, 2018-20 to 2022-24
India & Total Rural Urban
bigger States/UTs 2018-20 2019-21 2020-22 2021-23 2022-24 2018-20 2019-21 2020-22
India 907 913 914 917 918 907 912 912 914 914 910 918
Kerala 974 962 970 971 974 973 962 971 974 976 975 962
"""

IMR = """Table 14: Annual Estimates of Infant Mortality Rate by Sex, 2019-24
bigger States/UTs 2019 2020 2021 2022 2023 2024 2019 2020 2021 2022 2023 2024
India 30 28 27 26 25 24 30 28 27 27 26 24
Kerala 6 6 6 7 5 8 6 10 6 9 9 7
"""

IMR_SMALL = """Statement 46
Infant Mortality Rate by Sex and Residence, India and States/UTs, 2024
Kerala 8 7 9 5 5 6 10 8 11
Smaller States*
Manipur 2 2 3
Nagaland 12 15 10 Infant Mortality Rates for smaller States and Union
Union Territories*
Dadra & Nagar Haveli and D&D 9 13 3
"""


def test_period_header_skips_the_title_line():
    periods = srs.column_periods(SRB)
    assert [p.label for p in periods] == ["2018-20", "2019-21", "2020-22", "2021-23", "2022-24"]
    assert periods[0].start == date(2018, 1, 1) and periods[-1].end == date(2024, 12, 31)


def test_rows_ignore_trailing_text():
    rows = dict(srs.rows(IMR_SMALL))
    assert rows["Nagaland"] == ["12", "15", "10"]
    assert rows["Dadra & Nagar Haveli and D&D"] == ["9", "13", "3"]


def test_observations_read_the_total_block(monkeypatch):
    tables = {
        "Table 14": IMR,
        "Table 15": IMR.replace("Infant Mortality Rate", "Total Fertility Rate"),
        "Table 16": SRB,
        "Statement 46": IMR_SMALL,
        "Statement 53": "Statement 53\nIndia 28 28 28 32 31 32 19 20 18\n",
    }
    monkeypatch.setattr(srs, "pages", lambda _: [])
    monkeypatch.setattr(srs, "find", lambda texts, heading: tables[heading])
    found, _ = srs.observations(b"", 2024, REF.resolver())

    def values(indicator_id):
        return {(o.entity_slug, o.period.label): o.value for o in found if o.indicator_id == indicator_id}

    assert values("sex-ratio-at-birth")[("india", "2022-24")] == 918
    assert values("sex-ratio-at-birth")[("keralam", "2018-20")] == 974
    imr = values("infant-mortality-rate")
    assert imr[("keralam", "2024")] == 8 and imr[("india", "2019")] == 30
    pooled = {slug for slug, label in imr if label == "2022-24"}
    assert pooled == {"manipur", "nagaland", "dadra-and-nagar-haveli-and-daman-and-diu"}
    assert values("under5-mortality-rate") == {("india", "2024"): 28}


MMR_PAGE = """Table 1: Maternal Mortality Ratio (MMR), Maternal Mortality Rate and Life
India & Major States MMR 95% CI Mortality
INDIA 87 (78,95) 5 0.18%
Kerala 24 (0,50) 1 0.04%
SOUTH SUBTOTAL 41 (27,55) 2 0.07%
Other states 84 (62,107) 4 0.14%
"""

LIFE_PAGE = """11. Statement 3 below gives the estimates of life expectancy at birth by sex and residence
Statement 3
Expectation of life at birth by Sex and Residence, India and bigger
States/UTs, 2020-24
India* 70.6 68.7 72.8 69.4 67.4 71.8 73.2 71.6 75.1
Kerala 75.6 72.5 78.7 76.2 72.9 79.4 75.0 72.0 78.0
"""


def test_bulletin_rows():
    assert list(srs_bulletins.mmr_rows([MMR_PAGE])) == [("INDIA", 87, 78, 95), ("Kerala", 24, 0, 50)]
    assert list(
        srs_bulletins.life_rows(["Expectation of life at birth by sex and residence\n", LIFE_PAGE])
    ) == [
        ("India", 70.6),
        ("Kerala", 75.6),
    ]
    assert srs_bulletins._period("2020", "2024").label == "2020-24"
    assert srs_bulletins._period("2022", "24").end == date(2024, 12, 31)


def test_three_year_growth_needs_consecutive_years():
    def growth(year, value, provisional=False):
        return Observation(
            "gsdp-growth-real", "keralam", fiscal_year(year), value, is_provisional=provisional
        )

    series = [growth(2019, 1.0), growth(2021, 11.8), growth(2022, 5.7), growth(2023, 6.7, True)]
    out = mospi.three_year_growth(series)
    assert len(out) == 1  # 2019-20 to 2021-22 skips the missing 2020-21
    assert out[0].value == 8.07 and out[0].is_provisional
    assert out[0].period.label == "2021-22 to 2023-24"


def test_hces_gini_takes_headline_series_and_averages():
    rows = [
        {
            "year": "2023-24",
            "state": "Kerala",
            "sector": sector,
            "imputation_type": imputation,
            "value": value,
        }
        for sector, imputation, value in (
            ("Rural", "Without Imputation", "0.300"),
            ("Rural", "With Imputation", "0.290"),
            ("Urban", "Without Imputation", "0.320"),
        )
    ]
    found, problems = mospi.hces_observations(rows, REF.resolver())
    values = {o.indicator_id: o.value for o in found}
    assert values == {"consumption-gini-rural": 0.3, "consumption-gini-urban": 0.32, "consumption-gini": 0.31}
    assert found[0].period.start == date(2023, 8, 1) and problems == []
