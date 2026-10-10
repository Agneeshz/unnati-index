from unnati.connectors import rbi_municipal
from unnati.reference import load_reference

# The shape of RBI's Statement 3 page: a title row, the header with one column group per ratio,
# year labels, column numbers, then a row per state and the total.
PAGE = """
<table>
<tr><td>Statement 3: Own Revenue of Municipal Corporations – Key Ratios</td></tr>
<tr><td>State/UT</td><td colspan='3'>Own Revenue / Revenue Receipts</td>
    <td colspan='3'>Own Tax Revenue / Revenue Receipts</td></tr>
<tr><td>2021-22 (Acco unts)</td><td>2022-23 (Revised Estim ates)</td><td>2023-24 (Budget Estim ates)</td>
    <td>2021-22 (Accounts)</td><td>2022-23 (Revised Estimates)</td><td>2023-24 (Budget Estimates)</td></tr>
<tr><td>1</td><td>2</td><td>3</td><td>4</td><td>5</td><td>6</td><td>7</td></tr>
<tr><td>6. Delhi</td><td>0.57</td><td>0.63</td><td>0.65</td><td>0.25</td><td>0.28</td><td>0.30</td></tr>
<tr><td>11. Jammu and Kashmir</td><td>0.15</td><td>-</td><td>1.00</td><td>-</td><td>-</td><td>-</td></tr>
<tr><td>Total</td><td>0.61</td><td>0.60</td><td>0.62</td><td>0.25</td><td>0.30</td><td>0.30</td></tr>
</table>
"""


def test_own_revenue_share_uses_accounts_and_revised_estimates_only():
    found, problems = rbi_municipal.observations(PAGE, load_reference().resolver())
    values = {(o.entity_slug, o.period.label): (o.value, o.is_provisional) for o in found}
    assert values == {
        ("delhi", "2021-22"): (57.0, False),
        ("delhi", "2022-23"): (63.0, True),  # revised estimate: provisional
        ("jammu-and-kashmir", "2021-22"): (15.0, False),  # "-" is skipped, budget estimates too
        ("india", "2021-22"): (61.0, False),
        ("india", "2022-23"): (60.0, True),
    }
    assert problems == ["RBI municipal finances: only 3 state rows read"]
