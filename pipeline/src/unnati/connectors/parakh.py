"""PARAKH Rashtriya Sarvekshan 2024 (4 Dec 2024): average Grade 6 mathematics performance by
state, from NCERT's official state reports.

Each state has a report at parakh.ncert.gov.in/sites/default/files/2025-07/
REPORT_<State name>_IND<3-digit state code>.pdf (the listing page blocks automated access, but
the files do not). Its Grade 6 page compares the state's average performance (the average
percentage of questions answered correctly) with the national average in each subject. The
value is read from that chart's text and checked against the report's own sentence, e.g. "The
performance gap is 16% in ... Mathematics". No report has been found for DNH & DD."""

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

_PCT = re.compile(r"^(\d{1,3})%$")


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


def grade6_maths(pdf_bytes: bytes) -> tuple[float, float] | None:
    """(state average, national average) for Grade 6 mathematics, or None if not found."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            # States say "State Average", UTs "UT Average".
            if "GRADE 6" not in text or not re.search(r"Comparison of (State|UT) Average with National", text):
                continue
            lines = [line.strip() for line in text.split("\n")]
            for i, line in enumerate(lines):
                if line == "Mathematics" and 0 < i < len(lines) - 1:
                    before, after = _PCT.match(lines[i - 1]), _PCT.match(lines[i + 1])
                    if before and after:
                        state, national = float(before.group(1)), float(after.group(1))
                        gap = re.search(r"([\d.]+)%\s+in\s+(?:[A-Za-z ,]*?)Mathematics", " ".join(lines))
                        if gap and abs(abs(state - national) - float(gap.group(1))) > 1:
                            message = f"Grade 6 maths {state} vs {national} disagrees with the stated gap"
                            raise ValueError(message)
                        return state, national
    return None


def observations(reports: dict[str, bytes]) -> tuple[list[Observation], list[str]]:
    out: list[Observation] = []
    problems: list[str] = []
    national: float | None = None
    for slug, pdf in sorted(reports.items()):
        try:
            found = grade6_maths(pdf)
        except ValueError as err:
            problems.append(f"PARAKH {slug}: {err}")
            continue
        if found is None:
            problems.append(f"PARAKH {slug}: Grade 6 comparison page not found")
            continue
        state, national = found
        note = "PARAKH Rashtriya Sarvekshan 2024 state report: Grade 6 maths, average % of questions correct"
        out.append(Observation("parakh-grade6-maths", slug, ROUND, state, note=note))
    if national is not None:
        note = "PARAKH Rashtriya Sarvekshan 2024: national average, Grade 6 maths"
        out.append(Observation("parakh-grade6-maths", "india", ROUND, national, note=note))
    return out, problems
