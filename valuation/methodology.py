"""DCF following DCF_methodology.md (Technique 1: revenue x FCF margin), one function, every intermediate returned.
Used by both DCF pages so they always agree. Amounts are raw dollars / raw share counts; rates are decimals.

Steps: 1 growth path -> 2 revenue -> 3 FCF -> 4 WACC -> 5 discount each FCF -> 6 terminal value (Gordon)
       -> 7 enterprise value -> 8 equity bridge (+cash, -total debt) -> 9 per share."""

N = 10
KEYS = ["rev0", "g1", "g10", "fcf_margin", "rf", "beta", "erp", "kd", "tax", "g_term", "price", "shares", "debt", "cash"]


def wacc_parts(i):
    """CAPM cost of equity, market-value weights and the blended WACC (shared by every engine)."""
    ke = i["rf"] + i["beta"] * i["erp"]
    equity_mv = i["price"] * i["shares"] if i.get("price") else 0.0
    wd = i["debt"] / (i["debt"] + equity_mv) if i["debt"] + equity_mv else 0.0
    kd_at = i["kd"] * (1 - i["tax"])
    return dict(ke=ke, equity_mv=equity_mv, wd=wd, kd_at=kd_at, w_calc=(1 - wd) * ke + wd * kd_at)


def run(i, wacc=None, fcf=None, fcf_next=None):
    """i: inputs (see KEYS). wacc: optional override of the computed WACC (used by sensitivity grids).
    fcf / fcf_next: explicit 10-year FCF path and year-11 FCF (from forecast()); default is revenue x FCF margin."""
    g1, g10, m = i["g1"], i["g10"], i["fcf_margin"]
    if i.get("two_stage"):  # years 1-5 at g1, years 6-10 at g2
        growth = [g1] * 5 + [i["g2"]] * 5
    elif i.get("growth_fade"):  # years 1-5 at g1, explicit rates for years 6-10
        growth = [g1] * 5 + list(i["growth_fade"])
    else:
        growth = [g1 + (g10 - g1) * t / (N - 1) for t in range(N)]  # year 1 = g1, year 10 = g10, linear
    rev, r = [], i["rev0"]
    for g in growth:
        r *= 1 + g
        rev.append(r)
    fcf = list(fcf) if fcf is not None else [x * m for x in rev]
    # WACC
    wp = wacc_parts(i)
    ke, equity_mv, wd, kd_at, w_calc = wp["ke"], wp["equity_mv"], wp["wd"], wp["kd_at"], wp["w_calc"]
    w = w_calc if wacc is None else wacc
    gt = i["g_term"]
    out = dict(growth=growth, revenue=rev, fcf=fcf, ke=ke, equity_mv=equity_mv, wd=wd, we=1 - wd, kd_after_tax=kd_at,
               wacc_calc=w_calc, wacc=w, ok=w > gt)
    if w <= gt:
        out["error"] = f"WACC ({w:.2%}) must be above terminal growth ({gt:.2%})."
        return out
    df = [1 / (1 + w) ** t for t in range(1, N + 1)]
    pv = [f * d for f, d in zip(fcf, df)]
    fcf_next = fcf_next if fcf_next is not None else fcf[-1] * (1 + gt)
    tv = fcf_next / (w - gt)
    tv_pv = tv * df[-1]
    ev = sum(pv) + tv_pv
    eq = ev + i["cash"] - i["debt"]
    ps = eq / i["shares"]
    out.update(discount=df, pv=pv, pv_sum=sum(pv), fcf_next=fcf_next, tv=tv, tv_pv=tv_pv, tv_share=tv_pv / ev if ev else None,
               tv_multiple=tv / fcf[-1] if fcf[-1] else None, ev=ev, equity=eq, per_share=ps,
               gap=(ps - i["price"]) / i["price"] if i.get("price") else None)
    return out


def value(i, **kw):
    r = run(i, **kw)
    return r.get("per_share")


def scenarios(i):
    cases = [("Bear", -0.03, -0.02, +0.01), ("Base", 0, 0, 0), ("Bull", +0.03, +0.03, -0.01)]
    out = {}
    for name, dg, dm, dw in cases:
        j = dict(i, g1=i["g1"] + dg, fcf_margin=i["fcf_margin"] + dm)
        base_w = run(j)["wacc_calc"]
        out[name] = dict(value=value(j, wacc=base_w + dw), g1=j["g1"], margin=j["fcf_margin"], wacc=base_w + dw, g_term=i["g_term"])
    return out


