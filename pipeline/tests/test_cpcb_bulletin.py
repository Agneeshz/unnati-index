from datetime import date

from unnati.connectors import cpcb_bulletin as cb


def test_states_average_their_cities_and_india_averages_all(monkeypatch):
    readings = [
        cb.CityReading("Delhi", 166, "Moderate", "PM 10", "44/46"),
        cb.CityReading("Agra", 109, "Moderate", "PM 10", "5/6"),
        cb.CityReading("Gorakhpur", 91, "Satisfactory", "PM 10", "1/1"),
        cb.CityReading("Nowhere Town", 50, "Good", "PM 10", "1/1"),
    ]
    monkeypatch.setattr(cb, "parse", lambda _: readings)
    found, problems = cb.observations({date(2026, 10, 1): b""})
    values = {o.entity_slug: o for o in found}
    assert values["delhi"].value == 166
    assert values["uttar-pradesh"].value == 100  # (109 + 91) / 2
    assert "highest Agra 109" in values["uttar-pradesh"].note
    assert values["india"].value == 104  # all four cities, including the unmapped one
    assert values["delhi"].period.label == "2026-10-01"
    assert problems == ["CPCB bulletin: city 'Nowhere Town' has no state in cpcb_cities.csv"]


def test_every_mapped_state_is_a_current_entity():
    from unnati.reference import load_reference

    current = {e.slug for e in load_reference().entities if e.valid_to is None}
    assert set(cb.city_states().values()) <= current
