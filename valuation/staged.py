"""Three-stage DCF: Stage 1 growth, Stage 2 growth, Gordon-growth terminal stage. Every intermediate is returned.

Stage 1: 5 or 10 years at one flat growth rate (i["g1"]).
Stage 2: 0, 5 or 10 years; growth fades linearly from g2_start to g2_end (or an explicit list of that length).
Each stage picks one FCF method:  1 revenue x FCF margin   2 operating-margin build   4 Damodaran FCFF (margin ramp, ROC fade).
Each stage has its own method inputs in st["p1"] / st["p2"] (falling back to the same key in i, so a single shared set still works).
Method 4's margin ramp counts from the start of the stage that uses it; its tax and ROC fades reach their end values at the end of that stage.
Terminal: FCF(last year) x (1 + g) / (WACC - g), discounted from the last forecast year. One WACC for all years.
Amounts are raw dollars / shares, rates are decimals. Shares one WACC build (wacc_parts) with valuation/methodology.py."""
from .methodology import wacc_parts

STAGE1_LENS = (5, 10)
STAGE2_LENS = (0, 5, 10)
METHODS = (1, 2, 4)
NAMES = {1: "Revenue × FCF margin", 2: "Operating-margin build", 4: "Damodaran FCFF"}
NEED = {1: ["fcf_margin"],
        2: ["op_margin", "da_pct", "capex_pct", "nwc_pct", "content_pct"],
        4: ["margin0", "target_margin", "margin_years", "t_end", "roic0"]}
BASE = ["rev0", "g1", "rf", "beta", "erp", "kd", "tax", "g_term", "price", "shares", "debt", "cash"]


def param(i, st, stage, key):
    """Method input for a stage: the stage's own value if given, else the shared one in i."""
    v = (st.get(f"p{stage}") or {}).get(key)
    return i.get(key) if v is None else v


def validate(i, st):
    if st["len1"] not in STAGE1_LENS:
        raise ValueError(f"Stage 1 must be {STAGE1_LENS} years, got {st['len1']}")
    if st["len2"] not in STAGE2_LENS:
        raise ValueError(f"Stage 2 must be {STAGE2_LENS} years, got {st['len2']}")
    used = [(1, st["m1"])] + ([(2, st["m2"])] if st["len2"] else [])
    for stage, m in used:
        if m not in METHODS:
            raise ValueError(f"Method {m} is not available (choose from {METHODS})")
    missing = [k for k in BASE if i.get(k) is None]
    for stage, m in used:
        missing += [f"{k} (stage {stage})" for k in NEED[m] if param(i, st, stage, k) is None]
    if st["len2"] and not st.get("g2_list") and i.get("g2_end") is None and st.get("g2_end") is None:
        missing.append("g2_end")
    if missing:
        raise ValueError("missing inputs: " + ", ".join(sorted(set(missing))))


def growth_path(i, st):
    g = [i["g1"]] * st["len1"]
    n2 = st["len2"]
    if n2:
        lst = st.get("g2_list")
        if lst and len(lst) == n2:
            g += list(lst)
        else:
            a = st.get("g2_start", i["g1"])
            b = st.get("g2_end", i.get("g2_end"))
            g += [a + (b - a) * k / (n2 - 1) for k in range(n2)]
    return g


