"""The worked example on the DCF methodology page must stay true."""
import pytest
from valuation import fcff

EXAMPLE = dict(rev0=1000.0, rf=0.04, beta=1.0, erp=0.05, kd=0.05, tax=0.21, g_term=0.025, shares=100.0, debt=0.0, cash=100.0, price=20.0,
               g1=0.10, margin0=0.20, target_margin=0.20, margin_years=5, t_end=0.21, da_pct=0.04, capex_pct=0.05, nwc_pct=0.10)


@pytest.fixture(scope="module")
def result():
    i, tr, _ = fcff.apply_overrides(EXAMPLE, {})
    return fcff.run(i, tr)


def test_wacc(result):
    assert result["wacc"] == pytest.approx(0.09)


def test_year_one(result):
    y1 = result["rows"][0]
    assert y1["revenue"] == pytest.approx(1100.0)
    assert y1["nopat"] == pytest.approx(173.8)
    assert y1["fcff"] == pytest.approx(152.8)


def test_value(result):
    assert result["pv_sum"] == pytest.approx(1432.84, abs=0.01)
    assert result["tv"] == pytest.approx(5075.30, abs=0.01)
    assert result["ev"] == pytest.approx(3576.70, abs=0.01)
    assert result["per_share"] == pytest.approx(36.77, abs=0.01)


def test_wacc_must_exceed_terminal_growth():
    i, tr, _ = fcff.apply_overrides(EXAMPLE, {"wacc1": 0.02})
    assert "error" in fcff.run(i, tr, wacc=0.02)


def test_reverse_dcf_recovers_price():
    i, tr, _ = fcff.apply_overrides(dict(EXAMPLE, price=60.0), {})
    solves = {s["key"]: s["implied"] for s in fcff.reverse_dcf(i, tr)["solves"]}
    assert solves["growth"] == pytest.approx(0.193, abs=0.001)
    assert solves["wacc"] == pytest.approx(0.0658, abs=0.001)


def test_terminal_reinvestment_check(result):
    """Section 4 of the methodology page: default terminal reinvestment is only ~3%, implying a very high return on new capital."""
    assert result["terminal_reinvestment_rate"] == pytest.approx(0.0313, abs=0.001)
    assert result["implied_terminal_roic"] == pytest.approx(0.80, abs=0.01)


def test_stable_roc_adjustment(result):
    """With a 10% stable ROC the reinvestment rate is g / ROC = 25% and the example value falls to about $31.93."""
    fcff11 = result["nopat_next"] * (1 - 0.025 / 0.10)
    tv_pv = fcff11 / (0.09 - 0.025) / 1.09 ** 10
    assert (result["pv_sum"] + tv_pv + 100) / 100 == pytest.approx(31.93, abs=0.01)
