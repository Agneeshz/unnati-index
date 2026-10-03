from unnati.connectors import bprd, rbi_hsis, trai

TRAI_PAGE = """Table 1.41 : State/UT wise number of Internet Subscribers per 100 population
at the end of Mar-26
S.N. State(s)
1 Andhra Pradesh 18.55 20.93 39.48 56.01 101.60 73.50
23 Tamil Nadu incl. Chennai 19.93 47.80 67.73 57.20 111.93 87.33
Uttar Pradesh
26 71.50 81.17 152.67 38.96 136.50 62.82
(UPE+UPW)
Andaman & Nicobar
1 0.23 0.23 0.46 105.32 121.07 112.55
Islands
2 Chandigarh 0.04 1.49 1.53 - - 120.35
Dadar & Nagar Haweli
3 0.32 0.60 0.92 133.64 45.71 59.44
(incl. Daman & Diu)
Total 440.87 651.93 1092.79 48.31 126.80 76.59
"""


def test_trai_table_handles_wrapped_names_and_metro_notes():
    period, rows = trai.table(TRAI_PAGE)
    assert period.label == "Mar 2026"
    assert dict(rows) == {
        "Andhra Pradesh": 73.5,
        "Tamil Nadu": 87.33,
        "Uttar Pradesh": 62.82,
        "Andaman & Nicobar Islands": 112.55,
        "Chandigarh": 120.35,
        "Dadra & Nagar Haveli and Daman & Diu": 59.44,
        "All India": 76.59,
    }
    assert trai.table("some other page") is None


DOPO_PAGE = """TABLE 3.1.1 -- (CONTINUED...)
(1) (2) (9) (10) (11) (12) (13) (14)
4 Bihar 4,304 3,598 1,70,516 1,02,454 68,062 23,933
31 Dadra and Nagar Haveli 504 466 1,424 1,120 304 101
and Daman and Diu
35 Lakshadweep - - 321 249 72 26
All India 1,64,802 1,27,613 27,55,274 21,62,436 5,92,838 2,72,535
"""


def test_dopo_rows_read_total_sanctioned_and_actual():
    assert bprd.rows(DOPO_PAGE) == [
        ("Bihar", 170516, 102454),
        ("Dadra and Nagar Haveli and Daman and Diu", 1424, 1120),
        ("Lakshadweep", 321, 249),
        ("All India", 2755274, 2162436),
    ]


def test_rbi_index_parsing():
    page = (
        "Handbook of Statistics on Indian States 2024-25'>"
        "<a href=PublicationsView.aspx?id=23613>Table 164: State-wise Gross Fiscal Deficit</a></td>"
        "<td nowrap><a href='https://rbidocs.rbi.org.in/rdocs/Publications/DOCs/164T_ABC.XLSX'>XLSX</a>"
    )
    assert rbi_hsis.edition_of(page) == "2024-25"
    [table] = rbi_hsis.listed_tables(page)
    assert (table.number, table.url.endswith("164T_ABC.XLSX")) == (164, True)
