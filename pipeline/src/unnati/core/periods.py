"""Reporting periods used by Indian statistics: calendar years, fiscal years (April–March),
fiscal quarters and months. Every observation is stored with a start date, end date and a
human label, so data of different frequencies can be compared and aligned."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

PERIOD_TYPES = (
    "day",
    "month",
    "quarter",
    "fiscal_year",
    "calendar_year",
    "survey_round",
    "multi_year",
)


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label: str
    type: str

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"period end {self.end} is before start {self.start}")
        if self.type not in PERIOD_TYPES:
            raise ValueError(f"unknown period type {self.type!r}")

    @property
    def midpoint(self) -> date:
        return self.start + (self.end - self.start) / 2


def calendar_year(year: int) -> Period:
    return Period(date(year, 1, 1), date(year, 12, 31), str(year), "calendar_year")


def fiscal_year(start_year: int) -> Period:
    """Indian fiscal year starting 1 April of ``start_year``, labelled e.g. ``2023-24``."""
    return Period(
        date(start_year, 4, 1),
        date(start_year + 1, 3, 31),
        f"{start_year}-{(start_year + 1) % 100:02d}",
        "fiscal_year",
    )


def fiscal_quarter(fy_start_year: int, quarter: int) -> Period:
    """Quarter ``1``–``4`` of a fiscal year; Q1 is April–June."""
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"quarter must be 1-4, got {quarter}")
    first_month = 4 + 3 * (quarter - 1)
    year = fy_start_year + (first_month - 1) // 12
    first_month = (first_month - 1) % 12 + 1
    last_month = first_month + 2
    end = date(year, last_month, calendar.monthrange(year, last_month)[1])
    label = f"Q{quarter} {fiscal_year(fy_start_year).label}"
    return Period(date(year, first_month, 1), end, label, "quarter")


def month(year: int, month_number: int) -> Period:
    last_day = calendar.monthrange(year, month_number)[1]
    label = f"{calendar.month_abbr[month_number]} {year}"
    return Period(date(year, month_number, 1), date(year, month_number, last_day), label, "month")


def day(value: date) -> Period:
    return Period(value, value, value.isoformat(), "day")


def span(start: date, end: date, label: str, period_type: str = "multi_year") -> Period:
    """Arbitrary span, e.g. a survey round (NFHS-6: 2023-24) or a 3-year rolling window."""
    return Period(start, end, label, period_type)


_FY = re.compile(r"^(?:FY\s*)?(\d{4})\s*[-–/]\s*(\d{2}|\d{4})$", re.IGNORECASE)
_YEAR = re.compile(r"^\d{4}$")
_MONTH = re.compile(r"^([A-Za-z]{3,9})[\s\-,]+(\d{4})$")


def parse_period(text: str) -> Period:
    """Parse the common labels found in Indian statistical tables.

    ``"2023-24"``, ``"2023-2024"``, ``"FY 2023-24"`` → fiscal year;
    ``"2024"`` → calendar year; ``"Jun 2026"`` / ``"June, 2026"`` → month.
    """
    cleaned = text.strip().rstrip("*#").strip()
    if m := _FY.match(cleaned):
        start, end = int(m.group(1)), m.group(2)
        consecutive = int(end) == start + 1 if len(end) == 4 else int(end) == (start + 1) % 100
        if not consecutive:
            raise ValueError(f"{text!r} is not a single fiscal year")
        return fiscal_year(start)
    if _YEAR.match(cleaned):
        return calendar_year(int(cleaned))
    if m := _MONTH.match(cleaned):
        name = m.group(1)[:3].title()
        months = {abbr: i for i, abbr in enumerate(calendar.month_abbr) if abbr}
        if name in months:
            return month(int(m.group(2)), months[name])
    raise ValueError(f"unrecognised period label {text!r}")


def days_in(period: Period) -> int:
    return (period.end - period.start + timedelta(days=1)).days
