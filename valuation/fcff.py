"""Textbook FCFF DCF with an editable per-year trajectory for every driver.

    FCFF_t = EBIT_t x (1 - T_t) + D&A_t - CapEx_t - dNWC_t
    EBIT   = revenue x operating margin      D&A, CapEx = % of revenue      dNWC = % of the change in revenue

Ten explicit years, one constant WACC, then Gordon growth on the year-11 FCFF built from the same drivers.
Every driver is a list of 10 yearly values (TRAJ_KEYS). Defaults come from the EDGAR table (valuation/edgar_table.py);
`traj` overrides replace a whole list. Amounts are raw dollars, rates are decimals. Shares the WACC build (wacc_parts)
with the other engines."""
from .methodology import wacc_parts
from .staged import _bisect

N = 10
TRAJ_KEYS = ["growth", "op_margin", "tax", "da_pct", "capex_pct", "nwc_pct"]
LABELS = {"growth": "Revenue growth", "op_margin": "Operating margin (EBIT / revenue)", "tax": "Tax rate on EBIT",
          "da_pct": "D&A (% of revenue)", "capex_pct": "CapEx (% of revenue)", "nwc_pct": "ΔNWC (% of change in revenue)"}
GLOBAL_KEYS = ["rev0", "rf", "beta", "erp", "kd", "g_term", "shares", "debt", "cash", "p_fail", "liq_ps", "price"]


def _lin(a, b, n=N):
    """n values from a to b, the last one equal to b (year 1 is one step from a)."""
    return [a + (b - a) * k / n for k in range(1, n + 1)]


def start_values(D):
    """Year-0 reference for each driver (TTM, from the EDGAR defaults)."""
    return dict(growth=D.get("last_growth") if D.get("last_growth") is not None else D["g1"], op_margin=D["margin0"],
                tax=D["tax"], da_pct=D["da_pct"], capex_pct=D["capex_pct"], nwc_pct=D["nwc_pct"])


def default_traj(D, g_term=None):
    """Default trajectories. Growth: g1 for years 1-5, then a straight line to terminal growth in year 10.
    Margin: ramps from today's to target_margin over margin_years (default target = today's, i.e. flat). Tax: TTM rate to t_end by year 10.
    D&A %: flat. CapEx %: D&A % plus the TTM net capex scaled by growth/g1, so net investment shrinks as growth fades and the terminal year is consistent.
    ΔNWC %: flat."""
    gt = D["g_term"] if g_term is None else g_term
    g1 = D["g1"]
    growth = [g1] * 5 + [g1 + (gt - g1) * k / 5 for k in range(1, 6)]
    my = max(float(D.get("margin_years") or 5), 1)
    margin = [D["margin0"] + (D["target_margin"] - D["margin0"]) * min(y / my, 1) for y in range(1, N + 1)]
    tax = _lin(D["tax"], D.get("t_end", 0.25))
    da = [D["da_pct"]] * N
    net0 = D["capex_pct"] - D["da_pct"]
    base_g = max(g1, 0.01)
    capex = [da[k] + net0 * max(growth[k], 0.0) / base_g for k in range(N)]
    return dict(growth=growth, op_margin=margin, tax=tax, da_pct=da, capex_pct=capex, nwc_pct=[D["nwc_pct"]] * N)


