"""PARAKH Rashtriya Sarvekshan 2024 (4 Dec 2024): share of Grade 6 students at "Proficient" or
"Advanced" level in mathematics, by state.

NCERT's state report pages block automated access and the dashboard loads figures in the
browser, so the state table is curated in `manual/parakh_prs2024_g6_maths.csv`. It was
transcribed from the PRS 2024 state tables as republished by Education for All in India
("Table 2: State / UT-wise Proficient Total (%)", G6 Math) and is marked as pending a check
against NCERT's own report; replace the file when NCERT's tables can be downloaded."""

from __future__ import annotations

import csv
from datetime import date
from importlib.resources import files

from unnati.core.entities import EntityResolver, UnknownEntityError
from unnati.core.periods import span
from unnati.observations import Observation

SOURCE_URL = (
    "https://educationforallinindia.com/"
    "proficiency-levels-in-indian-school-education-insights-from-parakh-rashtriya-sarvekshan-2024/"
)
ROUND = span(date(2024, 12, 4), date(2024, 12, 4), "PRS 2024", "survey_round")


def rows() -> list[tuple[str, float]]:
    path = files("unnati.manual").joinpath("parakh_prs2024_g6_maths.csv")
    with path.open(encoding="utf-8", newline="") as fh:
        return [(r["place"], float(r["proficient_pct"])) for r in csv.DictReader(fh)]


def observations(resolver: EntityResolver) -> tuple[list[Observation], list[str]]:
    out: list[Observation] = []
    problems: list[str] = []
    for place, value in rows():
        try:
            entity = resolver.resolve(place, ROUND)
        except UnknownEntityError as err:
            problems.append(str(err))
            continue
        if entity is not None:
            note = (
                "PARAKH Rashtriya Sarvekshan 2024, Grade 6 maths, Proficient + Advanced"
                " (transcribed; pending NCERT check)"
            )
            out.append(Observation("parakh-grade6-maths", entity.slug, ROUND, value, note=note))
    return out, problems
