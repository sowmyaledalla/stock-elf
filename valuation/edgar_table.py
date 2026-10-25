"""Every input the DCF methodology needs, per fiscal year + TTM, straight from SEC EDGAR XBRL company facts.
Each value carries the XBRL tag and the filing (accession number) it came from so it can be looked up."""
import datetime as dt
import numpy as np
import yfinance as yf
from .data import _cached, risk_free
from .snapshot import Facts, load_facts, YEARS, D, _split_factor
from .staged import default_stage_config, default_growth_fade

T = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "RevenuesNetOfInterestExpense"],
    "opinc": ["OperatingIncomeLoss"],
    "pretax": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
               "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "tax": ["IncomeTaxExpenseBenefit"],
    "ni": ["NetIncomeLoss", "ProfitLoss"],
    "interest": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "da": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet"],
    "sbc": ["ShareBasedCompensation"],
    "dil_shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "sti": ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "debt_cur": ["DebtCurrent", "LongTermDebtCurrent", "ShortTermBorrowings", "CommercialPaper"],
    "debt_lt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "leases": ["OperatingLeaseLiability"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "assets": ["Assets"],
    "ca": ["AssetsCurrent"],
    "cl": ["LiabilitiesCurrent"],
}
BAL = ["cash", "sti", "debt_cur", "debt_lt", "leases", "equity", "assets", "ca", "cl"]
FLOW = ["revenue", "opinc", "pretax", "tax", "ni", "interest", "ocf", "capex", "da", "sbc", "dil_shares"]
M = 1e6


def _src(e):
    return None if not e else {"tag": e["tag"], "form": e.get("form"), "filed": e.get("filed"), "accn": e.get("accn"), "end": e.get("end")}


def _instant_entry(F, key, end, tol=7):
    c = [r for r in F.entries(key) if "start" not in r and abs((D(r["end"]) - D(end)).days) <= tol]
    return max(c, key=lambda r: r["filed"]) if c else None


def _latest_instant_entry(F, key, after):
    c = [r for r in F.entries(key) if "start" not in r and r["end"] >= after]
    return max(c, key=lambda r: (r["end"], r["filed"])) if c else None


