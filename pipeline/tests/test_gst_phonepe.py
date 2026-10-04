from datetime import date

from unnati.connectors import gstn, phonepe
from unnati.reference import load_reference, population

REF = load_reference()

TABLE2 = """Table-2: SGST & SGST portion of IGST settled to States/UTs till September, 2026
(Rs. in crore)
Pre-Settlement SGST Post-Settlement SGST1
State/UT 2025-26 2026-27 Growth 2025-26 2026-27 Growth
Kerala 6,000 6,500 8% 17,000 19,437 14%
Dadra and Nagar Haveli and
Daman and Diu 600 650 8% 700 800 14%
Other Territory 168 276 65% 724 1,092 51%
Grand Total 2,75,291 2,91,150 6% 4,99,996 5,78,802 16%
"""


class _Page:
    def extract_text(self):
        return TABLE2


class _Pdf:
    pages = (_Page(),)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_gst_table2_reads_post_settlement_sgst(monkeypatch):
    monkeypatch.setattr(gstn.pdfplumber, "open", lambda _: _Pdf())
    period, rows = gstn.table2(b"")
    assert period.start == date(2026, 4, 1) and period.end == date(2026, 9, 30)
    assert dict((n, (a, b)) for n, a, b in rows)["Kerala"] == (17000, 19437)
    assert "Dadra and Nagar Haveli and Daman and Diu" in [n for n, _, _ in rows]
    found, _ = gstn.observations([b""], REF.resolver(), population())
    values = {(o.indicator_id, o.entity_slug): o.value for o in found}
    kerala = population()[("keralam", 2026)].persons
    assert values[("gst-collection-per-capita", "keralam")] == round(19437 * 1e7 / kerala)
    assert values[("gst-collection-growth", "india")] == round((578802 / 499996 - 1) * 100, 1)
    assert not any(slug == "other-territory" for _, slug in values)


def test_phonepe_calendar_years_and_latest_four_quarters():
    quarters = {(2025, q): {"kerala": 100.0 * q, "bihar": 50.0} for q in range(1, 5)}
    quarters[(2026, 1)] = {"kerala": 500.0, "bihar": 60.0}
    found, problems = phonepe.observations(quarters, REF.resolver(), population())
    labels = {(o.entity_slug, o.period.label) for o in found}
    assert ("keralam", "2025") in labels and ("india", "2025") in labels
    latest = [o for o in found if o.entity_slug == "keralam" and o.period.label.startswith("Apr 2025")]
    assert latest and latest[0].value == round(
        (200 + 300 + 400 + 500) / population()[("keralam", 2026)].persons, 1
    )
    assert problems == []
