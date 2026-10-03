import pytest

from unnati.core.entities import (
    AmbiguousEntityError,
    Entity,
    EntityResolver,
    UnknownEntityError,
    normalize_name,
)
from unnati.core.periods import calendar_year, fiscal_year
from unnati.reference import load_reference


@pytest.fixture(scope="module")
def resolver() -> EntityResolver:
    return load_reference().resolver()


def slug(resolver, name, period):
    entity = resolver.resolve(name, period)
    return None if entity is None else entity.slug


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Andaman & Nicobar Islands", "andaman and nicobar islands"),
        ("  Jammu   &  Kashmir* ", "jammu and kashmir"),
        ("Andhra Pradesh¹", "andhra pradesh"),
        ("The Dadra and Nagar Haveli and Daman and Diu", "dadra and nagar haveli and daman and diu"),
        ("NCT of Delhi", "nct of delhi"),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Orissa", "odisha"),
        ("Pondicherry", "puducherry"),
        ("Uttaranchal", "uttarakhand"),
        ("NCT of Delhi", "delhi"),
        ("A & N Islands", "andaman-and-nicobar-islands"),
        ("Tamilnadu", "tamil-nadu"),
        ("All India", "india"),
        ("INDIA", "india"),
    ],
)
def test_common_source_spellings(resolver, name, expected):
    assert slug(resolver, name, calendar_year(2024)) == expected


def test_aggregate_rows_are_skipped(resolver):
    assert resolver.resolve("Total (States)", calendar_year(2024)) is None
    assert resolver.resolve("Total UTs", calendar_year(2024)) is None


def test_andhra_pradesh_before_and_after_the_2014_split(resolver):
    assert slug(resolver, "Andhra Pradesh", fiscal_year(2012)) == "andhra-pradesh-undivided"
    # FY 2014-15 straddles the 2 June 2014 split; its midpoint falls after it.
    assert slug(resolver, "Andhra Pradesh", fiscal_year(2014)) == "andhra-pradesh"
    assert slug(resolver, "Andhra Pradesh", calendar_year(2024)) == "andhra-pradesh"


def test_telangana_did_not_exist_before_2014(resolver):
    with pytest.raises(UnknownEntityError, match="none is valid"):
        resolver.resolve("Telangana", fiscal_year(2012))


def test_jammu_and_kashmir_state_then_ut(resolver):
    assert slug(resolver, "Jammu & Kashmir", calendar_year(2018)) == "jammu-and-kashmir-state"
    assert slug(resolver, "J&K", calendar_year(2019)) == "jammu-and-kashmir-state"
    assert slug(resolver, "Jammu & Kashmir", calendar_year(2020)) == "jammu-and-kashmir"
    assert slug(resolver, "Jammu and Kashmir (UT)", calendar_year(2024)) == "jammu-and-kashmir"
    with pytest.raises(UnknownEntityError):
        resolver.resolve("Ladakh", calendar_year(2018))
    assert slug(resolver, "Ladakh", calendar_year(2020)) == "ladakh"


def test_dnh_and_dd_merger(resolver):
    assert slug(resolver, "Dadra & Nagar Haveli", calendar_year(2018)) == "dadra-and-nagar-haveli"
    assert slug(resolver, "Daman & Diu", calendar_year(2018)) == "daman-and-diu"
    assert slug(resolver, "DNH & DD", calendar_year(2021)) == "dadra-and-nagar-haveli-and-daman-and-diu"
    # The old name alone is not silently mapped onto the merged UT.
    with pytest.raises(UnknownEntityError):
        resolver.resolve("Dadra & Nagar Haveli", calendar_year(2021))


def test_unknown_names_are_errors_not_guesses(resolver):
    with pytest.raises(UnknownEntityError, match="unknown place name"):
        resolver.resolve("Atlantis", calendar_year(2024))


def test_type_filter_excludes_other_levels(resolver):
    with pytest.raises(UnknownEntityError):
        resolver.resolve("Kerala", calendar_year(2024), types=frozenset({"city"}))


def test_ambiguity_is_reported():
    a = Entity(slug="a", name="Same Name", type="state")
    b = Entity(slug="b", name="Same Name", type="state")
    with pytest.raises(AmbiguousEntityError):
        EntityResolver([a, b]).resolve("Same Name", calendar_year(2024))