PRESET_NAMES = {"flat": "Flat (all constant)", "young": "Young growth", "growth": "Growth", "mature": "Mature", "declining": "Declining"}
PRESET_NOTES = {
    "flat": "The simple-DCF shape: EBIT margin, tax rate, D&A, CapEx and ΔNWC all held at their TTM values every year; growth keeps the default fade. FCFF is then a constant share of revenue.",
    "young": "Growth starts high (at least 25%) and fades to terminal; margin climbs over 10 years to a mature level (at least 15%); no tax for 4 years (NOLs), then up to 25%; heavy CapEx tapering so that year-10 reinvestment = g ÷ ROC; ΔNWC absorbs 10% of new revenue.",
    "growth": "Growth held (at least 12%) for 3 years, then fades; margin widens 3 pts over 5 years; tax to 25% within 3 years; CapEx stays high for 5 years, then tapers so that year-10 reinvestment = g ÷ ROC; ΔNWC at least 5% of new revenue.",
    "mature": "Growth capped near GDP+ (at most 5%) fading to terminal; margin, tax, D&A flat; CapEx moves to the level where year-10 reinvestment = g ÷ ROC (ROC a few points above WACC); ΔNWC as reported.",
    "declining": "Revenue shrinks (about −3% easing toward 0%); margin contracts 15% over 10 years; CapEx cut toward D&A; ΔNWC releases cash (−5% of the revenue change). Set a failure/distress probability and liquidation value, and consider lowering terminal growth.",
}
# Damodaran's life-cycle table (attributes / valuation issue / valuation solution), shown on the page
PRESET_GUIDE = {
    "flat": dict(attributes="Not a life-cycle stage: a no-trend baseline.", issue="Ignores margin expansion, tax normalisation and the fade in net investment as growth slows.",
                 solution="Use it to see what the TTM economics alone are worth, then bend individual curves."),
    "young": dict(attributes="No history; small or zero revenue with operating losses; high probability of failure; illiquid; multiple claims on equity.",
                  issue="Negative cash flows; revenue, target margin and survival time are hard to estimate.",
                  solution="Forecast revenue from market size × share; let margins converge to mature peers; then Value = DCF × (1 − probability of failure)."),
    "growth": dict(attributes="Fast-changing financials; market value far above book; low debt; short, unstable history.",
                   issue="Past growth cannot continue; how fast it fades is the hard part.",
                   solution="g = reinvestment rate × ROC; FCFF = EBIT(1 − t) − reinvestment; terminal value = FCFF(n+1) ÷ (WACC − g stable)."),
    "mature": dict(attributes="Growth near the economy's (2–3%); stable margins; high excess returns; debt capacity and cash build-up.",
                   issue="Complacency: past operating data can undervalue a firm with operating slack.",
                   solution="Restructure operations (raise EBIT/ROC) and financing (optimal debt ratio lowers WACC); terminal reinvestment rate = g stable ÷ ROC."),
    "declining": dict(attributes="Stagnant or shrinking revenue; falling margins and pricing power; asset sales; high default risk and leverage.",
                      issue="Depressed history, negative returns, a real chance of default.",
                      solution="Firm value = going-concern value × (1 − P distress) + liquidation value × P distress; take P distress from bond-rating default tables."),
}