def sensitivity(i):
    """WACC (rows) x terminal growth (columns), and FCF margin (rows) x WACC (columns)."""
    w0 = run(i)["wacc_calc"]
    ws = [w0 + d for d in (-0.02, -0.01, 0, 0.01, 0.02)]
    gs = [i["g_term"] + d for d in (-0.01, -0.005, 0, 0.005, 0.01)]
    g1 = [[value(dict(i, g_term=g), wacc=w) if w > g else None for g in gs] for w in ws]
    ms = [i["fcf_margin"] + d for d in (-0.05, -0.025, 0, 0.025, 0.05)]
    g2 = [[value(dict(i, fcf_margin=mm), wacc=w) for w in ws] for mm in ms]
    return dict(wacc=ws, g=gs, grid=g1, margins=ms, grid_margin=g2)


def implied_margin(i):
    """FCF margin at which the DCF equals the current price (goal seek)."""
    if not i.get("price"):
        return None
    lo, hi = 0.0, 1.0
    f = lambda mm: value(dict(i, fcf_margin=mm)) - i["price"]
    if f(lo) > 0 or f(hi) < 0:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
    return (lo + hi) / 2


def implied_wacc(i):
    if not i.get("price"):
        return None
    lo, hi = i["g_term"] + 0.002, 0.40
    f = lambda w: value(i, wacc=w) - i["price"]
    if f(lo) < 0 or f(hi) > 0:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) > 0 else (lo, mid)
    return (lo + hi) / 2


def full(i):
    r = run(i)
    if r.get("error"):
        return r
    r.update(scenarios=scenarios(i), sensitivity=sensitivity(i), implied_margin=implied_margin(i), implied_wacc=implied_wacc(i))
    f = []
    if r["tv_share"] and r["tv_share"] > 0.7:
        f.append(f"Terminal value is {r['tv_share']:.0%} of enterprise value: the result leans on the long-run assumptions.")
    if r["tv_multiple"] and r["tv_multiple"] > 25:
        f.append(f"Terminal value equals {r['tv_multiple']:.0f}x year-10 free cash flow, which is rich for a mature business.")
    if i["g_term"] > 0.035:
        f.append("Terminal growth above ~3% exceeds long-run economic growth.")
    r["flags"] = f
    return r


TECH_KEYS = ["op_margin", "da_pct", "capex_pct", "nwc_pct", "content_pct", "roic0"]  # roic_term optional (defaults to WACC)


def forecast(i, t):
    """Methodology section 5b: the three ways to turn the revenue forecast into FCF (growth/revenue path is shared).
    i: base inputs (KEYS); t: technique inputs (TECH_KEYS, optional roic_term). Valuation is NOT done here."""
    base = run(i)
    growth, rev = base["growth"], base["revenue"]
    prev = [i["rev0"]] + rev[:-1]
    gT = i["g_term"]
    roic_term = t.get("roic_term") or base["wacc_calc"]
    # 1. revenue x FCF margin
    t1 = dict(fcf=[x * i["fcf_margin"] for x in rev])
    t1["fcf_next"] = t1["fcf"][-1] * (1 + gT)
    # 2. operating-margin build: EBIT -> NOPAT -> + D&A - capex - change in NWC - other net up-front investment
    ebit = [x * t["op_margin"] for x in rev]
    nopat = [e * (1 - i["tax"]) for e in ebit]
    da = [x * t["da_pct"] for x in rev]
    capex = [x * t["capex_pct"] for x in rev]
    dnwc = [t["nwc_pct"] * (x - p) for x, p in zip(rev, prev)]
    content = [x * t["content_pct"] for x in rev]
    f2 = [n + d - c - w - k for n, d, c, w, k in zip(nopat, da, capex, dnwc, content)]
    t2 = dict(ebit=ebit, nopat=nopat, da=da, capex=capex, dnwc=dnwc, content=content, fcf=f2, fcf_next=f2[-1] * (1 + gT))
    # 3. reinvestment rate: reinvestment = growth / ROIC, ROIC fades to terminal ROIC
    roic = [t["roic0"] + (roic_term - t["roic0"]) * k / N for k in range(1, N + 1)]
    rr = [min(max(g / r, 0.0), 0.9) for g, r in zip(growth, roic)]
    f3 = [n * (1 - r) for n, r in zip(nopat, rr)]
    rr_term = min(max(gT / roic_term, 0.0), 0.9)
    t3 = dict(nopat=nopat, growth=growth, roic=roic, rr=rr, fcf=f3, roic_term=roic_term, rr_term=rr_term,
              fcf_next=nopat[-1] * (1 + gT) * (1 - rr_term))
    for k in (t1, t2, t3):
        k["margin"] = [f / r for f, r in zip(k["fcf"], rev)]
        k["sum"] = sum(k["fcf"])
    return dict(growth=growth, revenue=rev, t1=t1, t2=t2, t3=t3, wacc_calc=base["wacc_calc"], roic_term=roic_term)


