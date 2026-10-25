"""FCFF DCF (Damodaran-style): growth = reinvestment rate x return on capital, margin/tax/WACC converge,
terminal ROC fades to the cost of capital over a moat-dependent number of years."""
import numpy as np

MOAT_YEARS = {"none": 0, "narrow": 5, "wide": 15}
ROC_CAP = 0.40
G_TERM_CAP = 0.045


def _nan0(x, d=0.0):
    return d if x is None or (isinstance(x, float) and np.isnan(x)) else x


def spread(cov):  # interest-coverage -> credit spread (simplified Damodaran table)
    for lim, sp in [(12.5, .006), (9.5, .008), (7.5, .01), (6, .0125), (4.5, .0175), (3.5, .0225),
                    (3, .0275), (2.5, .035), (2, .045), (1.5, .06)]:
        if cov > lim:
            return sp
    return .09


def build_inputs(p, erp=0.045, beta=None, ov=None):
    """ov: researched overrides (see inputs/*.json). beta/erp/rf feed the WACC; any other key replaces the computed input."""
    ov = {k: v for k, v in (ov or {}).items() if v is not None and k != "notes"}
    erp, beta = ov.pop("erp", erp), ov.pop("beta", beta)
    rf = ov.pop("rf", p["rf"])
    ebit, rev = p["ebit"], p["revenue"]
    t_eff = float(np.clip(_nan0(p["tax"]) / p["pretax"], 0.05, 0.30)) if p.get("pretax") else 0.21
    nopat = ebit * (1 - t_eff)
    beta = beta or float(np.clip(0.67 * _nan0(p.get("beta_raw"), 1.0) + 0.33, 0.6, 1.6))  # peer-median, else Blume
    cov = ebit / p["interest"] if p.get("interest") else 20
    kd = rf + spread(cov)
    debt, cash, mcap = _nan0(p["debt"]), _nan0(p["cash"]), p["mcap"]
    wd = debt / (debt + mcap)
    ke = rf + beta * erp
    wacc1 = (1 - wd) * ke + wd * kd * (1 - 0.25)
    wacc10 = (1 - wd) * (rf + erp) + wd * kd * (1 - 0.25)
    ic = max(debt + _nan0(p["equity"]) - cash - _nan0(p["goodwill"]), 0.05 * rev)  # capital ex-goodwill
    roc = nopat / ic
    reinv = -_nan0(p["capex"]) - _nan0(p["da"]) - _nan0(p["d_wc"])  # capex is negative in yfinance
    rr = float(np.clip(reinv / nopat, 0.02, 0.70)) if nopat > 0 else 0.02
    fund = rr * min(roc, ROC_CAP)
    r = {int(k): v for k, v in p.get("edgar", {}).get("revenue", {}).items()}
    ys = sorted(r)
    cagr = (r[ys[-1]] / r[ys[-4]]) ** (1 / 3) - 1 if len(ys) >= 4 else fund
    est = list(p.get("rev_est", {}).values())  # analyst revenue growth, current and next FY
    parts = ([fund] if rr > 0.02 + 1e-9 else []) + [cagr] + ([float(np.mean(est))] if est else [])
    g1 = float(np.clip(np.mean(parts), -0.03, 0.20))  # blend: fundamental, 3y CAGR, analyst consensus
    if ebit <= 0 and "target_margin" not in ov:
        raise ValueError(f"Operating income is negative ({ebit/rev:.0%} margin): a default DCF is meaningless. "
                         "Supply researched target_margin, g1, roc_cap, shares (see the company-narrative skill) via inputs/<TICKER>.json.")
    i = dict(rev0=rev, margin0=ebit / rev, target_margin=ebit / rev, t0=t_eff, t_end=0.25, g1=g1,
                rr=rr, fund_g=fund, cagr=cagr, analyst_g=(float(np.mean(est)) if est else None), margin_years=5, roc=roc, roc_cap=min(roc, ROC_CAP), wacc1=wacc1, wacc10=wacc10, ke=ke, kd=kd, wd=wd,
                beta=beta, rf=rf, erp=erp, g_term=min(rf, G_TERM_CAP), debt=debt, cash=cash,
                shares=p["shares"], price=p["price"])
    moat = ov.pop("moat", None)
    i.update(ov)
    if "wacc1" in ov and "wacc10" not in ov:
        i["wacc10"] = ov["wacc1"]
    i["g_term"] = min(i["g_term"], i["wacc10"] - 0.01)
    if moat:
        i["moat"] = moat
    return i


