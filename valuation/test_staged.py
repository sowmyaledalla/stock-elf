"""Regression and sanity tests for valuation/staged.py. Run:  python3 -m valuation.test_staged
1. M1 and M2 at 5+5 years must equal today's single-stage Methods 1 and 2 (methodology.run on forecast()).
2. M4 at 5+5 must equal today's damodaran() when its extras are neutralised (one WACC, no moat years, last growth = g_term).
3. Mixed methods take each stage's FCF from its own method.
4. Other horizons (5, 10+0, 5+10, 10+10) match an independent hand calculation.
5. Bad stage lengths / Method 3 / WACC <= g are rejected; sensitivity and scenario base cells equal the main value."""
import copy, random
from . import methodology as m
from . import staged as s

TOL = 1e-9


def mk(k):
    r = random.Random(1000 + k)
    i = dict(rev0=r.uniform(5e9, 6e10), g1=r.uniform(.03, .2), g10=.03, fcf_margin=r.uniform(.05, .3), rf=r.uniform(.03, .055),
             beta=r.uniform(.8, 1.7), erp=r.uniform(.04, .055), kd=r.uniform(.04, .08), tax=r.uniform(.1, .25), g_term=r.uniform(.015, .03),
             price=r.uniform(20, 300), shares=r.uniform(1e9, 5e9), debt=r.uniform(0, 3e10), cash=r.uniform(0, 2e10),
             op_margin=r.uniform(.1, .4), da_pct=r.uniform(.005, .05), capex_pct=r.uniform(.01, .08), nwc_pct=r.uniform(-.1, .1),
             content_pct=r.uniform(0, .04), roic0=r.uniform(.1, .4), margin0=r.uniform(.1, .35), target_margin=r.uniform(.15, .4),
             margin_years=5, t_end=r.uniform(.15, .27))
    return i


def close(a, b, what):
    assert abs(a - b) <= TOL * max(1, abs(a), abs(b)), f"{what}: {a!r} != {b!r}"


def test_m1_m2_match_single_stage():
    for k in range(200):
        i = mk(k)
        fade = [i["g1"] * f for f in (.8, .65, .5, .4, .3)]
        i0 = dict(i, growth_fade=fade)  # today's engine: years 1-5 at g1, explicit rates for 6-10
        st = dict(len1=5, len2=5, m1=1, m2=1, g2_list=fade)
        new = s.run(i, st)
        old = m.run(i0)
        for key in ("per_share", "pv_sum", "tv", "tv_pv", "ev", "equity", "tv_share", "wacc"):
            close(new[key], old[key], f"M1 {key} set {k}")
        for a, b in zip(new["fcf"], old["fcf"]):
            close(a, b, "M1 fcf")
        t = {x: i[x] for x in m.TECH_KEYS}
        f = m.forecast(i0, t)["t2"]
        old2 = m.run(i0, fcf=f["fcf"], fcf_next=f["fcf_next"])
        new2 = s.run(i, dict(len1=5, len2=5, m1=2, m2=2, g2_list=fade))
        for key in ("per_share", "pv_sum", "tv", "ev"):
            close(new2[key], old2[key], f"M2 {key} set {k}")
    print("OK  M1 and M2 at 5+5 equal today's engine (200 random input sets)")


def m4_params(i):
    return dict(margin0=i["margin0"], target_margin=i["target_margin"], margin_years=5, t_end=i["t_end"], roic0=i["roic0"])


def test_m4_matches_damodaran_when_neutralised():
    """Stage 1 = 10 years of Method 4 is exactly today's Damodaran FCFF with one WACC and no moat years (flat growth)."""
    for k in range(200):
        i = mk(k)
        w = m.wacc_parts(i)["w_calc"]
        t = dict(m4_params(i), moat="none", moat_years=0)
        i0 = dict(i, growth_fade=[i["g1"]] * 5)
        old = m.damodaran(i0, t, wacc=w, wacc10=w)
        new = s.run(i, dict(len1=10, len2=0, m1=4))
        for a, b in zip(new["fcf"], old["fcf"]):
            close(a, b, f"M4 fcf set {k}")
        # the values agree too when the last growth rate equals terminal growth (the two terminal formulas then coincide)
        j = dict(i, g1=i["g_term"])
        j0 = dict(j, growth_fade=[j["g1"]] * 5)
        close(s.run(j, dict(len1=10, len2=0, m1=4))["per_share"], m.damodaran(j0, t, wacc=w, wacc10=w)["per_share"], f"M4 per share set {k}")
    print("OK  Stage 1 = 10 years of Method 4 equals today's Damodaran FCFF year by year, and in value when growth ends at g_term (200 sets)")


