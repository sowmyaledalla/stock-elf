"""Quick-review financial snapshot (10 fiscal years + TTM): Financials, Profitability, Financial Health, Valuation.
Statements come from SEC EDGAR XBRL company facts; only prices (for the valuation multiples) come from yfinance."""
import datetime as dt
import requests
import yfinance as yf
from .data import _cached

import os
HDR = {"User-Agent": os.environ.get("SEC_USER_AGENT", "StockElf open-source-user@example.com")}
YEARS = 10

TAGS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "RevenuesNetOfInterestExpense"],
    "cogs": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "gross": ["GrossProfit"],
    "opinc": ["OperatingIncomeLoss"],
    "ni": ["NetIncomeLoss", "ProfitLoss"],
    "eps": ["EarningsPerShareDiluted"],
    "dps": ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"],
    "shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "assets": ["Assets"],
    "ca": ["AssetsCurrent"],
    "cl": ["LiabilitiesCurrent"],
    "ltd": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
}
PER_SHARE = {"eps", "dps", "shares", "dil_shares"}  # taken as first reported, then adjusted for later splits
D = dt.date.fromisoformat


def _days(a, b):
    return (D(b) - D(a)).days


class Facts:
    def __init__(self, gaap, tags=None):
        self.g = gaap
        self.tags = tags or TAGS

    def entries(self, key):
        out = []
        for tag in self.tags[key]:
            for unit, rows in self.g.get(tag, {}).get("units", {}).items():
                out += [dict(r, tag=tag) for r in rows]
        return out

    def annual(self, key):
        """{fy_end: entry}: 10-K, ~12-month duration; restated (latest filed) unless per-share (first filed)."""
        best = {}
        for tag in self.tags[key]:
            by_end = {}
            for unit, rows in self.g.get(tag, {}).get("units", {}).items():
                for r in rows:
                    if r.get("form", "").startswith("10-K") and "start" in r and 350 <= _days(r["start"], r["end"]) <= 380:
                        by_end.setdefault(r["end"], []).append(dict(r, tag=tag))
            for end, rs in by_end.items():
                if end not in best:  # earlier tags win per period
                    best[end] = (min if key in PER_SHARE else max)(rs, key=lambda r: r["filed"])
        return best

    def instant(self, key, end, tol=7):
        """Balance-sheet value at (or within tol days of) `end`, latest filed."""
        cands = [r for r in self.entries(key) if "start" not in r and abs(_days(r["end"], end)) <= tol]
        return max(cands, key=lambda r: r["filed"])["val"] if cands else None

    def latest_instant(self, key, after):
        cands = [r for r in self.entries(key) if "start" not in r and r["end"] >= after]
        if not cands:
            return None, None
        r = max(cands, key=lambda r: (r["end"], r["filed"]))
        return r["val"], r["end"]

    def ytd(self, key, fy_end):
        """Year-to-date flow since the last fiscal year end, from the newest 10-Q, plus the same span a year earlier."""
        start = (D(fy_end) + dt.timedelta(days=1)).isoformat()
        for tag in self.tags[key]:
            rows = [r for u in self.g.get(tag, {}).get("units", {}).values() for r in u if "start" in r and r.get("form") == "10-Q"]
            cur = [r for r in rows if abs(_days(start, r["start"])) <= 5 and r["end"] > fy_end]
            if not cur:
                continue
            c = max(cur, key=lambda r: (r["end"], r["filed"]))
            prior = [r for r in rows if abs(_days(r["start"], start) - 365) <= 6 and abs(_days(r["end"], c["end"]) - 365) <= 6]
            if prior:
                return c, max(prior, key=lambda r: r["filed"]), tag
        return None, None, None


def _split_factor(splits, filed):
    f = 1.0
    for d, ratio in splits:
        if d > filed:
            f *= ratio
    return f


def _price_on(hist, end):
    s = hist[hist.index <= end]
    return float(s.iloc[-1]) if len(s) else None