def detect_stage(E, D):
    """Suggest a life-cycle stage (Damodaran ch. 5-8) from the SEC history: operating margin and its trend, 3-year revenue CAGR,
    length of history, interest cover. Returns {key, name, reasons, metrics}. A rule-based hint, not a verdict."""
    I = {r["key"]: r["vals"] for r in E["rows"]}
    n = len(E["cols"]) - 1                      # last fiscal-year column (the final column is TTM)
    rev, opm, opinc, intr = I["revenue"], I["op_m"], I["opinc"], I["interest"]
    ok = lambda x: x is not None
    cagr3 = (rev[n - 1] / rev[n - 4]) ** (1 / 3) - 1 if n >= 4 and ok(rev[n - 1]) and ok(rev[n - 4]) and rev[n - 4] > 0 else None
    m_now, m_then = D["margin0"], opm[n - 3] if n >= 3 and ok(opm[n - 3]) else None
    cover = D["margin0"] * rev[-1] / intr[-1] if ok(rev[-1]) and ok(intr[-1]) and intr[-1] else None
    years = sum(1 for v in rev[:n] if ok(v))
    g_last = E.get("last_growth")
    metrics = dict(cagr3=cagr3, margin_now=m_now, margin_3y_ago=m_then, interest_cover=cover, years_of_history=years, last_growth=g_last)
    reasons = []
    if m_now <= 0 or years < 4 or (cagr3 is not None and cagr3 > 0.40 and m_now < 0.05):
        key = "young"
        reasons.append("operating margin is not positive" if m_now <= 0 else "short history" if years < 4 else f"revenue CAGR {cagr3:.0%} with thin margins")
    elif (cagr3 is not None and cagr3 < -0.02) or (cagr3 is not None and cagr3 < 0.02 and m_then and m_now < 0.7 * m_then) or (cover is not None and cover < 1.5 and (cagr3 or 0) < 0.03):
        key = "declining"
        if cagr3 is not None and cagr3 < 0.02:
            reasons.append(f"revenue CAGR {cagr3:.1%} over 3 years")
        if m_then and m_now < 0.7 * m_then:
            reasons.append(f"operating margin fell from {m_then:.1%} to {m_now:.1%}")
        if cover is not None and cover < 1.5:
            reasons.append(f"interest cover only {cover:.1f}x")
    elif (cagr3 is not None and cagr3 >= 0.10) or (g_last is not None and g_last >= 0.12):
        key = "growth"
        reasons.append(f"revenue CAGR {cagr3:.0%} over 3 years" if cagr3 is not None else f"last-year growth {g_last:.0%}")
        reasons.append(f"operating margin {m_now:.1%}" + (f" (was {m_then:.1%} three years ago)" if m_then else ""))
    else:
        key = "mature"
        reasons.append((f"revenue growth of {cagr3:.1%} a year is close to the economy's" if cagr3 is not None and cagr3 >= 0.01 else f"revenue roughly flat ({cagr3:.1%} a year)") if cagr3 is not None else "slow, steady growth")
        if m_then:
            reasons.append(f"operating margin {m_then:.1%} three years ago, {m_now:.1%} now")
    return dict(key=key, name=PRESET_NAMES[key], reasons=reasons, metrics=metrics)


def presets(i):
    """Company-type starting curves (the six drivers) built from this company's own TTM numbers i and terminal growth: {key: {name, note, guide, traj}}.
    CapEx is solved so the year-10 net reinvestment equals g ÷ ROC of NOPAT (the stable-growth condition); ROC = WACC, a few points above for a mature firm."""
    gt = i["g_term"]
    g0 = i.get("last_growth") if i.get("last_growth") is not None else i["g1"]
    m0, da0, cx0, nw0, t0 = i["margin0"], i["da_pct"], i["capex_pct"], i["nwc_pct"], i["tax"]
    w = wacc_parts(i)["w_calc"]
    fade = lambda a, hold: [a if y < hold else a + (gt - a) * (y - hold + 1) / (N - hold) for y in range(N)]
    ramp = lambda a, b, n: [a + (b - a) * min((y + 1) / n, 1) for y in range(N)]

    def capex_end(m_end, t_end, da_end, nwc, roc):
        """Year-10 CapEx % of revenue so that CapEx − D&A + ΔNWC = (g ÷ ROC) × NOPAT."""
        return da_end + gt / roc * m_end * (1 - t_end) - nwc * gt / (1 + gt)

    out = {}
    out["flat"] = dict(growth=default_traj(i, gt)["growth"], op_margin=[m0] * N, tax=[t0] * N, da_pct=[da0] * N, capex_pct=[cx0] * N, nwc_pct=[nw0] * N)
    g = max(g0, 0.25)
    mt, da1 = max(m0, 0.15), max(da0, 0.05)
    out["young"] = dict(growth=fade(g, 1), op_margin=ramp(m0, mt, 10), tax=[0.0] * 4 + [0.25 * k / 6 for k in range(1, 7)],
                        da_pct=ramp(da0, da1, 10), capex_pct=ramp(max(cx0, 0.15), capex_end(mt, 0.25, da1, 0.10, w), 10), nwc_pct=[max(nw0, 0.10)] * N)
    g = max(g0, 0.12)
    mg = m0 + 0.03
    cg = capex_end(mg, 0.25, da0, max(nw0, 0.05), w)
    out["growth"] = dict(growth=fade(g, 3), op_margin=ramp(m0, mg, 5), tax=ramp(t0, 0.25, 3), da_pct=[da0] * N,
                         capex_pct=[cx0 if y < 5 else cx0 + (cg - cx0) * (y - 4) / 5 for y in range(N)], nwc_pct=[max(nw0, 0.05)] * N)
    g = min(max(g0, gt), 0.05)
    cm = capex_end(m0, 0.25, da0, nw0, w + 0.03)
    out["mature"] = dict(growth=fade(g, 3), op_margin=[m0] * N, tax=ramp(t0, 0.25, 3), da_pct=[da0] * N,
                         capex_pct=ramp(cx0, cm, 5), nwc_pct=[nw0] * N)
    md = m0 * 0.85
    out["declining"] = dict(growth=[-0.03 + 0.03 * y / (N - 1) for y in range(N)], op_margin=ramp(m0, md, 10), tax=ramp(t0, 0.25, 5),
                            da_pct=[da0] * N, capex_pct=ramp(cx0, capex_end(md, 0.25, da0, -0.05, w), 5), nwc_pct=[-0.05] * N)
    return {k: dict(name=PRESET_NAMES[k], note=PRESET_NOTES[k], guide=PRESET_GUIDE[k], traj=v) for k, v in out.items()}


