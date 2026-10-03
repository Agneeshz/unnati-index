from datetime import date

import pytest

from unnati.core.periods import calendar_year, fiscal_quarter, fiscal_year, month, parse_period


def test_fiscal_year_runs_april_to_march():
    fy = fiscal_year(2023)
    assert (fy.start, fy.end, fy.label) == (date(2023, 4, 1), date(2024, 3, 31), "2023-24")


def test_fiscal_year_label_across_century():
    assert fiscal_year(2099).label == "2099-00"


def test_fiscal_quarters():
    assert fiscal_quarter(2026, 1).start == date(2026, 4, 1)
    assert fiscal_quarter(2026, 1).end == date(2026, 6, 30)
    q4 = fiscal_quarter(2026, 4)
    assert (q4.start, q4.end, q4.label) == (date(2027, 1, 1), date(2027, 3, 31), "Q4 2026-27")


def test_month_handles_leap_years():
    assert month(2028, 2).end == date(2028, 2, 29)
    assert month(2026, 6).label == "Jun 2026"


@pytest.mark.parametrize(
    "label, expected",
    [
        ("2023-24", fiscal_year(2023)),
        ("2023-2024", fiscal_year(2023)),
        ("FY 2023-24", fiscal_year(2023)),
        ("2023-24*", fiscal_year(2023)),
        ("1999-00", fiscal_year(1999)),
        ("2024", calendar_year(2024)),
        ("Jun 2026", month(2026, 6)),
        ("June, 2026", month(2026, 6)),
    ],
)
def test_parse_period(label, expected):
    assert parse_period(label) == expected


@pytest.mark.parametrize("label", ["2023-25", "Q1", "Smarch 2026", ""])
def test_parse_period_rejects_unknown_labels(label):
    with pytest.raises(ValueError):
        parse_period(label)


def test_midpoint():
    assert fiscal_year(2014).midpoint == date(2014, 9, 30)