def test_m4_ramps_restart_in_stage_2():
    """Method 4 in stage 2 behaves like a fresh Damodaran model starting from the revenue at the end of stage 1."""
    for k in range(100):
        i = mk(k)
        g = i["g1"] * .6
        w = m.wacc_parts(i)["w_calc"]
        p2 = dict(margin0=i["margin0"] * 0.9, target_margin=i["target_margin"], margin_years=5, t_end=i["t_end"], roic0=i["roic0"] * 0.8)
        st = dict(len1=5, len2=10, m1=1, m2=4, g2_start=g, g2_end=g, p2=p2)
        new = s.run(dict(i, g1=g), st)
        rev5 = new["rows"][4]["revenue"]
        sub = dict(i, rev0=rev5, g1=g, growth_fade=[g] * 5)
        old = m.damodaran(sub, dict(p2, moat="none", moat_years=0), wacc=w, wacc10=w)
        for y in range(10):
            close(new["rows"][5 + y]["fcf"], old["fcf"][y], f"stage-2 M4 year {y+1} set {k}")
    print("OK  Method 4 in Stage 2 equals a fresh Damodaran model started from the end-of-Stage-1 revenue (100 sets)")


def test_per_stage_inputs():
    for k in range(50):
        i = mk(k)
        i["g2_end"] = i["g_term"] + .01
        st = dict(len1=5, len2=5, m1=1, m2=1, g2_start=i["g1"] * .7, p1=dict(fcf_margin=.20), p2=dict(fcf_margin=.30))
        r = s.run(i, st)
        for row in r["rows"]:
            close(row["fcf"], row["revenue"] * (.20 if row["stage"] == 1 else .30), "per-stage margin")
        # a stage's own value beats the shared one; missing own value falls back to the shared one
        st2 = dict(st, p2={})
        r2 = s.run(i, st2)
        for row in r2["rows"][5:]:
            close(row["fcf"], row["revenue"] * i["fcf_margin"], "fallback to shared input")
        # method 2 per stage
        st3 = dict(len1=5, len2=5, m1=2, m2=2, g2_start=i["g1"] * .7, p1=dict(op_margin=.2), p2=dict(op_margin=.35))
        r3 = s.run(i, st3)
        assert abs(r3["rows"][0]["ebit"] / r3["rows"][0]["revenue"] - .2) < TOL and abs(r3["rows"][9]["ebit"] / r3["rows"][9]["revenue"] - .35) < TOL
    print("OK  each stage uses its own inputs (Method 1 margin, Method 2 operating margin) and falls back to the shared value")


def test_mixed_methods():
    i = mk(3)
    fade = [i["g1"] * f for f in (.8, .65, .5, .4, .3)]
    i0 = dict(i, growth_fade=fade)
    t = {x: i[x] for x in m.TECH_KEYS}
    f = m.forecast(i0, t)
    mixed = s.run(i, dict(len1=5, len2=5, m1=1, m2=2, g2_list=fade))
    for y in range(5):
        close(mixed["fcf"][y], f["t1"]["fcf"][y], f"stage 1 year {y+1} uses method 1")
    for y in range(5, 10):
        close(mixed["fcf"][y], f["t2"]["fcf"][y], f"stage 2 year {y+1} uses method 2")
    close(mixed["fcf_next"], f["t2"]["fcf"][9] * (1 + i["g_term"]), "terminal uses last year's FCF")
    assert [r["method"] for r in mixed["rows"]] == [1] * 5 + [2] * 5 and [r["stage"] for r in mixed["rows"]] == [1] * 5 + [2] * 5
    assert abs(mixed["boundary"]["jump"] - (mixed["rows"][5]["fcf_margin"] - mixed["rows"][4]["fcf_margin"])) < TOL
    print("OK  mixed methods: stage 1 from method 1, stage 2 from method 2, terminal from the last year")


def hand_value(i, growth, margin, w, gt):
    """Independent calculation for method 1: no shared code with staged.py."""
    rev, pv = i["rev0"], 0.0
    for t, g in enumerate(growth, 1):
        rev *= 1 + g
        pv += rev * margin / (1 + w) ** t
    tv = rev * margin * (1 + gt) / (w - gt) / (1 + w) ** len(growth)
    return (pv + tv + i["cash"] - i["debt"]) / i["shares"]