def apply_overrides(D, ov):
    """Flat overrides (saved JSON, pasted skill output, the page's boxes) -> (inputs i, trajectories, wacc override).
    Understands the older single-number keys too: g1, growth_fade (years 6-10), target_margin, margin_years, t_end.
    A `traj` dict ({driver: [10 values]}) wins over everything else for the drivers it names."""
    ov = {k: v for k, v in (ov or {}).items() if v is not None and k != "notes"}
    i = dict(D)
    for k in GLOBAL_KEYS:
        if k in ov:
            i[k] = float(ov[k])
    for k in ("g1", "target_margin", "margin_years", "t_end", "da_pct", "capex_pct", "nwc_pct"):
        if k in ov:
            i[k] = float(ov[k])
    if "tax" in ov:
        i["tax"] = float(ov["tax"])
    if "margin0" in ov:
        i["margin0"] = float(ov["margin0"])
    if "op_margin" in ov and "target_margin" not in ov:
        i["target_margin"] = float(ov["op_margin"])
    i["g_term"] = float(ov.get("g_term", D["g_term"]))
    wacc = ov.get("wacc1", ov.get("wacc"))
    wacc = float(wacc) if wacc is not None else None
    tr = default_traj(i, i["g_term"])
    fade = ov.get("growth_fade")
    if isinstance(fade, list) and len(fade) == 5:
        tr["growth"][5:] = [float(x) for x in fade]
    elif ov.get("g10") is not None:
        tr["growth"][5:] = [i["g1"] + (float(ov["g10"]) - i["g1"]) * k / 5 for k in range(1, 6)]
    for k, v in (ov.get("traj") or {}).items():
        if k in TRAJ_KEYS and isinstance(v, list) and len(v) == N and all(x is not None for x in v):
            tr[k] = [float(x) for x in v]
    return i, tr, wacc


