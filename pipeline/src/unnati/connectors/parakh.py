"""PARAKH Rashtriya Sarvekshan 2024 (4 Dec 2024): learning levels by state, from NCERT's official
state reports.

Each state has a report at parakh.ncert.gov.in/sites/default/files/2025-07/
REPORT_<State name>_IND<3-digit state code>.pdf (the listing page blocks automated access, but
the files do not). For each grade it compares the state's average performance (the average
percentage of questions answered correctly) with the national average in every subject:
Grade 3 (Language, Mathematics), Grade 6 (also The World Around Us) and Grade 9 (Language,
Mathematics, Science, Social Science). From these:

- parakh-grade3/6/9: the mean over that grade's subjects;
- parakh-learning: the mean of the three grade averages (used in the Education pillar);
- parakh-grade6-maths: Grade 6 mathematics on its own.

No report has been found for DNH & DD."""

from __future__ import annotations

import io
import re
from datetime import date
from urllib.parse import quote

import httpx
import pdfplumber

from unnati.core.http import PoliteClient
from unnati.core.periods import span
from unnati.observations import Observation

BASE = "https://parakh.ncert.gov.in/sites/default/files/2025-07/REPORT_{name}_IND{code:03d}.pdf"
ROUND = span(date(2024, 12, 4), date(2024, 12, 4), "PRS 2024", "survey_round")
# Names PARAKH uses where they differ from ours.
NAMES = {
    "keralam": ["Kerala"],
    "delhi": ["NCT of Delhi"],
    "jammu-and-kashmir": ["Jammu and Kashmir", "Jammu & Kashmir"],
}
SUBJECTS = {
    3: ("Language", "Mathematics"),
    6: ("Language", "Mathematics", "The World Around Us"),
    9: ("Language", "Mathematics", "Science", "Social Science"),
}

_PCT = re.compile(r"^(\d{1,3})%$")
_GRADE = re.compile(r"GRADE\s+(\d)\b")


def report_url(http: PoliteClient, slug: str, name: str, code: int) -> str | None:
    for candidate in dict.fromkeys([*NAMES.get(slug, []), name, name.replace(" and ", " & ")]):
        url = BASE.format(name=quote(candidate), code=code)
        try:
            if http.request("HEAD", url).status_code == 200:
                return url
        except httpx.HTTPStatusError as err:
            if err.response.status_code != 404:
                raise
    return None


def comparison(text: str) -> dict[str, tuple[float, float]]:
    """{subject: (state average, national average)} from one grade's comparison chart text:
    a state value, the subject name (one or two lines), then the national value."""
    lines = [line.strip() for line in text.split("\n")]
    start = next((i for i, line in enumerate(lines) if "Comparison of" in line), None)
    if start is None:
        return {}
    out: dict[str, tuple[float, float]] = {}
    pending: float | None = None
    label: list[str] = []
    for line in lines[start + 1 :]:
        pct = _PCT.match(line)
        if pct and pending is not None and label:
            out[" ".join(label)] = (pending, float(pct.group(1)))
            pending, label = None, []
        elif pct:
            pending = float(pct.group(1))
        elif pending is not None:
            label.append(line)
        else:
            break  # the legend ("<State> National") ends the chart
    return out


def grades(pdf_bytes: bytes) -> dict[int, dict[str, tuple[float, float]]]:
    """{grade: {subject: (state, national)}} for grades 3, 6 and 9."""
    out: dict[int, dict[str, tuple[float, float]]] = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            grade = _GRADE.search(text[:80])
            # States say "State Average", UTs "UT Average".
            if not grade or not re.search(r"Comparison of (State|UT) Average with National", text):
                continue
            g = int(grade.group(1))
            found = comparison(text)
            if g in SUBJECTS and set(found) == set(SUBJECTS[g]):
                out[g] = found
    return out


def grade6_maths(pdf_bytes: bytes) -> tuple[float, float] | None:
    """(state average, national average) for Grade 6 mathematics, or None if not found."""
    return grades(pdf_bytes).get(6, {}).get("Mathematics")


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 1)


def observations(reports: dict[str, bytes]) -> tuple[list[Observation], list[str]]:
    out: list[Observation] = []
    problems: list[str] = []
    national: dict[int, dict[str, tuple[float, float]]] = {}
    source = "PARAKH Rashtriya Sarvekshan 2024 state report"
    for slug, pdf in sorted(reports.items()):
        found = grades(pdf)
        missing = [g for g in SUBJECTS if g not in found]
        if missing:
            problems.append(f"PARAKH {slug}: grade {', '.join(map(str, missing))} chart not read")
            continue
        national = found
        for g, subjects in found.items():
            note = f"{source}: Grade {g}, mean of {', '.join(subjects)} (average % correct)"
            value = _mean([s for s, _ in subjects.values()])
            out.append(Observation(f"parakh-grade{g}", slug, ROUND, value, note=note))
        overall = _mean([_mean([s for s, _ in subjects.values()]) for subjects in found.values()])
        note = f"{source}: mean of the Grade 3, 6 and 9 averages"
        out.append(Observation("parakh-learning", slug, ROUND, overall, note=note))
        maths = found[6]["Mathematics"][0]
        note = f"{source}: Grade 6 mathematics"
        out.append(Observation("parakh-grade6-maths", slug, ROUND, maths, note=note))
    if national:  # every report repeats the national averages
        note = "PARAKH Rashtriya Sarvekshan 2024: national average"
        for g, subjects in national.items():
            value = _mean([n for _, n in subjects.values()])
            out.append(Observation(f"parakh-grade{g}", "india", ROUND, value, note=note))
        overall = _mean([_mean([n for _, n in subjects.values()]) for subjects in national.values()])
        out.append(Observation("parakh-learning", "india", ROUND, overall, note=note))
        maths = national[6]["Mathematics"][1]
        out.append(Observation("parakh-grade6-maths", "india", ROUND, maths, note=note))
    return out, problems