def test_horizons_against_hand_calc():
    for (l1, l2) in [(5, 0), (10, 0), (5, 5), (5, 10), (10, 5), (10, 10)]:
        for k in range(30):
            i = mk(k)
            i["g2_end"] = i["g_term"] + .01
            st = dict(len1=l1, len2=l2, m1=1, m2=1, g2_start=i["g1"] * .7, g2_end=i["g2_end"])
            r = s.run(i, st)
            g = [i["g1"]] * l1 + [st["g2_start"] + (st["g2_end"] - st["g2_start"]) * q / (l2 - 1) for q in range(l2)] if l2 else [i["g1"]] * l1
            w = m.wacc_parts(i)["w_calc"]
            close(r["per_share"], hand_value(i, g, i["fcf_margin"], w, i["g_term"]), f"{l1}+{l2} per share set {k}")
            assert len(r["fcf"]) == l1 + l2 == r["stages"]["n"] and len(r["discount"]) == l1 + l2
            close(r["discount"][-1], 1 / (1 + w) ** (l1 + l2), "last discount factor")
    print("OK  horizons 5, 10, 10, 15, 15, 20 years match an independent hand calculation (180 cases)")


def test_validation():
    i = mk(1)
    for bad in (dict(len1=7, len2=5, m1=1), dict(len1=0, len2=5, m1=1), dict(len1=5, len2=3, m1=1), dict(len1=5, len2=15, m1=1),
                dict(len1=5, len2=5, m1=3), dict(len1=5, len2=5, m1=1, m2=3), dict(len1=5, len2=5, m1=1, m2=7)):
        try:
            s.run(dict(i, g2_end=.03), bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted invalid stage config {bad}")
    # method 3 is allowed in stage 2 only when stage 2 is absent (it is then never used)
    s.run(i, dict(len1=5, len2=0, m1=1, m2=3))
    # missing inputs are reported, not silently defaulted
    j = {k: v for k, v in i.items() if k != "fcf_margin"}
    try:
        s.run(j, dict(len1=5, len2=0, m1=1))
        raise AssertionError("missing fcf_margin not reported")
    except ValueError as e:
        assert "fcf_margin" in str(e)
    r = s.run(dict(i, g_term=.30), dict(len1=5, len2=0, m1=1))
    assert "error" in r and "must be above" in r["error"]
    try:
        s.run({k: v for k, v in i.items() if k != "target_margin"}, dict(len1=5, len2=0, m1=4, p1=dict(margin0=.2)))
        raise AssertionError("missing Method 4 inputs not reported")
    except ValueError as e:
        assert "stage 1" in str(e)
    j2 = {k: v for k, v in i.items() if k != "op_margin"}
    try:
        s.run(dict(j2, g2_end=.03), dict(len1=5, len2=5, m1=1, m2=2, g2_start=.05))
        raise AssertionError("missing stage-2 op_margin not reported")
    except ValueError as e:
        assert "op_margin (stage 2)" in str(e)
    s.run(dict(j2, g2_end=.03), dict(len1=5, len2=5, m1=1, m2=2, g2_start=.05, p2=dict(op_margin=.3, da_pct=.02, capex_pct=.03, nwc_pct=0, content_pct=0)))
    print("OK  invalid stage lengths, Method 3, missing inputs (named per stage) and WACC <= g are rejected")


def test_sensitivity_and_scenarios():
    for k in range(20):
        i = mk(k)
        i["g2_end"] = i["g_term"] + .01
        st = dict(len1=5, len2=5, m1=1, m2=2, g2_start=i["g1"] * .6, p1=dict(fcf_margin=i["fcf_margin"] * 1.1), p2=dict(op_margin=i["op_margin"] * .9))
        r = s.full(i, st)
        assert set(r["scenarios"]["Bear"]["margins"]) == {"stage 1 fcf_margin", "stage 2 op_margin"}
        close(r["sensitivity"]["grid"][2][2], r["per_share"], "sensitivity base cell")
        close(r["scenarios"]["Base"]["value"], r["per_share"], "scenario base")
        assert r["scenarios"]["Bear"]["value"] < r["scenarios"]["Base"]["value"] < r["scenarios"]["Bull"]["value"]
        g = r["sensitivity"]["grid"]
        assert all(g[a][c] is None or g[a][c] > g[a + 1][c] for a in range(4) for c in range(5) if g[a + 1][c] is not None), "value falls as WACC rises"
    print("OK  sensitivity base cell and Base scenario equal the main value; Bear < Base < Bull; value falls as WACC rises")


def test_wacc_override_reaches_grid_and_scenarios():
    for k in range(40):
        i = mk(k)
        i["g2_end"] = i["g_term"] + .01
        st = dict(len1=5, len2=5, m1=1, m2=2, g2_start=i["g1"] * .6)
        for w in (None, m.wacc_parts(i)["w_calc"] + 0.012, 0.085):
            if w is not None and w <= i["g_term"] + .015:
                continue
            r = s.full(i, st, wacc=w)
            close(r["sensitivity"]["grid"][2][2], r["per_share"], f"grid base cell with wacc={w} set {k}")
            close(r["scenarios"]["Base"]["value"], r["per_share"], f"Base scenario with wacc={w} set {k}")
            close(r["sensitivity"]["wacc"][2], r["wacc"], "grid centre is the WACC in use")
    print("OK  a WACC override is the centre of the sensitivity grid and the Base scenario (40 sets x 3 cases)")


def test_defaults_and_override_mapping():
    D = mk(2)
    D.pop("g2_end", None)
    cfg = s.default_stage_config(D)
    assert (cfg["len1"], cfg["len2"], cfg["m1"], cfg["m2"]) == (5, 5, 1, 1) and cfg["p1"] == cfg["p2"]
    close(cfg["g2_start"], D["g1"] * .6, "default stage-2 start growth")
    # nothing overridden -> defaults
    i, st, w, ex = s.apply_overrides(D, {})
    assert i == D and w is None and ex == dict(p1={}, p2={}) and st["p1"] == cfg["p1"]
    # the paste/saved-file mapping (same rules as /dcf2's paste dialog)
    ov = dict(g1=.09, growth_fade=[.075, .06, .05, .04, .03], fcf_margin=.19, target_margin=.34, margin0=.313, margin_years=5, t_end=.2, roc_cap=.33,
              tax=.17, beta=1.4, wacc1=.095, content_pct=.03, da_pct=.008, notes={"x": 1})
    i, st, w, ex = s.apply_overrides(D, ov)
    close(i["g1"], .09, "g1"); close(i["beta"], 1.4, "beta"); close(i["tax"], .17, "tax"); close(w, .095, "wacc override")
    for pk in ("p1", "p2"):
        close(st[pk]["fcf_margin"], .19, "fcf_margin both stages"); close(st[pk]["op_margin"], .34, "op_margin <- target_margin")
        close(st[pk]["roic0"], .33, "roic0 <- roc_cap"); close(st[pk]["margin0"], .313, "margin0"); close(st[pk]["t_end"], .2, "t_end")
    assert st["g2_list"] == [.075, .06, .05, .04, .03] and st["g2_start"] == .075 and st["g2_end"] == .03
    # tax falls back to t_end; flat g2; g10 sets only the end rate; an explicit stage state wins over pasted values
    i2, st2, _, _ = s.apply_overrides(D, dict(t_end=.22, g2=.04))
    close(i2["tax"], .22, "tax <- t_end"); assert st2["g2_start"] == .04 == st2["g2_end"] and "g2_list" not in st2
    i3, st3, _, _ = s.apply_overrides(D, dict(g10=.035))
    close(st3["g2_end"], .035, "g10"); close(st3["g2_start"], cfg["g2_start"], "start unchanged")
    i4, st4, _, ex4 = s.apply_overrides(D, dict(fcf_margin=.19), dict(len2=0, m1=2, p1=dict(fcf_margin=.25, op_margin=.3), g2_end=.02))
    close(st4["p1"]["fcf_margin"], .25, "explicit stage-1 margin wins"); close(st4["p2"]["fcf_margin"], .19, "pasted value kept in stage 2")
    assert st4["len2"] == 0 and st4["m1"] == 2 and abs(st4["g2_end"] - .02) < TOL
    # the mapped state runs through the engine
    s.run(i, st, wacc=w)
    print("OK  default stage set-up and the flat-override mapping behave as specified (pasted keys, fallbacks, precedence)")


def test_goal_seek():
    for k in range(40):
        i = mk(k)
        i["g2_end"] = i["g_term"] + .01
        st = dict(len1=5, len2=5, m1=1, m2=2, g2_start=i["g1"] * .6)
        g = s.implied_g1(i, st)
        if g is not None:
            assert abs(s.value(dict(i, g1=g), st) - i["price"]) < 1e-4, f"implied g1 set {k}"
        w = s.implied_wacc(i, st)
        if w is not None:
            assert abs(s.value(i, st, wacc=w) - i["price"]) < 1e-4, f"implied wacc set {k}"
    print("OK  implied growth and implied discount rate reproduce today's price (40 sets)")


def test_inputs_not_mutated():
    i = mk(5)
    i["g2_end"] = .03
    before = copy.deepcopy(i)
    s.full(i, dict(len1=10, len2=10, m1=1, m2=4, g2_start=.08))
    assert i == before
    print("OK  inputs are not modified")


if __name__ == "__main__":
    test_m1_m2_match_single_stage()
    test_m4_matches_damodaran_when_neutralised()
    test_m4_ramps_restart_in_stage_2()
    test_per_stage_inputs()
    test_mixed_methods()
    test_horizons_against_hand_calc()
    test_validation()
    test_sensitivity_and_scenarios()
    test_wacc_override_reaches_grid_and_scenarios()
    test_defaults_and_override_mapping()
    test_goal_seek()
    test_inputs_not_mutated()
    print("ALL PASSED")