def value(i, moat="narrow", detail=False):
    g1, gt = i["g1"], i["g_term"]
    rev, roc0 = i["rev0"], i["roc_cap"]
    flows, nopat, prev = [], 0, i["rev0"]
    pv, disc = 0.0, 1.0
    for y in range(1, 11):
        fade = i.get("growth_fade")
        g = g1 if y <= 5 else fade[y - 6] if fade else g1 + (gt - g1) * (y - 5) / 5
        rev *= 1 + g
        m = i["margin0"] + (i["target_margin"] - i["margin0"]) * min(y / i.get("margin_years", 5), 1)
        t = i["t0"] + (i["t_end"] - i["t0"]) * y / 10
        w = i["wacc1"] + (i["wacc10"] - i["wacc1"]) * max(y - 5, 0) / 5
        roc = roc0 + (i["wacc10"] - roc0) * y / 10
        nopat = rev * m * (1 - t)
        if nopat <= 0 or i.get("s2c"):  # sales-to-capital reinvestment: always when supplied; forced in loss-making years (a negative NOPAT would flip the sign)
            f = nopat - (rev - prev) / i.get("s2c", 1.5)
        else:
            f = nopat * (1 - min(g / max(roc, 1e-3), 1.0))
        prev = rev
        disc /= 1 + w
        pv += f * disc
        flows.append(f)
    # excess-return fade after year 10 (moat), then Gordon on NOPAT/WACC
    n = i["moat_years"] if i.get("moat_years") is not None and moat == i.get("moat") else MOAT_YEARS[moat]
    n = int(n)
    roc_start = roc0 + (i["wacc10"] - roc0)  # = wacc10 by year 10; excess comes from moat spread below
    roc_exc = max(roc0, i["wacc10"])
    for k in range(1, n + 1):
        roc = roc_exc + (i["wacc10"] - roc_exc) * k / (n + 1) if n else i["wacc10"]
        nopat *= 1 + gt
        f = nopat * (1 - gt / roc)
        disc /= 1 + i["wacc10"]
        pv += f * disc
    nopat *= 1 + gt
    tv = nopat * (1 - gt / i["wacc10"]) / (i["wacc10"] - gt)
    ev = pv + tv * disc
    eq = ev + i["cash"] - i["debt"]
    ps = eq / i["shares"]
    return (ps, flows, dict(ev=ev, tv_share=tv * disc / ev)) if detail else ps


def scenarios(i, moat="narrow"):
    out = {}
    for name, dg, dm, dw, dt in [("Bear", -0.03, 0.90, +0.008, -0.003), ("Base", 0, 1, 0, 0), ("Bull", +0.03, 1.07, -0.007, 0)]:
        j = dict(i, g1=i["g1"] + dg, target_margin=i["target_margin"] * dm, wacc1=i["wacc1"] + dw,
                 wacc10=i["wacc10"] + dw, g_term=min(i["g_term"] + dt, i["wacc10"] + dw - 0.01))
        out[name] = dict(value=value(j, moat), g1=j["g1"], margin=j["target_margin"], wacc=j["wacc1"], g_term=j["g_term"])
    return out


def moat_table(i):
    return {m: value(i, m) for m in ("none", "narrow", "wide")}


def sensitivity(i, moat="narrow"):
    ws = [-0.02, -0.01, 0, 0.01, 0.02]
    gs = [-0.01, -0.005, 0, 0.005, 0.01]
    rows = []
    for dw in ws:
        row = []
        for dg in gs:
            j = dict(i, wacc1=i["wacc1"] + dw, wacc10=i["wacc10"] + dw)
            j["g_term"] = min(i["g_term"] + dg, j["wacc10"] - 0.01)
            row.append(value(j, moat))
        rows.append(row)
    return dict(wacc=[i["wacc1"] + d for d in ws], g=[i["g_term"] + d for d in gs], grid=rows)


def implied_growth(i, moat="narrow"):
    """Year-1..5 growth the current price requires (bisection)."""
    lo, hi = -0.2, 0.8
    if value(dict(i, g1=hi), moat) < i["price"]:
        return None
    for _ in range(50):
        mid = (lo + hi) / 2
        if value(dict(i, g1=mid), moat) < i["price"]:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def implied_wacc(i, moat="narrow"):
    """Discount rate (shift applied to the whole WACC path) at which the DCF equals the current price = market-implied return."""
    lo, hi = -0.04, 0.12
    f = lambda s: value(dict(i, wacc1=i["wacc1"] + s, wacc10=i["wacc10"] + s, g_term=min(i["g_term"], i["wacc10"] + s - 0.01)), moat) - i["price"]
    if f(lo) < 0 or f(hi) > 0:
        return None
    for _ in range(50):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) > 0 else (lo, mid)
    return i["wacc1"] + (lo + hi) / 2
