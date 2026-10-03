from datetime import date

import httpx
import pytest

from unnati import observations as obs
from unnati.connectors import mospi
from unnati.core.http import PoliteClient
from unnati.core.periods import fiscal_year
from unnati.db import scalar
from unnati.reference import load_reference
from unnati.runs import start_run
from unnati.seed import seed

REF = load_reference()
INDICATORS = {i.id: i for i in REF.indicators}
TODAY = date(2026, 10, 3)


def o(value, slug="keralam", year=2023, indicator="per-capita-nsdp-constant", provisional=False):
    return obs.Observation(indicator, slug, fiscal_year(year), value, is_provisional=provisional)


# --- validation ---------------------------------------------------------------------------------


def test_values_outside_the_valid_range_are_hard_errors():
    result = obs.validate([o(-5.0), o(5.0, indicator="no-such-thing")], INDICATORS, current_places=0)
    assert not result.ok
    assert any("below 0" in line for line in result.hard)
    assert any("unknown indicator" in line for line in result.hard)


def test_duplicates_and_non_numbers_are_hard_errors():
    result = obs.validate([o(1.0), o(2.0), o(float("nan"), slug="goa")], INDICATORS, current_places=0)
    assert any("duplicate" in line for line in result.hard)
    assert any("not a number" in line for line in result.hard)


def test_thin_coverage_is_only_a_note():
    types = {e.slug: e.type for e in REF.entities}
    result = obs.validate([o(100.0), o(200.0, slug="goa")], INDICATORS, current_places=36, entity_types=types)
    assert result.ok and "only 2 states/UTs" in result.soft[0]


# --- loading with vintages ------------------------------------------------------------------------


def test_only_new_and_revised_values_are_written(db):
    seed(db, REF)
    first = obs.load(db, [o(100.0), o(200.0, slug="goa")], start_run(db, "mospi_nas_state"))
    assert first == {"received": 2, "new": 2, "revised": 0, "unchanged": 0}

    second = obs.load(db, [o(100.0), o(250.0, slug="goa")], start_run(db, "mospi_nas_state"))
    assert second == {"received": 2, "new": 0, "revised": 1, "unchanged": 1}
    assert scalar(db, "select count(*) from observation") == 3  # the revision is kept, not overwritten
    latest = scalar(
        db,
        """select value from latest_observation lo join entity e on e.id = lo.entity_id
           where e.slug = 'goa'""",
    )
    assert latest == 250.0


def test_a_provisional_value_becoming_final_is_a_revision(db):
    seed(db, REF)
    obs.load(db, [o(100.0, provisional=True)], start_run(db, "mospi_nas_state"))
    counts = obs.load(db, [o(100.0, provisional=False)], start_run(db, "mospi_nas_state"))
    assert counts["revised"] == 1


def test_unknown_entities_roll_the_whole_batch_back(db):
    seed(db, REF)
    with pytest.raises(ValueError, match="missing from the database"):
        obs.load(db, [o(1.0), o(2.0, slug="atlantis")], start_run(db, "mospi_nas_state"))
    assert scalar(db, "select count(*) from observation") == 0


# --- MoSPI connector ------------------------------------------------------------------------------


def test_fetch_all_follows_pages():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        calls.append((page, request.url.params["limit"]))
        return httpx.Response(200, json={"data": [{"n": page}], "meta_data": {"page": page, "totalPages": 3}})

    with PoliteClient(min_interval=0, transport=httpx.MockTransport(handler)) as http:
        rows = mospi.fetch_all(http, "/api/nas/getNASData", {"indicator_code": 25})
    assert [r["n"] for r in rows] == [1, 2, 3] and calls[0] == (1, "200")


def test_fetch_all_raises_api_errors():
    def handler(request):
        return httpx.Response(200, json={"success": False, "message": "Limit cannot be greater than 200"})

    with (
        PoliteClient(min_interval=0, transport=httpx.MockTransport(handler)) as http,
        pytest.raises(RuntimeError, match="Limit"),
    ):
        mospi.fetch_all(http, "/x", {})


def nas_row(state, year, constant, current="1"):
    return {"state": state, "year": year, "constant_price": constant, "current_price": current}


def test_nas_uses_current_boundaries_and_marks_recent_years_provisional():
    rows = {
        25: [
            nas_row("Andhra Pradesh", "2012-13", "80000"),
            nas_row("Telangana", "2012-13", "90000"),
            nas_row("Kerala", "2024-25", "150000"),
            nas_row("Jammu & Kashmir", "2017-18", "60000"),
            nas_row("Goa", "2020-21", None, None),
        ]
    }
    found, problems = mospi.nas_observations(rows, REF.resolver(), TODAY)
    per_capita = {
        (x.entity_slug, x.period.label): x for x in found if x.indicator_id == "per-capita-nsdp-constant"
    }
    assert not problems
    # MoSPI back-casts: 2012-13 "Andhra Pradesh" is today's state, not undivided AP.
    assert ("andhra-pradesh", "2012-13") in per_capita and ("telangana", "2012-13") in per_capita
    assert per_capita[("keralam", "2024-25")].is_provisional
    assert not per_capita[("andhra-pradesh", "2012-13")].is_provisional
    assert "likely include Ladakh" in per_capita[("jammu-and-kashmir", "2017-18")].note
    assert not [x for x in found if x.entity_slug == "goa"]  # missing values are skipped
