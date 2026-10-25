"""Normalise pasted DCF inputs (company-narrative skill output, or inputs/<T>.json) into calculator overrides."""
import json, re

# pasted key -> calculator key (same-name keys pass through)
ALIASES = {"revenue": "rev0", "operating_margin": "margin0", "sales_to_capital": "s2c", "risk_free": "rf",
           "wacc": "wacc1", "wacc_terminal": "wacc10", "tax_end": "t_end", "cost_debt": "kd"}
PASS = {"g1", "target_margin", "margin_years", "beta", "erp", "g_term", "t_end", "shares", "debt", "cash", "moat",
        "moat_years", "rev0", "margin0", "s2c", "rf", "wacc1", "wacc10", "roc_cap", "growth_fade",
        "fcf_margin", "g10", "traj", "price", "p_fail", "liq_ps", "op_margin", "da_pct", "capex_pct", "nwc_pct", "content_pct", "roic0", "roic_term", "tax", "kd"}
CURVE_RANGE = {"growth": (-0.6, 1.5), "op_margin": (-1.0, 1.0), "tax": (-0.2, 0.6), "da_pct": (0.0, 1.0), "capex_pct": (0.0, 1.0), "nwc_pct": (-2.0, 2.0)}
SCALAR_RANGE = {"g_term": (-0.05, 0.08), "rf": (0.0, 0.2), "beta": (0.0, 4.0), "erp": (0.0, 0.15), "kd": (0.0, 0.3), "tax": (0.0, 0.6), "p_fail": (0.0, 1.0), "price": (0.0, 1e6)}
STAGES = ("young", "growth", "mature", "declining")
EXPECTED = ["stage", "rev0", "traj.growth", "traj.op_margin", "traj.tax", "traj.da_pct", "traj.capex_pct", "traj.nwc_pct", "g_term", "rf", "beta", "erp",
            "kd", "tax", "price", "shares", "debt", "cash", "p_fail", "liq_ps"]   # the keys a complete paste carries
UNUSED = {"stage", "g2", "beta_terminal", "debt_weight", "base_year", "base_is_forecast", "other_adjustments"}


def parse_text(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:  # prose around the block: take the outermost braces
        a, b = t.find("{"), t.rfind("}")
        if a < 0 or b <= a:
            raise ValueError("No JSON object found in the pasted text.")
        try:
            return json.loads(t[a:b + 1])
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")


def normalize(raw):
    """Returns (overrides, ticker, warnings). Rates are decimals, dollar amounts raw, as in the paste."""
    warns, ov = [], {}
    raw = dict(raw)
    ticker = (raw.pop("ticker", None) or "").upper().strip()
    notes = raw.pop("notes", None)
    for k, v in raw.items():
        if v is None:
            continue
        k = ALIASES.get(k, k)
        if k in PASS:
            ov[k] = v
        elif k not in UNUSED and k != "short_term_investments":
            warns.append(f"Ignored unknown key '{k}'.")
    if "short_term_investments" in raw and raw["short_term_investments"] is not None:
        if "cash" in ov or "cash" in raw:
            ov["cash"] = (ov.get("cash") or 0) + raw["short_term_investments"]
            warns.append("short_term_investments added to cash.")
        else:
            warns.append("short_term_investments ignored: no cash given to add it to.")
    if isinstance(ov.get("roc_cap"), dict):
        rc = ov["roc_cap"]
        ov["roc_cap"] = rc.get("current_proxy")
        if ov["roc_cap"] is None:
            del ov["roc_cap"]
        if rc.get("terminal") is not None:
            warns.append("roc_cap.terminal not used: return on capital always fades to terminal WACC.")
    if "g2" in raw and raw["g2"] is not None:  # flat growth for the second growth stage (years 6-10 by default)
        ov["g2"] = raw["g2"]
        gt = ov.get("g_term", raw.get("g_term"))
        if gt is not None:  # the original /dcf model reads it as year-6 growth fading linearly to g_term by year 10
            ov["growth_fade"] = [raw["g2"] + (gt - raw["g2"]) * n / 4 for n in range(5)]
        warns.append("g2 = Stage 2 growth: a flat rate on /dcf2; in the original /dcf model, year-6 growth fading to g_term by year 10.")
    fade = ov.get("growth_fade")
    if fade is not None and (not isinstance(fade, list) or len(fade) != 5):
        warns.append("growth_fade must have 5 values (years 6-10); ignored.")
        del ov["growth_fade"]
    for k in ("moat",):
        if k in ov and ov[k] not in ("none", "narrow", "wide"):
            warns.append(f"moat '{ov[k]}' is not none/narrow/wide; ignored.")
            del ov[k]
    tj = ov.get("traj")
    if tj is not None:
        good = {}
        for k, v in (tj.items() if isinstance(tj, dict) else []):
            if v is None:
                continue                                                     # null curve = not supported: the page keeps its default
            if not (isinstance(v, list) and len(v) == 10 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)):
                warns.append(f"traj.{k} must be 10 numbers; ignored.")
                continue
            lo, hi = CURVE_RANGE.get(k, (None, None))
            if lo is None:
                warns.append(f"traj.{k} is not a known driver; ignored.")
                continue
            if any(x < lo or x > hi for x in v):
                warns.append(f"traj.{k} has values outside {lo:.0%}..{hi:.0%} (check units: 0.06 = 6%); ignored.")
                continue
            good[k] = v
        if good:
            ov["traj"] = good
        else:
            del ov["traj"]
    for k, v in list(ov.items()):
        if k not in ("moat", "growth_fade", "traj") and not isinstance(v, (int, float)):
            warns.append(f"'{k}' is not a number; ignored.")
            del ov[k]
    if raw.get("wacc") is None and raw.get("debt_weight") is not None:
        warns.append("debt_weight ignored: the debt weight is computed from debt and market cap.")
    if isinstance(notes, dict):
        ov["notes"] = notes
    return ov, ticker, warns


def normalize_full(raw):
    """normalize() plus what the pages show after a paste: the life-cycle stage and a completeness report.
    Returns (overrides, ticker, warnings, meta) with meta = {stage, applied, missing, out_of_range}."""
    ov, ticker, warns = normalize(raw)
    stage = raw.get("stage")
    if stage is not None and stage not in STAGES:
        warns.append(f"stage '{stage}' is not one of {', '.join(STAGES)}; ignored.")
        stage = None
    out_of_range = []
    for k, (lo, hi) in SCALAR_RANGE.items():
        if k in ov and not lo <= ov[k] <= hi:
            out_of_range.append(k)
            warns.append(f"{k} = {ov[k]} is outside {lo}..{hi} (check units: rates are decimals, dollars raw); applied anyway.")
    have = set(ov) | {f"traj.{k}" for k in ov.get("traj", {})} | ({"stage"} if stage else set())
    have = {("rev0" if k == "revenue" else k) for k in have}
    applied = [k for k in EXPECTED if k in have]
    missing = [k for k in EXPECTED if k not in have]
    return ov, ticker, warns, dict(stage=stage, applied=applied, missing=missing, out_of_range=out_of_range, total=len(EXPECTED))