def run(i, tr, wacc=None):
    """i: scalar inputs; tr: the six trajectories. Returns every intermediate (rows per year, WACC build, terminal value, per share)."""
    wp = wacc_parts(i)
    w = wp["w_calc"] if wacc is None else wacc
    gt = i["g_term"]
    out = dict(ke=wp["ke"], equity_mv=wp["equity_mv"], wd=wp["wd"], we=1 - wp["wd"], kd_after_tax=wp["kd_at"], wacc_calc=wp["w_calc"], wacc=w, ok=w > gt)
    rows, prev = [], i["rev0"]
    for y in range(N):
        g = tr["growth"][y]
        rev = prev * (1 + g)
        ebit = rev * tr["op_margin"][y]
        tax = ebit * tr["tax"][y]
        da, capex, dnwc = rev * tr["da_pct"][y], rev * tr["capex_pct"][y], tr["nwc_pct"][y] * (rev - prev)
        fcff = ebit - tax + da - capex - dnwc
        rows.append(dict(year=y + 1, growth=g, revenue=rev, op_margin=tr["op_margin"][y], ebit=ebit, tax_rate=tr["tax"][y], nopat=ebit - tax,
                         da=da, capex=capex, dnwc=dnwc, fcff=fcff, fcff_margin=fcff / rev if rev else None))
        prev = rev
    out.update(rows=rows, fcff=[r["fcff"] for r in rows], revenue=[r["revenue"] for r in rows])
    if w <= gt:
        out["error"] = f"WACC ({w:.2%}) must be above terminal growth ({gt:.2%})."
        return out
    # terminal year: year-10 drivers held, revenue grows at g_term
    rev11 = prev * (1 + gt)
    ebit11 = rev11 * tr["op_margin"][-1]
    nopat11 = ebit11 * (1 - tr["tax"][-1])
    reinv11 = rev11 * (tr["capex_pct"][-1] - tr["da_pct"][-1]) + tr["nwc_pct"][-1] * (rev11 - prev)
    fcff11 = nopat11 - reinv11
    df = [1 / (1 + w) ** t for t in range(1, N + 1)]
    pv = [r["fcff"] * d for r, d in zip(rows, df)]
    tv = fcff11 / (w - gt)
    tv_pv = tv * df[-1]
    ev = sum(pv) + tv_pv
    eq = ev + i["cash"] - i["debt"]
    dcf_ps = eq / i["shares"]
    p_fail, liq = i.get("p_fail") or 0.0, i.get("liq_ps") or 0.0   # Damodaran ch. 5 / 8: value = going concern × (1 − p) + liquidation × p
    ps = dcf_ps * (1 - p_fail) + liq * p_fail
    for r_, d_, p_ in zip(rows, df, pv):
        r_.update(df=d_, pv=p_)
    out.update(discount=df, pv=pv, pv_sum=sum(pv), fcff_next=fcff11, nopat_next=nopat11,
               terminal_reinvestment_rate=(reinv11 / nopat11) if nopat11 > 0 else None,
               implied_terminal_roic=(gt * nopat11 / reinv11) if reinv11 > 0 and gt > 0 else None,
               tv=tv, tv_pv=tv_pv, tv_share=tv_pv / ev if ev else None, tv_multiple=tv / rows[-1]["fcff"] if rows[-1]["fcff"] > 0 else None,
               ev=ev, equity=eq, dcf_per_share=dcf_ps, per_share=ps, gap=(ps - i["price"]) / max(ps, i["price"]) if i.get("price") and ps > 0 else None)
    return out


def value(i, tr, **kw):
    return run(i, tr, **kw).get("per_share")


def _shift_growth(tr, d):
    """Add d to growth in years 1-5, tapering to 0 by year 10 (so a scenario does not break the fade into terminal growth)."""
    t = {k: list(v) for k, v in tr.items()}
    t["growth"] = [g + d * (1 if y < 5 else (N - 1 - y) / 5) for y, g in enumerate(tr["growth"])]
    return t


def sensitivity(i, tr, wacc=None):
    w0 = run(i, tr)["wacc_calc"] if wacc is None else wacc
    ws = [w0 + d for d in (-0.02, -0.01, 0, 0.01, 0.02)]
    gs = [i["g_term"] + d for d in (-0.01, -0.005, 0, 0.005, 0.01)]
    return dict(wacc=ws, g=gs, grid=[[value(dict(i, g_term=g), tr, wacc=w) if w > g else None for g in gs] for w in ws])


def scenarios(i, tr, wacc=None):
    """Bear / Base / Bull: growth -/+3 pts (years 1-5, tapering), operating margin -2/+3 pts in every year, WACC +/-1 pt."""
    w0 = run(i, tr)["wacc_calc"] if wacc is None else wacc
    out = {}
    for name, dg, dm, dw in [("Bear", -0.03, -0.02, +0.01), ("Base", 0, 0, 0), ("Bull", +0.03, +0.03, -0.01)]:
        t = _shift_growth(tr, dg)
        t["op_margin"] = [m + dm for m in tr["op_margin"]]
        out[name] = dict(value=value(i, t, wacc=w0 + dw), g1=t["growth"][0], margin=t["op_margin"][-1], wacc=w0 + dw, g_term=i["g_term"])
    return out