def run(i, st, wacc=None):
    """i: base + method inputs; st: dict(len1, len2, m1, m2, g2_start, g2_end, g2_list). wacc: optional override."""
    st = dict(st)
    st.setdefault("m2", st["m1"])
    validate(i, st)
    growth = growth_path(i, st)
    n = len(growth)
    wp = wacc_parts(i)
    w = wp["w_calc"] if wacc is None else wacc
    gt = i["g_term"]
    out = dict(stages=dict(len1=st["len1"], len2=st["len2"], m1=st["m1"], m2=st["m2"] if st["len2"] else None, n=n),
               growth=growth, ke=wp["ke"], equity_mv=wp["equity_mv"], wd=wp["wd"], we=1 - wp["wd"], kd_after_tax=wp["kd_at"],
               wacc_calc=wp["w_calc"], wacc=w)
    rows, prev = [], i["rev0"]
    for y in range(1, n + 1):
        stage = 1 if y <= st["len1"] else 2
        method = st["m1"] if stage == 1 else st["m2"]
        length = st["len1"] if stage == 1 else st["len2"]
        ys = y if stage == 1 else y - st["len1"]  # year within the stage
        P = lambda key: param(i, st, stage, key)
        g = growth[y - 1]
        r = prev * (1 + g)
        row = dict(year=y, stage=stage, method=method, growth=g, revenue=r)
        if method == 1:
            f = r * P("fcf_margin")
        elif method == 2:
            ebit = r * P("op_margin")
            nopat = ebit * (1 - i["tax"])
            da, capex, dnwc, other = r * P("da_pct"), r * P("capex_pct"), P("nwc_pct") * (r - prev), r * P("content_pct")
            f = nopat + da - capex - dnwc - other
            row.update(ebit=ebit, nopat=nopat, da=da, capex=capex, dnwc=dnwc, other=other)
        else:  # 4: margin ramps over margin_years from the stage start; tax and ROC reach their end values at the end of the stage
            m = P("margin0") + (P("target_margin") - P("margin0")) * min(ys / P("margin_years"), 1)
            tx = i["tax"] + (P("t_end") - i["tax"]) * ys / length
            roc = P("roic0") + (w - P("roic0")) * ys / length
            nopat = r * m * (1 - tx)
            rr = min(g / max(roc, 1e-3), 1.0) if nopat > 0 else None
            f = nopat * (1 - rr) if nopat > 0 else nopat - (r - prev) / 1.5  # loss years: reinvest from sales-to-capital 1.5
            row.update(op_margin=m, tax=tx, nopat=nopat, roc=roc, rr=rr)
        row.update(fcf=f, fcf_margin=f / r if r else None)
        rows.append(row)
        prev = r
    out.update(rows=rows, revenue=[x["revenue"] for x in rows], fcf=[x["fcf"] for x in rows], ok=w > gt)
    if st["len2"]:
        a, b = rows[st["len1"] - 1], rows[st["len1"]]
        out["boundary"] = dict(end_stage1=a["fcf_margin"], start_stage2=b["fcf_margin"], jump=b["fcf_margin"] - a["fcf_margin"],
                               growth_end_stage1=a["growth"], growth_start_stage2=b["growth"])
    out["growth_gap_to_terminal"] = growth[-1] - gt
    if w <= gt:
        out["error"] = f"WACC ({w:.2%}) must be above terminal growth ({gt:.2%})."
        return out
    df = [1 / (1 + w) ** t for t in range(1, n + 1)]
    pv = [f * d for f, d in zip(out["fcf"], df)]
    fcf_next = out["fcf"][-1] * (1 + gt)
    tv = fcf_next / (w - gt)
    tv_pv = tv * df[-1]
    ev = sum(pv) + tv_pv
    eq = ev + i["cash"] - i["debt"]
    ps = eq / i["shares"]
    for r_, d_, p_ in zip(rows, df, pv):
        r_.update(df=d_, pv=p_)
    out.update(discount=df, pv=pv, pv_sum=sum(pv), fcf_next=fcf_next, tv=tv, tv_pv=tv_pv,
               tv_share=tv_pv / ev if ev else None, tv_multiple=tv / out["fcf"][-1] if out["fcf"][-1] else None,
               ev=ev, equity=eq, per_share=ps, gap=(ps - i["price"]) / i["price"] if i.get("price") else None)
    return out


def value(i, st, **kw):
    return run(i, st, **kw).get("per_share")


def sensitivity(i, st, wacc=None):
    """WACC (rows) x terminal growth (columns), the same 5x5 grid as /dcf, centred on the WACC in use (an override if given). None where WACC <= g."""
    w0 = wacc_parts(i)["w_calc"] if wacc is None else wacc
    ws = [w0 + d for d in (-0.02, -0.01, 0, 0.01, 0.02)]
    gs = [i["g_term"] + d for d in (-0.01, -0.005, 0, 0.005, 0.01)]
    grid = [[value(dict(i, g_term=g), st, wacc=w) if w > g else None for g in gs] for w in ws]
    return dict(wacc=ws, g=gs, grid=grid)


