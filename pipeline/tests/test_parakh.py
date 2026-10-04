import pytest

from unnati.connectors import parakh

UT_PAGE = "\n".join(
    [
        "GRADE 6 UT Report: Chandigarh",
        "Comparison of UT Average with National Average Across Subjects",
        "68%",
        "Language",
        "57%",
        "54%",
        "Mathematics",
        "46%",
        "57%",
        "The World",
        "gap is 11% in Language,",
        "8% in Mathematics, and",
    ]
)


class _Page:
    def __init__(self, text):
        self.text = text

    def extract_text(self):
        return self.text


class _Pdf:
    def __init__(self, text):
        self.pages = [_Page("GRADE 3 State Report"), _Page(text)]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_reads_grade6_maths_for_states_and_uts(monkeypatch):
    monkeypatch.setattr(parakh.pdfplumber, "open", lambda _: _Pdf(UT_PAGE))
    assert parakh.grade6_maths(b"") == (54.0, 46.0)
    state_page = UT_PAGE.replace("UT Average", "State Average")
    monkeypatch.setattr(parakh.pdfplumber, "open", lambda _: _Pdf(state_page))
    assert parakh.grade6_maths(b"") == (54.0, 46.0)


def test_refuses_values_that_contradict_the_stated_gap(monkeypatch):
    wrong = UT_PAGE.replace("8% in Mathematics", "20% in Mathematics")
    monkeypatch.setattr(parakh.pdfplumber, "open", lambda _: _Pdf(wrong))
    with pytest.raises(ValueError):
        parakh.grade6_maths(b"")


def test_observations_add_the_national_average(monkeypatch):
    monkeypatch.setattr(parakh, "grade6_maths", lambda _: (62.0, 46.0))
    found, problems = parakh.observations({"punjab": b""})
    assert {(o.entity_slug, o.value) for o in found} == {("punjab", 62.0), ("india", 46.0)}
    assert problems == []
