from unnati.connectors import nfhs_factsheets as nf
from unnati.reference import load_reference

REF = load_reference()

PAGE = """Ha ryana - Key Indicators
NFHS-6 NFHS-5
Indicators (2023-24) (2019-21)
4. Population living in households with electricity (%) 99.8 99.6 99.7 99.6
16. Women age 20-24 years married before age 18 years (%) 2.2 3.6 (2.9) 6.3
44. Children age 12-23 months fully vaccinated based on information from either vaccination card
85.8 84.1 84.9 78.4
or mother's recall6 (%)
69. Children under 5 years who are stunted (height-for-age)12 (%) * * * 23.4
"""


def test_items_handle_wrapped_labels_footnotes_and_brackets():
    found = dict(nf.items(PAGE))
    assert found["Population living in households with electricity (%)"] == ["99.8", "99.6", "99.7", "99.6"]
    assert found[
        "Children age 12-23 months fully vaccinated based on information from either vaccination card"
        " or mother's recall (%)"
    ] == ["85.8", "84.1", "84.9", "78.4"]
    assert found["Women age 20-24 years married before age 18 years (%)"][2] == "(2.9)"


def test_headers_with_stray_spaces_resolve():
    assert nf.resolve_header(REF.resolver(), "Ha ryana").slug == "haryana"
    assert nf.resolve_header(REF.resolver(), "Tam il Nadu").slug == "tamil-nadu"


def test_observations_take_the_nfhs6_total_and_csvs_win():
    csv_text = (
        "Indicator_No,Indicator,NFHS6_Urban,NFHS6_Rural,NFHS6_Total,NFHS5_Total\n"
        "4,Population living in households with electricity (%),99,98,98.5,97.8\n"
    )
    pages = {"Ha ryana": PAGE}
    original = nf.state_pages
    nf.state_pages = lambda _: pages
    try:
        found, problems = nf.observations(b"", {"Haryana": csv_text}, REF.resolver())
    finally:
        nf.state_pages = original
    values = {o.indicator_id: (o.value, o.note) for o in found}
    assert values["households-with-electricity"][0] == 98.5  # the CSV wins
    assert values["full-immunisation"][0] == 84.9
    assert "stunting-under5" not in values  # "*": not shown in the source
    assert "25-49 unweighted cases" in values["child-marriage"][1]
    assert any("stunting-under5" in p for p in problems)