def _div(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def load_facts(ticker):
    """(company dict, full XBRL company-facts 'facts' dict) from SEC EDGAR; the 3.5MB download is cached for a day."""
    ticker = ticker.upper()

    def f():
        cik = next((v for v in requests.get("https://www.sec.gov/files/company_tickers.json", headers=HDR, timeout=20).json().values()
                    if v["ticker"] == ticker), None)
        if not cik:
            raise ValueError(f"{ticker} not found in the SEC ticker list")
        j = requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik['cik_str']:010d}.json", headers=HDR, timeout=60).json()
        return {"cik": cik, "facts": j["facts"]}
    r = _cached(f"facts_{ticker}.json", 24, f)
    return r["cik"], r["facts"]


def _build(ticker):
    ticker = ticker.upper()
    cik, facts = load_facts(ticker)
    j = {"facts": facts}
    F = Facts(j["facts"].get("us-gaap", {}))
    ann = {k: F.annual(k) for k in TAGS}
    ends = sorted(ann["revenue"])[-YEARS:]
    if not ends:
        raise ValueError("No annual revenue found in XBRL filings")
    last_end = ends[-1]

    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="max", auto_adjust=False)["Close"].dropna()
        hist.index = hist.index.tz_localize(None).strftime("%Y-%m-%d")
        splits = [(d.strftime("%Y-%m-%d"), float(r)) for d, r in t.splits.items()]
    except Exception:
        hist, splits = None, []

    # one column per fiscal year, then TTM
    cols = []
    for e in ends:
        c = {"label": e[:4], "end": e}
        for k in TAGS:
            a = ann[k].get(e)
            if a is None:
                c[k] = None
            elif k in PER_SHARE:
                c[k] = a["val"] * (_split_factor(splits, a["filed"]) if k == "shares" else 1) / (_split_factor(splits, a["filed"]) if k != "shares" else 1)
            else:
                c[k] = a["val"]
        for k in ("assets", "ca", "cl", "ltd", "equity"):
            c[k] = F.instant(k, e)
        c["price"] = _price_on(hist, e) if hist is not None else None
        cols.append(c)

    ttm = {"label": "TTM", "end": last_end}
    got = set()
    for k in TAGS:
        if k in ("assets", "ca", "cl", "ltd", "equity"):
            continue
        cur, prior, tag = F.ytd(k, last_end)
        base = ann[k].get(last_end)
        if cur and prior and base:
            ttm[k] = base["val"] + cur["val"] - prior["val"] if k not in ("shares",) else cur["val"]
            ttm["end"] = cur["end"]
            got.add(k)
        else:
            ttm[k] = None if cur else cols[-1][k]
    if ttm["end"] != last_end:
        for k in set(TAGS) - got - {"assets", "ca", "cl", "ltd", "equity"}:
            ttm[k] = None  # no year-to-date figure in the 10-Q: don't pass off the last annual value as TTM
        for k in ("assets", "ca", "cl", "ltd", "equity"):
            ttm[k], _ = F.latest_instant(k, last_end)
        ttm["prev_assets"], ttm["prev_equity"] = (F.instant("assets", (D(ttm["end"]) - dt.timedelta(days=365)).isoformat(), 20),
                                                  F.instant("equity", (D(ttm["end"]) - dt.timedelta(days=365)).isoformat(), 20))
    else:
        for k in ("assets", "ca", "cl", "ltd", "equity"):
            ttm[k] = cols[-1][k]
    ttm["price"] = float(hist.iloc[-1]) if hist is not None and len(hist) else None
    ttm["label"] = "TTM"
    ttm["period"] = ttm["end"][5:7] + "-" + ttm["end"][2:4]
    cols.append(ttm)

    for n, c in enumerate(cols):
        prev = cols[n - 1] if n and cols[n - 1] is not ttm else None
        pa = c.get("prev_assets") or (cols[n - 1]["assets"] if n else None)
        pe = c.get("prev_equity") or (cols[n - 1]["equity"] if n else None)
        if c is ttm and ttm["end"] == last_end:
            pa, pe = cols[-3]["assets"] if len(cols) > 2 else None, cols[-3]["equity"] if len(cols) > 2 else None
        avg = lambda a, b: (a + b) / 2 if a is not None and b is not None else a
        aa, ae = avg(c["assets"], pa), avg(c["equity"], pe)
        gross = c["gross"] if c["gross"] is not None else (c["revenue"] - c["cogs"] if c["revenue"] and c["cogs"] is not None else None)
        capex = -abs(c["capex"]) if c["capex"] is not None else None
        c["d"] = {
            "revenue": c["revenue"], "gross_m": _div(gross, c["revenue"]), "opinc": c["opinc"], "op_m": _div(c["opinc"], c["revenue"]),
            "ni": c["ni"], "eps": c["eps"], "dps": c["dps"], "shares": c["shares"],
            "bvps": _div(c["equity"], c["shares"]), "ocf": c["ocf"], "capex": capex,
            "fcf": c["ocf"] + capex if c["ocf"] is not None and capex is not None else None,
            "roa": _div(c["ni"], aa), "roe": _div(c["ni"], ae), "turn": _div(c["revenue"], aa), "net_m": _div(c["ni"], c["revenue"]),
            "lev": _div(aa, ae), "ltd": c["ltd"], "equity": c["equity"], "de": _div(c["ltd"], c["equity"]),
            "wc": c["ca"] - c["cl"] if c["ca"] is not None and c["cl"] is not None else None,
        }
        mcap = c["price"] * c["shares"] if c["price"] and c["shares"] else None
        pos = lambda x: x if x is not None and x > 0 else None
        c["d"].update({
            "mcap": mcap, "pe": _div(c["price"], pos(c["eps"])), "ps": _div(mcap, c["revenue"]),
            "pb": _div(c["price"], pos(c["d"]["bvps"])), "pcf": _div(mcap, pos(c["ocf"])),
        })

    M = 1e6
    spec = [
        ("Financials (USD)", [
            ("Revenue $Mil", "revenue", "m"), ("Gross Margin %", "gross_m", "pct"), ("Oper Income $Mil", "opinc", "m"),
            ("Operating Margin %", "op_m", "pct"), ("Net Income $Mil", "ni", "m"), ("Earnings Per Share $", "eps", "ps"),
            ("Dividends $", "dps", "ps"), ("Shares Mil", "shares", "m"), ("Book Value Per Share $", "bvps", "ps"),
            ("Oper Cash Flow $Mil", "ocf", "m"), ("Cap Spending $Mil", "capex", "m"), ("Free Cash Flow $Mil", "fcf", "m")]),
        ("Profitability", [
            ("Return on Assets %", "roa", "pct"), ("Return on Equity %", "roe", "pct"), ("Asset Turnover", "turn", "x2"),
            ("Net Margin %", "net_m", "pct"), ("Financial Leverage", "lev", "x1")]),
        ("Financial Health (USD)", [
            ("Long-Term Debt $Mil", "ltd", "m"), ("Total Equity $Mil", "equity", "m"), ("Debt/Equity", "de", "x2"),
            ("Working Capital $Mil", "wc", "m")]),
        ("Valuation", [
            ("Market Cap $Mil", "mcap", "m"), ("Price/Earnings", "pe", "x1"), ("Price/Sales", "ps", "x1"),
            ("Price/Book", "pb", "x1"), ("Price/Cash Flow", "pcf", "x1")]),
    ]
    scale = {"revenue", "opinc", "ni", "shares", "ocf", "capex", "fcf", "ltd", "equity", "wc", "mcap"}
    sections = []
    for title, rows in spec:
        sections.append({"title": title, "rows": [
            {"label": lab, "fmt": f, "vals": [(c["d"][k] / M if k in scale and c["d"][k] is not None else c["d"][k]) for c in cols]}
            for lab, k, f in rows]})
    return {"ticker": ticker, "name": cik["title"].title(), "cik": cik["cik_str"],
            "cols": [c["label"] if c is not ttm else "TTM " + ttm["period"] for c in cols],
            "price": ttm["price"], "sections": sections,
            "notes": ["Source: SEC EDGAR XBRL company facts (10-K annual data; TTM = latest fiscal year + year-to-date from 10-Qs, balance sheet from the newest 10-Q).",
                      "Prices for the valuation multiples are year-end closes from yfinance; per-share figures are first-reported, adjusted for later splits.",
                      "ROA/ROE/turnover/leverage use average of opening and closing balances. Debt/Equity = long-term debt / equity. Working capital = current assets - current liabilities.",
                      "A dash means the company did not report the item under a standard XBRL tag."]}


def snapshot(ticker):
    return _cached(f"snapshot_{ticker.upper()}.json", 6, lambda: _build(ticker))
