"""Fetch layer: yfinance (market + TTM) and edgartools (10y annual history), cached per day.
Finviz is used as a fallback when yfinance is missing critical fields (price, market cap, margins)."""
import json, time, datetime as dt
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf


def _finviz_fallback(ticker: str, pack: dict) -> dict:
    """Fill missing critical fields in pack from Finviz snapshot. Returns pack (mutated in place)."""
    missing = [k for k in ("price", "mcap", "revenue", "ebit") if not pack.get(k) or (isinstance(pack[k], float) and np.isnan(pack[k]))]
    if not missing:
        return pack
    try:
        import sys, os
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from functions.finvizfinance_api import _scrape_finviz_fundament
        fz = _scrape_finviz_fundament(ticker)

        def _fnum(s):
            """Parse Finviz value string → float (handles B/M/K suffixes and % signs)."""
            if not s or s in ('-', 'N/A', ''): return None
            s = s.strip().replace(',', '')
            try:
                if s.endswith('%'): return float(s[:-1]) / 100
                mult = {'B': 1e9, 'M': 1e6, 'K': 1e3}.get(s[-1])
                if mult: return float(s[:-1]) * mult
                return float(s)
            except ValueError:
                return None

        # Market data
        if not pack.get('price'):
            pack['price'] = _fnum(fz.get('Price'))
        if not pack.get('mcap'):
            pack['mcap'] = _fnum(fz.get('Market Cap'))
        if not pack.get('shares') and pack.get('mcap') and pack.get('price'):
            pack['shares'] = int(pack['mcap'] / pack['price'])
        if not pack.get('beta_raw'):
            pack['beta_raw'] = _fnum(fz.get('Beta'))
        if not pack.get('eps'):
            pack['eps'] = _fnum(fz.get('EPS (ttm)')) or _fnum(fz.get('EPS'))
        if not pack.get('pe'):
            pack['pe'] = _fnum(fz.get('P/E'))
        if not pack.get('name') or pack['name'] == ticker:
            pack['name'] = fz.get('Company', ticker)
        if not pack.get('sector'):
            pack['sector'] = fz.get('Sector')
        if not pack.get('industry'):
            pack['industry'] = fz.get('Industry')

        # Income statement — derive revenue + EBIT from Finviz margin + market data
        op_margin = _fnum(fz.get('Oper. Margin')) or _fnum(fz.get('Operating Margin'))
        sales = _fnum(fz.get('Sales'))  # some Finviz pages have TTM sales
        if not pack.get('revenue') or np.isnan(pack['revenue']):
            if sales:
                pack['revenue'] = sales
            elif op_margin and pack.get('mcap') and _fnum(fz.get('P/S')):
                ps = _fnum(fz.get('P/S'))
                pack['revenue'] = pack['mcap'] / ps if ps else None
        if (not pack.get('ebit') or np.isnan(pack['ebit'])) and pack.get('revenue') and op_margin:
            pack['ebit'] = pack['revenue'] * op_margin

        # Balance sheet proxies
        if not pack.get('debt') or np.isnan(pack['debt']):
            de = _fnum(fz.get('Debt/Eq'))
            eq = pack.get('equity')
            if de is not None and eq and not np.isnan(eq):
                pack['debt'] = de * eq

        pack['_finviz_fallback'] = list(missing)  # log which fields were filled
    except Exception as e:
        pack['_finviz_fallback_error'] = str(e)
    return pack

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache" / "valuation"
CACHE.mkdir(parents=True, exist_ok=True)
ERP = 4.5 / 100  # equity risk premium; change here or via --erp


def _cached(name, ttl_h, fn):
    p = CACHE / name
    if p.exists() and time.time() - p.stat().st_mtime < ttl_h * 3600:
        return json.loads(p.read_text())
    v = fn()
    p.write_text(json.dumps(v, default=float))
    return v


def _row(df, *names):
    """First matching row of a yfinance statement as a Series (latest column first)."""
    for n in names:
        if n in df.index:
            return df.loc[n]
    return pd.Series(dtype=float)


def _ttm(df, *names):
    r = _row(df, *names).dropna()
    return float(r.iloc[:4].sum()) if len(r) >= 4 else float("nan")


def _latest(df, *names):
    r = _row(df, *names).dropna()
    return float(r.iloc[0]) if len(r) else float("nan")


def risk_free():
    def f():
        return float(yf.Ticker("^TNX").history(period="5d")["Close"].dropna().iloc[-1]) / 100
    return _cached("rf.json", 6, f)


def edgar_history(ticker):
    """Annual revenue / operating income / net income, up to 10y, from SEC XBRL."""
    def f():
        try:
            from functions.edgar_api import _fetch_edgar, _xbrl_series
            inc, _, _ = _fetch_edgar(ticker)
            rev = _xbrl_series(inc, ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                                     "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"])
            op = _xbrl_series(inc, ["OperatingIncomeLoss"])
            ni = _xbrl_series(inc, ["NetIncomeLoss", "ProfitLoss"])
            return {"revenue": {int(k): v for k, v in rev.items()},
                    "op_income": {int(k): v for k, v in op.items()},
                    "net_income": {int(k): v for k, v in ni.items()}}
        except Exception as e:
            return {"error": str(e), "revenue": {}, "op_income": {}, "net_income": {}}
    return _cached(f"edgar_{ticker}.json", 24 * 7, f)


