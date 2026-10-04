from unnati.connectors import parakh

GRADE6 = "\n".join(
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
        "Around Us",
        "49%",
        "Chandigarh National",
        "In Language, ...",
    ]
)


def test_comparison_reads_every_subject_including_wrapped_names():
    assert parakh.comparison(GRADE6) == {
        "Language": (68.0, 57.0),
        "Mathematics": (54.0, 46.0),
        "The World Around Us": (57.0, 49.0),
    }
    assert parakh.comparison(GRADE6.replace("Comparison of", "Something else")) == {}


def test_observations_average_subjects_then_grades(monkeypatch):
    grades = {
        3: {"Language": (80.0, 64.0), "Mathematics": (70.0, 60.0)},
        6: {"Language": (60.0, 57.0), "Mathematics": (50.0, 46.0), "The World Around Us": (55.0, 49.0)},
        9: {
            "Language": (60.0, 54.0),
            "Mathematics": (40.0, 37.0),
            "Science": (50.0, 40.0),
            "Social Science": (50.0, 40.0),
        },
    }
    monkeypatch.setattr(parakh, "grades", lambda _: grades)
    found, problems = parakh.observations({"punjab": b""})
    values = {(o.indicator_id, o.entity_slug): o.value for o in found}
    assert values[("parakh-grade3", "punjab")] == 75
    assert values[("parakh-grade6", "punjab")] == 55
    assert values[("parakh-grade9", "punjab")] == 50
    assert values[("parakh-learning", "punjab")] == 60
    assert values[("parakh-grade6-maths", "punjab")] == 50
    assert values[("parakh-grade6-maths", "india")] == 46
    assert problems == []


def test_reports_missing_grades(monkeypatch):
    monkeypatch.setattr(parakh, "grades", lambda _: {6: {}})
    found, problems = parakh.observations({"punjab": b""})
    assert found == [] and problems == ["PARAKH punjab: grade 3, 9 chart not read"]