def implied_growth(i, tr, wacc=None):
    """Shift of the year 1-5 growth path at which the DCF equals the price, reported as the implied year-1 growth rate."""
    if not i.get("price"):
        return None
    s = _bisect(lambda d: (lambda v: None if v is None else v - i["price"])(value(i, _shift_growth(tr, d), wacc=wacc)), -0.3, 0.6)
    return None if s is None else tr["growth"][0] + s


def implied_wacc(i, tr):
    if not i.get("price"):
        return None
    return _bisect(lambda w: (lambda v: None if v is None else i["price"] - v)(value(i, tr, wacc=w)), i["g_term"] + 0.002, 0.40)


def reverse_dcf(i, tr, wacc=None, hb=None):
    """Reverse DCF: take today's price as given and solve, one lever at a time with everything else as in the current curves, for the
    assumption the price implies. Levers: year 1-5 growth (path shifted, tapering to the terminal rate), EBIT margin (every year shifted),
    terminal growth, discount rate. Also a growth x margin trade-off (required year-10 EBIT margin for several growth paths) and the
    market enterprise value (market cap + debt - cash) against the model's. Returns None without a price."""
    price = i.get("price")
    if not price:
        return None
    base = run(i, tr, wacc=wacc)
    w0 = base["wacc"]
    mcap = price * i["shares"]
    ev_mkt = mcap + i["debt"] - i["cash"]
    cagr = lambda t: ((lambda p: p ** (1 / N))(__import__("math").prod(1 + g for g in t["growth"])) - 1)
    gap = lambda **kw: (lambda v: None if v is None else v - price)(value(kw.get("i", i), kw.get("tr", tr), wacc=kw.get("w", wacc)))

    def shifted_margin(t, d):
        t = {k: list(v) for k, v in t.items()}
        t["op_margin"] = [m + d for m in t["op_margin"]]
        return t

    out = dict(price=price, market_cap=mcap, debt=i["debt"], cash=i["cash"], market_ev=ev_mkt, model_ev=base.get("ev"), model_value=base.get("per_share"), wacc=w0)
    if hb:
        rows = {r["key"]: r["vals"] for r in hb["rows"]}
        f = [v for v in rows["fcff"] if v is not None]
        out.update(ttm_fcff=(rows["fcff"][-1] if rows["fcff"][-1] is not None else (f[-1] if f else None)),
                   ttm_revenue=rows["revenue"][-1], fy_fcff_margin=[v for v in rows["fcff_margin"] if v is not None][-1:] or None,
                   hist_margin_max=max([v for v in rows["op_margin"][:-1] if v is not None] or [None]),
                   hist_growth_avg3=(sum(v for v in rows["growth"][-4:-1] if v is not None) / max(1, len([v for v in rows["growth"][-4:-1] if v is not None]))))
        out["ttm_fcff"] = None if out["ttm_fcff"] is None else out["ttm_fcff"] * 1e6
        out["ttm_revenue"] = None if out["ttm_revenue"] is None else out["ttm_revenue"] * 1e6
    solves = []
    sg = _bisect(lambda d: gap(tr=_shift_growth(tr, d)), -0.3, 0.6)
    gt_ = None if sg is None else _shift_growth(tr, sg)
    solves.append(dict(key="growth", label="Revenue growth, years 1–5", current=tr["growth"][0], implied=None if sg is None else tr["growth"][0] + sg,
                       extra=None if sg is None else dict(cagr10=cagr(gt_), current_cagr10=cagr(tr)), curve=None if sg is None else gt_["growth"], target="growth"))
    sm = _bisect(lambda d: gap(tr=shifted_margin(tr, d)), -0.5, 0.8)
    solves.append(dict(key="op_margin", label="EBIT margin, every year (year 10 shown)", current=tr["op_margin"][-1], implied=None if sm is None else tr["op_margin"][-1] + sm,
                       extra=dict(hist_max=out.get("hist_margin_max")), curve=None if sm is None else shifted_margin(tr, sm)["op_margin"], target="op_margin"))
    wl = w0 - 0.0
    sgt = _bisect(lambda x: gap(i=dict(i, g_term=x)), -0.03, w0 - 0.002)
    solves.append(dict(key="g_term", label="Terminal growth", current=i["g_term"], implied=sgt, extra=None, curve=None, target=None))
    swc = _bisect(lambda w: (lambda v: None if v is None else price - v)(value(i, tr, wacc=w)), i["g_term"] + 0.002, 0.40)
    solves.append(dict(key="wacc", label="Discount rate (WACC) — the return the price implies", current=w0, implied=swc, extra=None, curve=None, target=None))
    out["solves"] = solves
    grid = []
    for d in (-0.04, -0.02, 0.0, 0.02, 0.04, 0.06):
        tg = _shift_growth(tr, d)
        m = _bisect(lambda x: gap(tr=shifted_margin(tg, x)), -0.5, 0.8)
        grid.append(dict(growth1=tg["growth"][0], cagr10=cagr(tg), margin10=None if m is None else tg["op_margin"][-1] + m,
                         growth_curve=tg["growth"], margin_curve=None if m is None else shifted_margin(tg, m)["op_margin"]))
    out["tradeoff"] = grid
    return out