MOAT_YEARS = {"none": 0, "narrow": 5, "wide": 15}
DAM_KEYS = ["margin0", "target_margin", "margin_years", "t_end", "roic0"]  # + optional moat, moat_years, wacc10


def damodaran(i, t, wacc=None, wacc10=None):
    """Damodaran-style FCFF (the original /dcf model) with every intermediate returned.
    Revenue and growth come from the shared forecast; operating margin ramps to target_margin over margin_years, tax ramps to t_end,
    return on capital fades from roic0 to the year-10 WACC, reinvestment = growth / ROC, FCFF = NOPAT x (1 - reinvestment).
    WACC is wacc (years 1-5) fading to wacc10 (year 10); after year 10 the moat keeps excess returns for n years, then Gordon."""
    base = run(i)
    growth, rev = base["growth"], base["revenue"]
    w1 = wacc if wacc is not None else base["wacc_calc"]
    # year-10 WACC: beta normalises to 1 (market average), as in the original model
    w10 = wacc10 if wacc10 is not None else (wacc if wacc is not None else
          (1 - base["wd"]) * (i["rf"] + i["erp"]) + base["wd"] * base["kd_after_tax"])
    gt = min(i["g_term"], w10 - 0.01)
    moat = t.get("moat") or "narrow"
    n = int(t["moat_years"]) if t.get("moat_years") is not None else MOAT_YEARS[moat]
    m0, mT, my, tend, roc0 = t["margin0"], t["target_margin"], t["margin_years"], t["t_end"], t["roic0"]
    rows, disc, pv_sum, prev = [], 1.0, 0.0, i["rev0"]
    nopat = 0.0
    for y in range(1, N + 1):
        g, r = growth[y - 1], rev[y - 1]
        m = m0 + (mT - m0) * min(y / my, 1)
        tx = i["tax"] + (tend - i["tax"]) * y / N
        w = w1 + (w10 - w1) * max(y - 5, 0) / 5
        roc = roc0 + (w10 - roc0) * y / N
        nopat = r * m * (1 - tx)
        rr = min(g / max(roc, 1e-3), 1.0) if nopat > 0 else None
        f = nopat * (1 - rr) if nopat > 0 else nopat - (r - prev) / 1.5
        disc /= 1 + w
        pv_sum += f * disc
        rows.append(dict(year=y, growth=g, revenue=r, margin=m, tax=tx, nopat=nopat, roc=roc, rr=rr, fcff=f, wacc=w, df=disc, pv=f * disc))
        prev = r
    moat_rows = []
    roc_exc = max(roc0, w10)
    for k in range(1, n + 1):
        roc = roc_exc + (w10 - roc_exc) * k / (n + 1) if n else w10
        nopat *= 1 + gt
        f = nopat * (1 - gt / roc)
        disc /= 1 + w10
        pv_sum += f * disc
        moat_rows.append(dict(k=k, roc=roc, nopat=nopat, fcff=f, df=disc, pv=f * disc))
    nopat_next = nopat * (1 + gt)
    tv = nopat_next * (1 - gt / w10) / (w10 - gt)
    tv_pv = tv * disc
    ev = pv_sum + tv_pv
    eq = ev + i["cash"] - i["debt"]
    ps = eq / i["shares"]
    # shape compatible with run() so the page can show it like the other methods
    return dict(rows=rows, moat_rows=moat_rows, moat=moat, moat_n=n, wacc=w1, wacc10=w10, g_term=gt, roc_exc=roc_exc,
                nopat_next=nopat_next, rr_term=gt / w10, tv=tv, tv_pv=tv_pv, tv_df=disc, pv_sum=pv_sum, ev=ev, equity=eq, per_share=ps,
                tv_share=tv_pv / ev if ev else None, gap=(ps - i["price"]) / i["price"] if i.get("price") else None,
                fcf=[r["fcff"] for r in rows], discount=[r["df"] for r in rows], pv=[r["pv"] for r in rows],
                ke=base["ke"], kd_after_tax=base["kd_after_tax"], equity_mv=base["equity_mv"], wd=base["wd"], we=base["we"],
                tv_multiple=tv / rows[-1]["fcff"] if rows[-1]["fcff"] else None, fcf_next=nopat_next * (1 - gt / w10), ok=True)