def scenarios(i, st, wacc=None):
    """Bear / Base / Bull as on /dcf: stage-1 growth -/+3 pts, the margin of each method used -2/+3 pts (in that stage's own inputs), WACC +/-1 pt."""
    knob = {1: "fcf_margin", 2: "op_margin", 4: "target_margin"}
    used = [(1, st["m1"])] + ([(2, st.get("m2", st["m1"]))] if st["len2"] else [])
    w0 = wacc_parts(i)["w_calc"] if wacc is None else wacc
    out = {}
    for name, dg, dm, dw in [("Bear", -0.03, -0.02, +0.01), ("Base", 0, 0, 0), ("Bull", +0.03, +0.03, -0.01)]:
        j, sj = dict(i, g1=i["g1"] + dg), dict(st)
        margins = {}
        for stage, m in used:
            k = knob[m]
            p = dict(sj.get(f"p{stage}") or {})
            p[k] = param(i, st, stage, k) + dm
            sj[f"p{stage}"] = p
            margins[f"stage {stage} {k}"] = p[k]
        out[name] = dict(value=value(j, sj, wacc=w0 + dw), g1=j["g1"], wacc=w0 + dw, g_term=i["g_term"], margins=margins)
    return out


def full(i, st, wacc=None):
    r = run(i, st, wacc=wacc)
    if r.get("error"):
        return r
    r.update(sensitivity=sensitivity(i, st, wacc=wacc), scenarios=scenarios(i, st, wacc=wacc))
    flags = []
    if r["tv_share"] and r["tv_share"] > 0.7:
        flags.append(f"Terminal value is {r['tv_share']:.0%} of enterprise value: the result leans on the long-run assumptions.")
    if r["tv_multiple"] and r["tv_multiple"] > 25:
        flags.append(f"Terminal value equals {r['tv_multiple']:.0f}x last-year free cash flow, which is rich for a mature business.")
    if i["g_term"] > 0.035:
        flags.append("Terminal growth above ~3% exceeds long-run economic growth.")
    if r["growth_gap_to_terminal"] > 0.03:
        flags.append(f"Growth in the last forecast year ({r['growth'][-1]:.1%}) is far above terminal growth ({i['g_term']:.1%}): a cliff at the end of the forecast.")
    b = r.get("boundary")
    if b and abs(b["jump"]) > 0.03:
        flags.append(f"FCF margin jumps {b['jump']*100:+.1f} points between stage 1 ({b['end_stage1']:.1%}) and stage 2 ({b['start_stage2']:.1%}): check the two methods' assumptions are consistent.")
    r["flags"] = flags
    return r


# ── defaults, override mapping and goal seek (shared by /dcf and /dcf2, so both pages start from and map inputs identically)
PARAM_KEYS = ["fcf_margin", "op_margin", "da_pct", "capex_pct", "nwc_pct", "content_pct", "margin0", "target_margin", "margin_years", "t_end", "roic0"]
GLOBAL_KEYS = ["rev0", "g1", "rf", "beta", "erp", "kd", "g_term", "shares", "debt", "cash"]


def default_stage_config(D):
    """Starting stage set-up from the EDGAR defaults D: 5 + 5 years, Method 1 in both, Stage 2 growth fading 0.6 x g1 -> 3%."""
    p = {k: D[k] for k in PARAM_KEYS if D.get(k) is not None}
    return dict(len1=5, len2=5, m1=1, m2=1, g2_start=D["g1"] * 0.6, g2_end=0.03, p1=dict(p), p2=dict(p))


def default_growth_fade(D):
    """The five years-6-10 growth rates used when none are given: a straight line from the default Stage 2 start to its end."""
    c = default_stage_config(D)
    return [c["g2_start"] + (c["g2_end"] - c["g2_start"]) * k / 4 for k in range(5)]