def history(E):
    """Reported ratios per fiscal year + TTM from the EDGAR table, in the same units as the drivers."""
    I = {r["key"]: r["vals"] for r in E["rows"]}
    rev = I["revenue"]
    n = len(rev)
    div = lambda a, b: a / b if a is not None and b else None
    growth = [None] + [div(rev[k], rev[k - 1]) - 1 if div(rev[k], rev[k - 1]) is not None else None for k in range(1, n - 1)] + [None]
    growth[-1] = E.get("last_growth")  # TTM column: growth of the latest fiscal year
    dn = I["dnwc"]
    return dict(labels=E["cols"], growth=growth, op_margin=I["op_m"], tax=I["tax_rate"],
                da_pct=[div(abs(I["da"][k] or 0), rev[k]) if I["da"][k] is not None else None for k in range(n)],
                capex_pct=[div(abs(I["capex"][k] or 0), rev[k]) if I["capex"][k] is not None else None for k in range(n)],
                nwc_pct=[div(dn[k], rev[k] - rev[k - 1]) if k and dn[k] is not None and rev[k] is not None and rev[k - 1] is not None and rev[k] != rev[k - 1] else None for k in range(n)])


def history_build(E):
    """Reported FCFF build for every fiscal year in the EDGAR table (about 10 years) plus TTM, as the steps the forecast uses:
    EBIT -> tax on EBIT -> NOPAT -> + D&A - CapEx - dNWC -> FCFF, with each line's ratio to revenue (or to the change in revenue for dNWC).
    Tax rate used is the effective rate clipped to 0-35% so a loss year does not create a negative tax. Amounts in $ millions; None where EDGAR has no value."""
    I = {r["key"]: r["vals"] for r in E["rows"]}
    n = len(E["cols"])
    rev, ebit, da, dn = I["revenue"], I["opinc"], I["da"], I["dnwc"]
    cx = [None if v is None else abs(v) for v in I["capex"]]
    ok = lambda *a: all(x is not None for x in a)
    div = lambda a, b: a / b if ok(a, b) and b else None
    g = [None] + [div(rev[k], rev[k - 1]) - 1 if div(rev[k], rev[k - 1]) is not None else None for k in range(1, n - 1)] + [E.get("last_growth")]
    tr = [None if t is None else min(max(t, 0.0), 0.35) for t in I["tax_rate"]]
    tax = [ebit[k] * tr[k] if ok(ebit[k], tr[k]) else None for k in range(n)]
    nopat = [ebit[k] - tax[k] if ok(ebit[k], tax[k]) else None for k in range(n)]
    fcff = [nopat[k] + da[k] - cx[k] - dn[k] if ok(nopat[k], da[k], cx[k], dn[k]) else None for k in range(n)]
    drev = [None] + [rev[k] - rev[k - 1] if ok(rev[k], rev[k - 1]) else None for k in range(1, n)]
    drev[-1] = rev[-1] - rev[n - 2] if E["ends"][-1] != E["ends"][-2] and ok(rev[-1], rev[n - 2]) else drev[-1]
    rows = [
        ("Revenue", "revenue", rev, "m", "step"), ("Revenue growth", "growth", g, "pct", "ratio"),
        ("EBIT (operating income)", "ebit", ebit, "m", "step"), ("Operating margin", "op_margin", I["op_m"], "pct", "ratio"),
        ("Effective tax rate (reported)", "tax_rate", I["tax_rate"], "pct", "ratio"), ("Tax rate used (clipped 0-35%)", "tax_used", tr, "pct", "ratio"),
        ("− Tax on EBIT", "tax", tax, "m", "step"), ("= NOPAT  [EBIT × (1 − T)]", "nopat", nopat, "m", "total"),
        ("+ D&A", "da", da, "m", "step"), ("D&A % of revenue", "da_pct", [div(da[k], rev[k]) for k in range(n)], "pct", "ratio"),
        ("− CapEx", "capex", cx, "m", "step"), ("CapEx % of revenue", "capex_pct", [div(cx[k], rev[k]) for k in range(n)], "pct", "ratio"),
        ("− Increase in operating working capital (ΔNWC)", "dnwc", dn, "m", "step"), ("ΔNWC % of change in revenue", "nwc_pct", [div(dn[k], drev[k]) for k in range(n)], "pct", "ratio"),
        ("= FCFF  [NOPAT + D&A − CapEx − ΔNWC]", "fcff", fcff, "m", "total"), ("FCFF margin", "fcff_margin", [div(fcff[k], rev[k]) for k in range(n)], "pct", "ratio"),
        ("Memo: reported FCF (operating cash flow − CapEx)", "fcf", I["fcf"], "m", "memo"),
    ]
    return dict(cols=E["cols"], rows=[dict(label=l, key=k, vals=v, unit=u, kind=kd) for l, k, v, u, kd in rows])


