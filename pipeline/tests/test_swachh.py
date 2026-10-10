from unnati.connectors import swachh
from unnati.reference import city_lookup, load_reference

PAGE = """Ranking of Million Plus Cities based on total score
Rank State/ UT Name ULB Name Total Score (12500)
1 GUJARAT AHMEDABAD 12079 9579 1300 1200
GVMC
9 ANDHRA PRADESH 11636 9336 1100 1200
VISAKHAPATNAM
10 UTTAR PRADESH AGRA (M. Corp) 11532 9232 1100 1200
MUNICIPAL
31 DELHI CORPORATION OF 7920 7080 500 1200
DELHI
39 PUNJAB LUDHIANA 5272 5542 0 750
"""


def test_rows_rejoin_names_that_wrap_around_the_numbers():
    rows = list(swachh.page_rows(PAGE, load_reference().resolver()))
    assert [(s, b, v) for s, b, v in rows] == [
        ("gujarat", "AHMEDABAD", 12079.0),
        ("andhra-pradesh", "GVMC VISAKHAPATNAM", 11636.0),
        ("uttar-pradesh", "AGRA (M. Corp)", 11532.0),
        ("delhi", "MUNICIPAL CORPORATION OF DELHI", 7920.0),
        ("punjab", "LUDHIANA", 5272.0),  # the published total, though its parts add to 6,292
    ]


def test_body_names_map_to_cities():
    lookup = city_lookup()
    for state, body, city in [
        ("andhra-pradesh", "GVMC VISAKHAPATNAM", "visakhapatnam"),
        ("uttar-pradesh", "AGRA (M. Corp)", "agra"),
        ("delhi", "MUNICIPAL CORPORATION OF DELHI", "delhi-city"),
        ("keralam", "THIRUVANANTHAPUR AM", "thiruvananthapuram"),
        ("maharashtra", "GREATER MUMBAI", "mumbai"),
    ]:
        assert lookup.get((state, swachh._clean(body))) == city, body