def _build(ticker):
    ticker = ticker.upper()
    cik, facts = load_facts(ticker)
    F = Facts(facts.get("us-gaap", {}), T)
    ann = {k: F.annual(k) for k in FLOW}
    try:
        splits = [(d.strftime("%Y-%m-%d"), float(r)) for d, r in yf.Ticker(ticker).splits.items()]
    except Exception:
        splits = []
    ends = sorted(ann["revenue"])[-YEARS:]
    if not ends:
        raise ValueError("No annual revenue found in XBRL filings")
    last_end = ends[-1]
    cols = [{"label": e[:4], "end": e} for e in ends]
    ttm_end = last_end
    ttm = {}
    for k in FLOW:
        cur, prior, tag = F.ytd(k, last_end)
        base = ann[k].get(last_end)
        if cur and prior and base:
            ttm[k] = (base["val"] + cur["val"] - prior["val"], dict(cur, tag=tag))
            ttm_end = max(ttm_end, cur["end"])
        else:
            ttm[k] = None
    newer = ttm_end != last_end
    rows = {}
    for k in FLOW:
        vals, srcs = [], []
        for e in ends:
            a = ann[k].get(e)
            vals.append(None if not a else a["val"] * (_split_factor(splits, a["filed"]) if k == "dil_shares" else 1))
            srcs.append(_src(a))
        if newer:
            vals.append(ttm[k][0] if ttm[k] else None)
            srcs.append(_src(ttm[k][1]) if ttm[k] else None)
        else:
            vals.append(vals[-1]); srcs.append(srcs[-1])
        rows[k] = (vals, srcs)
    for k in BAL:
        vals, srcs = [], []
        for e in ends:
            en = _instant_entry(F, k, e)
            vals.append(en["val"] if en else None); srcs.append(_src(en))
        en = _latest_instant_entry(F, k, last_end) if newer else _instant_entry(F, k, last_end)
        vals.append(en["val"] if en else None); srcs.append(_src(en))
        rows[k] = (vals, srcs)
    n = len(ends) + 1
    cols.append({"label": "TTM " + ttm_end[5:7] + "-" + ttm_end[2:4], "end": ttm_end})

    def calc(fn):
        return [fn(i) for i in range(n)]
    g = lambda k, i: rows[k][0][i]
    div = lambda a, b: a / b if a is not None and b not in (None, 0) else None
    # debt = current + non-current (current portion: DebtCurrent if reported, else sum of its parts)
    debt_cur = []
    dsrc = []
    for i in range(n):
        e = ends[i] if i < len(ends) else None
        ent = []
        for tag in T["debt_cur"]:
            c = [r for u in facts.get("us-gaap", {}).get(tag, {}).get("units", {}).values() for r in u if "start" not in r and
                 abs((D(r["end"]) - D(cols[i]["end"])).days) <= (7 if i < len(ends) or not newer else 0)]
            if c:
                ent.append((tag, max(c, key=lambda r: r["filed"])))
        if ent and ent[0][0] == "DebtCurrent":
            ent = ent[:1]
        debt_cur.append(sum(x[1]["val"] for x in ent) if ent else None)
        dsrc.append(_src(dict(ent[0][1], tag="+".join(x[0] for x in ent))) if ent else None)
    rows["debt_cur"] = (debt_cur, dsrc)

    fcf = calc(lambda i: g("ocf", i) - abs(g("capex", i)) if g("ocf", i) is not None and g("capex", i) is not None else None)
    out = []

    def add(label, key, vals, unit="m", srcs=None, section="", note=""):
        out.append({"label": label, "key": key, "unit": unit, "vals": vals, "src": srcs or [None] * n, "section": section, "note": note})

    S = "Income statement"
    add("Revenue", "revenue", [None if v is None else v / M for v in rows["revenue"][0]], srcs=rows["revenue"][1], section=S)
    add("Operating income", "opinc", [None if v is None else v / M for v in rows["opinc"][0]], srcs=rows["opinc"][1], section=S)
    add("Operating margin", "op_m", calc(lambda i: div(g("opinc", i), g("revenue", i))), "pct", section=S)
    add("Income before tax", "pretax", [None if v is None else v / M for v in rows["pretax"][0]], srcs=rows["pretax"][1], section=S)
    add("Income tax expense", "tax", [None if v is None else v / M for v in rows["tax"][0]], srcs=rows["tax"][1], section=S)
    add("Effective tax rate", "tax_rate", calc(lambda i: div(g("tax", i), g("pretax", i))), "pct", section=S, note="tax ÷ income before tax")
    add("Net income", "ni", [None if v is None else v / M for v in rows["ni"][0]], srcs=rows["ni"][1], section=S)
    add("Interest expense", "interest", [None if v is None else v / M for v in rows["interest"][0]], srcs=rows["interest"][1], section=S)
    S = "Cash flow statement"
    add("Operating cash flow", "ocf", [None if v is None else v / M for v in rows["ocf"][0]], srcs=rows["ocf"][1], section=S)
    add("Capital expenditure (capex)", "capex", [None if v is None else -abs(v) / M for v in rows["capex"][0]], srcs=rows["capex"][1], section=S, note="shown negative (cash out)")
    add("Free cash flow (FCF)", "fcf", [None if v is None else v / M for v in fcf], section=S, note="operating cash flow + capex (capex is negative)")
    add("FCF margin", "fcf_m", calc(lambda i: div(fcf[i], g("revenue", i))), "pct", section=S, note="FCF ÷ revenue")
    add("Depreciation & amortization", "da", [None if v is None else v / M for v in rows["da"][0]], srcs=rows["da"][1], section=S)
    add("Stock-based compensation", "sbc", [None if v is None else v / M for v in rows["sbc"][0]], srcs=rows["sbc"][1], section=S)
    S = "Balance sheet (period end)"
    add("Cash & equivalents", "cash", [None if v is None else v / M for v in rows["cash"][0]], srcs=rows["cash"][1], section=S)
    add("Short-term investments", "sti", [None if v is None else v / M for v in rows["sti"][0]], srcs=rows["sti"][1], section=S)
    add("Short-term debt (incl. current portion)", "debt_cur", [None if v is None else v / M for v in rows["debt_cur"][0]], srcs=rows["debt_cur"][1], section=S)
    add("Long-term debt", "debt_lt", [None if v is None else v / M for v in rows["debt_lt"][0]], srcs=rows["debt_lt"][1], section=S)
    tot = calc(lambda i: (g("debt_cur", i) or 0) + (g("debt_lt", i) or 0) if g("debt_cur", i) is not None or g("debt_lt", i) is not None else None)
    add("Total debt", "debt", [None if v is None else v / M for v in tot], section=S, note="short-term + long-term (using only long-term is a common slip)")
    add("Operating lease liability (memo)", "leases", [None if v is None else v / M for v in rows["leases"][0]], srcs=rows["leases"][1], section=S, note="not included in debt")
    add("Total equity", "equity", [None if v is None else v / M for v in rows["equity"][0]], srcs=rows["equity"][1], section=S)
    add("Current assets", "ca", [None if v is None else v / M for v in rows["ca"][0]], srcs=rows["ca"][1], section=S)
    add("Current liabilities", "cl", [None if v is None else v / M for v in rows["cl"][0]], srcs=rows["cl"][1], section=S)
    nwc = calc(lambda i: (g("ca", i) - (g("cash", i) or 0) - (g("sti", i) or 0)) - (g("cl", i) - (g("debt_cur", i) or 0))
               if g("ca", i) is not None and g("cl", i) is not None else None)
    add("Operating working capital", "nwc", [None if v is None else v / M for v in nwc], section=S,
        note="(current assets - cash - ST investments) - (current liabilities - ST debt)")
    dn = calc(lambda i: nwc[i] - nwc[i - 1] if i and nwc[i] is not None and nwc[i - 1] is not None else None)
    dn[-1] = (nwc[-1] - nwc[len(ends) - 2]) if nwc[-1] is not None and len(ends) > 1 and nwc[len(ends) - 2] is not None and newer else dn[-1]
    add("Change in operating working capital", "dnwc", [None if v is None else v / M for v in dn], section=S,
        note="increase = cash tied up (a cost). TTM column = latest quarter vs last fiscal year-end")
    S = "Return on capital"
    ic = calc(lambda i: (g("equity", i) or 0) + (tot[i] or 0) + (g("leases", i) or 0) - (g("cash", i) or 0) - (g("sti", i) or 0)
              if g("equity", i) is not None else None)
    add("Invested capital", "ic", [None if v is None else v / M for v in ic], section=S, note="equity + debt + leases - cash - ST investments")
    nopat = calc(lambda i: g("opinc", i) * (1 - (div(g("tax", i), g("pretax", i)) or 0.21)) if g("opinc", i) is not None else None)
    add("NOPAT", "nopat", [None if v is None else v / M for v in nopat], section=S, note="operating income x (1 - effective tax rate)")
    add("ROIC", "roic", calc(lambda i: div(nopat[i], ic[i])), "pct", section=S, note="NOPAT / invested capital (year-end)")
    S = "Shares"
    add("Diluted weighted-average shares (M)", "dil_shares", [None if v is None else v / M for v in rows["dil_shares"][0]], "n", srcs=rows["dil_shares"][1], section=S)
    cover = [r for r in facts.get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])]
    cov = max(cover, key=lambda r: (r["end"], r["filed"])) if cover else None

    # ── market data (not on EDGAR) and defaults for the DCF
    price, beta, hist, name = None, None, {}, cik["title"].title()
    fallbacks = []
    try:
        t = yf.Ticker(ticker)
        h = t.history(period="5y", interval="1wk")["Close"].dropna()
        price = float(t.history(period="5d")["Close"].dropna().iloc[-1])
        hist = {d.strftime("%Y-%m-%d"): float(v) for d, v in h.items()}
        beta = (t.info or {}).get("beta")
    except Exception:
        pass
    try:
        rf = risk_free()
    except Exception:
        rf = 0.045
        fallbacks.append("risk_free")
    if not beta:
        fallbacks.append("beta")
    if not price:
        fallbacks.append("price")
    I = {r["key"]: r["vals"] for r in out}
    fy = [i for i in range(len(ends))]
    rev_m = I["revenue"]
    last_g = div(rev_m[len(ends) - 1], rev_m[len(ends) - 2]) if len(ends) > 1 and rev_m[len(ends) - 2] else None
    last_g = (last_g - 1) if last_g else None
    m3 = [v for v in I["fcf_m"][max(len(ends) - 3, 0):len(ends)] if v is not None]
    tr = I["tax_rate"][-1] if I["tax_rate"][-1] is not None else I["tax_rate"][len(ends) - 1]
    cash_tot = (I["cash"][-1] or 0) + (I["sti"][-1] or 0)
    shares = (cov["val"] / M) if cov else I["dil_shares"][-1]
    rv = I["revenue"]
    dn_l = I["dnwc"]; rv_chg = [(rv[k] - rv[k - 1]) if rv[k] is not None and rv[k - 1] is not None else None for k in range(1, len(ends))]
    ratios = [dn_l[k] / rv_chg[k - 1] for k in range(max(len(ends) - 3, 1), len(ends)) if dn_l[k] is not None and rv_chg[k - 1]]
    tech = {
        "op_margin": I["op_m"][-1] if I["op_m"][-1] is not None else 0.15,
        "da_pct": (I["da"][-1] or 0) / rv[-1] if rv[-1] else 0.0,
        "capex_pct": abs(I["capex"][-1] or 0) / rv[-1] if rv[-1] else 0.0,
        "nwc_pct": float(np.clip(np.mean(ratios), -0.3, 0.3)) if ratios else 0.0,
        "content_pct": 0.0,
        "roic0": float(np.clip(I["roic"][-1], 0.02, 1.5)) if I["roic"][-1] is not None else 0.15,
    }
    # Damodaran FCFF method: margin starts at today's operating margin, target defaults to the same (no ramp), tax normalises to 25%
    tech.update(margin0=tech["op_margin"], target_margin=tech["op_margin"], margin_years=5.0, t_end=0.25)
    defaults = {
        "rev0": (I["revenue"][-1] or 0) * M, "g1": float(np.clip(last_g if last_g is not None else 0.05, 0.02, 0.20)), "g10": 0.03,
        "fcf_margin": float(np.mean(m3)) if m3 else 0.10, "rf": rf, "beta": float(beta) if beta else 1.0, "erp": 0.0423,
        "kd": rf + 0.01, "tax": float(np.clip(tr, 0.10, 0.28)) if tr is not None else 0.21, "g_term": 0.025,
        **tech, "price": price, "shares": (shares or 0) * M, "debt": (I["debt"][-1] or 0) * M, "cash": cash_tot * M,
    }
    filings = {}
    for r in out:
        for s in r["src"]:
            if s and s.get("accn"):
                filings[s["accn"]] = {"accn": s["accn"], "form": s["form"], "filed": s["filed"], "end": s["end"],
                                      "url": f"https://www.sec.gov/Archives/edgar/data/{cik['cik_str']}/{s['accn'].replace('-', '')}/"}
    return {"ticker": ticker, "name": name, "cik": cik["cik_str"], "cols": [c["label"] for c in cols], "ends": [c["end"] for c in cols],
            "rows": out, "defaults": defaults, "price_hist": hist, "last_growth": last_g,
            "shares_source": ({"tag": "dei:EntityCommonStockSharesOutstanding", "form": "cover page", "filed": cov["filed"], "accn": cov.get("accn"), "end": cov["end"]} if cov else None),
            "filings": sorted(filings.values(), key=lambda f: f["filed"], reverse=True),
            "fallbacks": fallbacks, "stage_defaults": dict(default_stage_config(defaults), growth_fade_default=default_growth_fade(defaults)), "market_note": "Price, beta and risk-free rate are market data, not in EDGAR: price/beta from yfinance, 10-year Treasury yield (^TNX). ERP default is Damodaran's published figure; edit it."}


def edgar_table(ticker):
    return _cached(f"edgartable_{ticker.upper()}.json", 6, lambda: _build(ticker))