def full(i, tr, wacc=None):
    r = run(i, tr, wacc=wacc)
    if r.get("error"):
        return r
    r.update(sensitivity=sensitivity(i, tr, wacc=wacc), scenarios=scenarios(i, tr, wacc=wacc))
    f = []
    if r["tv_share"] and r["tv_share"] > 0.7:
        f.append(f"Terminal value is {r['tv_share']:.0%} of enterprise value: the result leans on the long-run assumptions.")
    if i["g_term"] > 0.035:
        f.append("Terminal growth above ~3% exceeds long-run economic growth.")
    if tr["growth"][-1] - i["g_term"] > 0.03:
        f.append(f"Year-10 growth ({tr['growth'][-1]:.1%}) is far above terminal growth ({i['g_term']:.1%}): a cliff after the forecast.")
    roic = r.get("implied_terminal_roic")
    if r.get("terminal_reinvestment_rate") is not None and r["terminal_reinvestment_rate"] <= 0:
        f.append("Terminal reinvestment (CapEx - D&A + ΔNWC) is zero or negative while the business still grows: raise year-10 CapEx or lower terminal growth.")
    elif roic is not None and roic > 0.5:
        f.append(f"Terminal growth of {i['g_term']:.1%} needs only {r['terminal_reinvestment_rate']:.0%} of NOPAT reinvested, i.e. a {roic:.0%} return on new capital forever: check year-10 CapEx and ΔNWC.")
    if any(rw["fcff"] < 0 for rw in r["rows"]):
        f.append("FCFF is negative in some forecast years (heavy CapEx or working capital): the terminal value still assumes year-10 drivers.")
    r["flags"] = f
    return r