def apply_overrides(D, ov, stages=None):
    """Map flat overrides (a pasted/saved JSON or the /dcf form) and an optional explicit stage state onto the defaults.
    Precedence: defaults < flat overrides < explicit stages. Returns (i, st, wacc, explicit); `explicit` holds only what was set, not defaults."""
    ov = {k: v for k, v in (ov or {}).items() if v is not None and k != "notes"}
    i = dict(D)
    for k in GLOBAL_KEYS:
        if k in ov:
            i[k] = float(ov[k])
    tax = ov.get("tax", ov.get("t_end"))
    if tax is not None:
        i["tax"] = float(tax)
    wacc = ov.get("wacc1", ov.get("wacc"))
    wacc = float(wacc) if wacc is not None else None
    st = default_stage_config(D)
    explicit = dict(p1={}, p2={})

    def setp(k, v):
        if v is not None:
            explicit["p1"][k] = float(v)
            explicit["p2"][k] = float(v)

    for k in ("fcf_margin", "da_pct", "capex_pct", "nwc_pct", "content_pct", "margin0", "target_margin", "margin_years", "t_end"):
        setp(k, ov.get(k))
    setp("op_margin", ov.get("op_margin", ov.get("target_margin", ov.get("margin0"))))
    roc = ov.get("roic0", ov.get("roc_cap") if isinstance(ov.get("roc_cap"), (int, float)) else None)
    setp("roic0", roc)
    if ov.get("g2") is not None:
        explicit.update(g2_start=float(ov["g2"]), g2_end=float(ov["g2"]), g2_list=None)
    elif isinstance(ov.get("growth_fade"), list) and ov["growth_fade"]:
        lst = [float(x) for x in ov["growth_fade"]]
        explicit.update(g2_list=lst, g2_start=lst[0], g2_end=lst[-1])
    elif ov.get("g10") is not None:
        explicit.update(g2_end=float(ov["g10"]), g2_list=None)
    for k in ("len1", "len2", "m1", "m2", "g2_start", "g2_end", "g2_list"):  # explicit stage state (the page's own controls) wins
        if stages and k in stages and stages[k] is not None:
            explicit[k] = stages[k]
    for pk in ("p1", "p2"):
        for k, v in ((stages or {}).get(pk) or {}).items():
            if v is not None:
                explicit[pk][k] = float(v)
    for k in ("len1", "len2", "m1", "m2"):
        if k in explicit:
            st[k] = int(explicit[k])
    for k in ("g2_start", "g2_end"):
        if k in explicit:
            st[k] = float(explicit[k])
    if explicit.get("g2_list"):
        st["g2_list"] = [float(x) for x in explicit["g2_list"]]
    for pk in ("p1", "p2"):
        st[pk].update(explicit[pk])
    return i, st, wacc, explicit


def _bisect(f, lo, hi, n=60):
    flo, fhi = f(lo), f(hi)
    if flo is None or fhi is None or flo > 0 or fhi < 0:
        return None
    for _ in range(n):
        mid = (lo + hi) / 2
        fm = f(mid)
        if fm is None:
            return None
        lo, hi = (mid, hi) if fm < 0 else (lo, mid)
    return (lo + hi) / 2


def implied_g1(i, st, wacc=None):
    """Stage-1 growth rate at which the DCF equals today's price (None if no rate in -20%..80% does)."""
    if not i.get("price"):
        return None
    return _bisect(lambda g: (lambda v: None if v is None else v - i["price"])(value(dict(i, g1=g), st, wacc=wacc)), -0.2, 0.8)


def implied_wacc(i, st):
    """Discount rate at which the DCF equals today's price: the return the market price implies."""
    if not i.get("price"):
        return None
    lo = i["g_term"] + 0.002

    def f(w):
        v = value(i, st, wacc=w)
        return None if v is None else i["price"] - v  # value falls as WACC rises, so this rises with w
    return _bisect(f, lo, 0.40)