def company_pack(ticker):
    ticker = ticker.upper()

    def f():
        yf_err = None
        pack = None
        try:
            s = yf.Ticker(ticker)
            info = s.info
            if not info or not info.get("regularMarketPrice") and not info.get("currentPrice") and not info.get("marketCap"):
                raise ValueError(f"yfinance returned empty info for {ticker}")
            qi, qb, qc = s.quarterly_income_stmt, s.quarterly_balance_sheet, s.quarterly_cashflow
            rev, ebit = _ttm(qi, "Total Revenue"), _ttm(qi, "Operating Income", "EBIT")
            pretax, tax = _ttm(qi, "Pretax Income"), _ttm(qi, "Tax Provision")
            pack = dict(
                ticker=ticker, name=info.get("shortName", ticker), sector=info.get("sector"),
                industry=info.get("industry"), price=info.get("currentPrice") or info.get("regularMarketPrice"),
                shares=info.get("sharesOutstanding"), mcap=info.get("marketCap"), beta_raw=info.get("beta"),
                revenue=rev, ebit=ebit, net_income=_ttm(qi, "Net Income"), eps=info.get("trailingEps"),
                interest=abs(_ttm(qi, "Interest Expense")), pretax=pretax, tax=tax,
                capex=_ttm(qc, "Capital Expenditure"), da=_ttm(qc, "Depreciation And Amortization",
                                                             "Depreciation Amortization Depletion"),
                d_wc=_ttm(qc, "Change In Working Capital"), fcf=_ttm(qc, "Free Cash Flow"),
                debt=_latest(qb, "Total Debt"), cash=_latest(qb, "Cash Cash Equivalents And Short Term Investments"),
                equity=_latest(qb, "Stockholders Equity", "Common Stock Equity"),
                goodwill=_latest(qb, "Goodwill And Other Intangible Assets", "Goodwill"),
                book_ps=info.get("bookValue"), pe=info.get("trailingPE"),
                as_of=str(qi.columns[0].date()) if len(qi.columns) else None,
            )
            try:
                re_ = s.revenue_estimate
                pack["rev_est"] = {k: float(re_.loc[k, "growth"]) for k in ("0y", "+1y") if k in re_.index}
            except Exception:
                pack["rev_est"] = {}
            try:
                h = s.history(period="5y", interval="1wk")["Close"].dropna()
                pack["price_hist"] = {str(i.date()): float(v) for i, v in h.items()}
            except Exception:
                pack["price_hist"] = {}
        except Exception as e:
            yf_err = str(e)

        # If yfinance failed entirely, try building a minimal pack from Finviz
        if pack is None:
            try:
                import sys as _sys
                _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
                from functions.finvizfinance_api import _scrape_finviz_fundament
                fz = _scrape_finviz_fundament(ticker)

                def _fnum(s):
                    if not s or s in ('-', 'N/A', ''): return None
                    s = s.strip().replace(',', '')
                    try:
                        if s.endswith('%'): return float(s[:-1]) / 100
                        mult = {'B': 1e9, 'M': 1e6, 'K': 1e3}.get(s[-1])
                        if mult: return float(s[:-1]) * mult
                        return float(s)
                    except ValueError:
                        return None

                price = _fnum(fz.get('Price'))
                mcap  = _fnum(fz.get('Market Cap'))
                op_m  = _fnum(fz.get('Oper. Margin')) or _fnum(fz.get('Operating Margin'))
                sales = _fnum(fz.get('Sales'))
                ps    = _fnum(fz.get('P/S'))
                rev_fz = sales or (mcap / ps if mcap and ps else None)
                ebit_fz = (rev_fz * op_m) if rev_fz and op_m else None
                shares = int(mcap / price) if mcap and price else None
                pack = dict(
                    ticker=ticker, name=fz.get('Company', ticker),
                    sector=fz.get('Sector'), industry=fz.get('Industry'),
                    price=price, shares=shares, mcap=mcap,
                    beta_raw=_fnum(fz.get('Beta')), eps=_fnum(fz.get('EPS (ttm)')) or _fnum(fz.get('EPS')),
                    pe=_fnum(fz.get('P/E')), book_ps=_fnum(fz.get('Book/sh')),
                    revenue=rev_fz, ebit=ebit_fz,
                    net_income=None, interest=None, pretax=None, tax=None,
                    capex=None, da=None, d_wc=None, fcf=None,
                    debt=None, cash=_fnum(fz.get('Cash/sh')) * shares if _fnum(fz.get('Cash/sh')) and shares else None,
                    equity=None, goodwill=None, as_of=None, rev_est={}, price_hist={},
                    _source='finviz', _yf_error=yf_err,
                )
            except Exception as fz_err:
                raise RuntimeError(f"yfinance failed ({yf_err}); Finviz fallback also failed ({fz_err})")

        _finviz_fallback(ticker, pack)  # fill any remaining missing fields
        return pack

    pack = _cached(f"pack_{ticker}_{dt.date.today()}.json", 12, f)
    pack["edgar"] = edgar_history(ticker)
    pack["rf"] = risk_free()
    return pack
