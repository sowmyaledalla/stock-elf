"""
EDGAR-based fundamental data fetcher for Rule 1 analysis.
Fetches 10 years of annual financials from SEC EDGAR via edgartools,
computes EPS, Revenue, Equity, FCF, ROIC, and PE (via yfinance year-end prices).
"""

import numpy as np
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from edgar import Company, set_identity

import os
SEC_IDENTITY = os.environ.get("SEC_USER_AGENT", "StockElf open-source-user@example.com")  # SEC asks for a contact; set SEC_USER_AGENT to your own
set_identity(SEC_IDENTITY)

# ── EDGAR helpers ────────────────────────────────────────────────────────────

def _fy_columns(df):
    """Return only the 'FY XXXX' data columns from an EDGAR dataframe."""
    return [c for c in df.columns if str(c).startswith("FY ")]


def _parse_year(col_label):
    """'FY 2024' -> 2024"""
    try:
        return int(str(col_label).split()[-1])
    except Exception:
        return None


def _xbrl_series(df, tags):
    """
    Try XBRL tag candidates in order; return first match as a
    year-indexed (int) pd.Series, dropping NaN values.
    Handles duplicate index entries (some filers repeat tags).
    """
    if df is None or df.empty:
        return pd.Series(dtype=float)
    fy_cols = _fy_columns(df)
    for tag in tags:
        if tag not in df.index:
            continue
        raw = df.loc[tag, fy_cols]
        # Duplicate tag rows → DataFrame; keep the first row
        if isinstance(raw, pd.DataFrame):
            raw = raw.iloc[0]
        result = {}
        for col in fy_cols:
            year = _parse_year(col)
            if year is None:
                continue
            val = raw[col]
            # val might itself be a Series if columns are duplicated
            if isinstance(val, pd.Series):
                val = val.iloc[0]
            val = pd.to_numeric(val, errors="coerce")
            if not np.isnan(float(val)):
                result[year] = float(val)
        if result:
            return pd.Series(result).sort_index()
    return pd.Series(dtype=float)


def _fetch_edgar(ticker):
    """Pull annual income, balance sheet, and cash flow from EDGAR."""
    company = Company(ticker)
    inc = company.income_statement(periods=10, period="annual", as_dataframe=True)
    bal = company.balance_sheet(periods=10, period="annual", as_dataframe=True)
    cf  = company.cash_flow_statement(periods=10, period="annual", as_dataframe=True)
    return inc, bal, cf


# ── Growth computation ────────────────────────────────────────────────────────

def _compute_growth(series, col):
    """
    Given a year-indexed Series, build a DataFrame with:
      col, col_growth_pcent, del_year
    del_year = years back from most recent year.
    """
    s = series.dropna().sort_index()
    if s.empty:
        return pd.DataFrame()
    maxyear = s.index.max()
    df = s.rename(col).to_frame()
    df["del_year"] = maxyear - df.index

    def _pcent_growth(row):
        dy = row["del_year"]
        if dy == 0:
            return 0.0
        base = row[col]
        top  = df.loc[maxyear, col]
        if base == 0 or np.isnan(base):
            return np.nan
        ratio = top / base
        return np.sign(ratio) * (abs(ratio) ** (1 / dy) - 1)

    df[col + "_growth_pcent"] = df.apply(_pcent_growth, axis=1)
    return df


# ── Plotly figure builders (match existing rule1estimations.py API) ───────────

def _growth_plots(series, col, label, reqd=0.15):
    """Bar (absolute) + Scatter (CAGR back n years), same structure as makeGrowthPlots."""
    df = _compute_growth(series, col)
    if df.empty:
        fig = go.Figure()
        return {"data": fig.data, "layout": fig.layout}

    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=(label, label + " CAGR by look-back"))
    fig.add_trace(go.Bar(x=df.index, y=df[col], name=label,
                         marker_color="#3b82f6"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["del_year"], y=df[col + "_growth_pcent"],
                             name="CAGR", line=dict(color="#10b981", width=2)),
                  row=1, col=2)
    fig.add_trace(go.Scatter(x=[0, 12], y=[reqd, reqd],
                             name="Target 15%", line=dict(color="#ef4444", width=1, dash="dash")),
                  row=1, col=2)
    fig.update_xaxes(title_text="Year", row=1, col=1)
    fig.update_xaxes(title_text="Years back", row=1, col=2)
    fig.update_yaxes(title_text=label, row=1, col=1)
    fig.update_yaxes(title_text="CAGR", tickformat=".1%", row=1, col=2)
    fig.update_layout(height=380, margin=dict(t=40, b=30, l=30, r=20),
                      paper_bgcolor="white", plot_bgcolor="#f8fafc",
                      legend=dict(orientation="h", y=-0.15))
    return {"data": fig.data, "layout": fig.layout}


_COL_LABELS = {
    "eps":        ("EPS ($)",       "EPS Growth (%)"),
    "revenue":    ("Revenue ($M)",  "Revenue Growth (%)"),
    "equity":     ("Equity ($M)",   "Equity Growth (%)"),
    "fcf":        ("FCF ($M)",      "FCF Growth (%)"),
    "pe_series":  ("P/E Ratio",     "P/E Change (%)"),
}

def _datatable(df, col, value_scale=1.0, value_fmt=None):
    """Plotly table: Year | Years Back | Value | CAGR %"""
    gdf = _compute_growth(df, col)
    if gdf.empty:
        fig = go.Figure()
        return {"data": fig.data, "layout": fig.layout}

    display = gdf.copy()
    display.index.name = "Year"
    display = display.reset_index().sort_values("Year", ascending=False)
    display[col] = (display[col] / value_scale).round(2)
    display[col + "_growth_pcent"] = (display[col + "_growth_pcent"] * 100).round(2)

    val_label, growth_label = _COL_LABELS.get(col, (col.replace("_", " ").title(), "Growth (%)"))
    header_vals = ["Year", "Years Back", val_label, growth_label]
    cell_vals = [
        display["Year"],
        display["del_year"],
        display[col],
        display[col + "_growth_pcent"],
    ]

    fig = go.Figure(data=[go.Table(
        header=dict(values=header_vals, fill_color="#1e293b", font_color="white",
                    align="left", font_size=11),
        cells=dict(values=cell_vals, fill_color=["#f8fafc", "#ffffff"],
                   align="left", font_size=11),
    )])
    fig.update_layout(height=320, margin=dict(t=10, b=10, l=10, r=10))
    return {"data": fig.data, "layout": fig.layout}


def _roic_figure(roic_series):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=roic_series.index, y=roic_series.values,
                             name="ROIC", line=dict(color="#3b82f6", width=3),
                             mode="lines+markers"))
    fig.add_shape(type="line", x0=roic_series.index.min(), x1=roic_series.index.max(),
                  y0=0.1, y1=0.1, line=dict(color="#ef4444", width=1, dash="dash"))
    fig.update_yaxes(tickformat=".1%")
    fig.update_layout(height=320, margin=dict(t=20, b=30, l=30, r=20),
                      paper_bgcolor="white", plot_bgcolor="#f8fafc",
                      legend=dict(orientation="h", y=-0.2))
    return {"data": fig.data, "layout": fig.layout}


def _pe_figure(pe_series):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pe_series.index, y=pe_series.values,
                             name="P/E (year-end)", line=dict(color="#f59e0b", width=3),
                             mode="lines+markers"))
    fig.add_shape(type="line", x0=pe_series.index.min(), x1=pe_series.index.max(),
                  y0=15, y1=15, line=dict(color="#94a3b8", width=1, dash="dot"))
    fig.update_layout(height=320, margin=dict(t=20, b=30, l=30, r=20),
                      paper_bgcolor="white", plot_bgcolor="#f8fafc",
                      legend=dict(orientation="h", y=-0.2))
    return {"data": fig.data, "layout": fig.layout}


def _debt_figure(ltd_series, fcf_series, debt_eq_series):
    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=("Long-Term Debt vs FCF ($M)", "Debt/Equity Ratio"))
    if not ltd_series.empty:
        fig.add_trace(go.Bar(x=ltd_series.index, y=ltd_series / 1e6,
                             name="LT Debt", marker_color="#ef4444"), row=1, col=1)
    if not fcf_series.empty:
        fig.add_trace(go.Scatter(x=fcf_series.index, y=fcf_series / 1e6,
                                 name="FCF", line=dict(color="#10b981", width=2)),
                      row=1, col=1)
    if not debt_eq_series.empty:
        fig.add_trace(go.Scatter(x=debt_eq_series.index, y=debt_eq_series.values,
                                 name="Debt/Equity", line=dict(color="#f59e0b", width=2)),
                      row=1, col=2)
    fig.update_layout(height=320, margin=dict(t=40, b=30, l=30, r=20),
                      paper_bgcolor="white", plot_bgcolor="#f8fafc",
                      legend=dict(orientation="h", y=-0.2))
    return {"data": fig.data, "layout": fig.layout}


# ── Historical PE via yfinance ────────────────────────────────────────────────

def _historical_pe(ticker, eps_by_year):
    """
    Fetch year-end closing prices from yfinance; compute PE = price / EPS per year.
    """
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="10y")
        if hist.empty:
            return pd.Series(dtype=float)
        hist.index = hist.index.tz_localize(None)
        pe = {}
        for year, eps in eps_by_year.items():
            if np.isnan(eps) or eps <= 0:
                continue
            yr_data = hist[hist.index.year == year]
            if yr_data.empty:
                continue
            price = float(yr_data["Close"].iloc[-1])
            pe[year] = round(price / eps, 2)
        return pd.Series(pe).sort_index()
    except Exception:
        return pd.Series(dtype=float)


# ── Main entry point ─────────────────────────────────────────────────────────

def edgar_getFundamentalPlots(ticker):
    """
    Drop-in replacement for rule1estimations.getFundamentalPlots().
    Returns the same figure dict structure, sourced from SEC EDGAR + yfinance.
    """
    ticker = ticker.upper()
    inc, bal, cf = _fetch_edgar(ticker)

    # ── Raw series ───────────────────────────────────────────────────────────
    revenue = _xbrl_series(inc, [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ])

    eps = _xbrl_series(inc, [
        "EarningsPerShareDiluted", "EarningsPerShareBasic",
    ])

    net_income = _xbrl_series(inc, [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ])

    shares = _xbrl_series(inc, [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ])

    # Compute EPS from Net Income / Shares if EarningsPerShareDiluted missing
    if eps.empty and not net_income.empty and not shares.empty:
        common = net_income.index.intersection(shares.index)
        if len(common) > 0:
            eps = (net_income[common] / shares[common]).round(4)

    equity = _xbrl_series(bal, [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "CommonStockholdersEquity",
    ])

    ltd = _xbrl_series(bal, [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "LongTermDebtAndCapitalLeaseObligations",
    ])

    cash_bal = _xbrl_series(bal, [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments",
    ])

    total_assets = _xbrl_series(bal, ["Assets"])
    liabilities  = _xbrl_series(bal, ["Liabilities"])

    op_cf = _xbrl_series(cf, ["NetCashProvidedByUsedInOperatingActivities"])

    capex = _xbrl_series(cf, [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "CapitalExpendituresIncurredButNotYetPaid",
    ]).abs()

    ebit = _xbrl_series(inc, [
        "OperatingIncomeLoss",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    ])

    tax_exp  = _xbrl_series(inc, ["IncomeTaxExpenseBenefit"])
    pretax   = _xbrl_series(inc, [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
    ])
    if not pretax.empty and not tax_exp.empty:
        common_t = pretax.index.intersection(tax_exp.index)
        tax_rate = float((tax_exp[common_t] / pretax[common_t]).clip(0, 0.5).mean())
    else:
        tax_rate = 0.21

    # ── Derived series ───────────────────────────────────────────────────────

    # FCF = Operating CF - CapEx
    if not op_cf.empty and not capex.empty:
        common_fcf = op_cf.index.intersection(capex.index)
        fcf = op_cf[common_fcf] - capex[common_fcf]
    elif not op_cf.empty:
        fcf = op_cf.copy()
    else:
        fcf = pd.Series(dtype=float)

    # ROIC = EBIT*(1-t) / (LTD + Equity - Cash)
    if not ebit.empty and not equity.empty:
        ic_series = ltd + equity - cash_bal
        common_r = ebit.index.intersection(ic_series.index)
        if len(common_r) > 0:
            roic_series = (ebit[common_r] * (1 - tax_rate)) / ic_series[common_r].abs().replace(0, np.nan)
        else:
            roic_series = pd.Series(dtype=float)
    else:
        roic_series = pd.Series(dtype=float)

    # Debt/Equity
    if not ltd.empty and not equity.empty:
        common_de = ltd.index.intersection(equity.index)
        debt_eq = (ltd[common_de] / equity[common_de].replace(0, np.nan)).round(3)
    else:
        debt_eq = pd.Series(dtype=float)

    # Historical PE
    pe_series = _historical_pe(ticker, eps) if not eps.empty else pd.Series(dtype=float)

    # ── Build figures ────────────────────────────────────────────────────────
    figures = {}

    figures["returnOnCapitalEmployed"] = _roic_figure(roic_series) if not roic_series.empty else \
        {"data": go.Figure().data, "layout": go.Figure().layout}

    figures["priceEarningsRatio"] = _pe_figure(pe_series) if not pe_series.empty else \
        {"data": go.Figure().data, "layout": go.Figure().layout}

    figures["debt"] = _debt_figure(ltd, fcf, debt_eq)

    figures["eps"]     = _growth_plots(eps,     "eps",     "EPS (Diluted, $)")
    figures["revenue"] = _growth_plots(revenue, "revenue", "Revenue ($)")
    figures["equity"]  = _growth_plots(equity,  "equity",  "Stockholders Equity ($)")
    figures["cash"]    = _growth_plots(fcf,     "fcf",     "Free Cash Flow ($)")

    # Data tables (values in millions for large numbers, raw for EPS)
    figures["epsdiluted-table"]                    = _datatable(eps,     "eps")
    figures["revenue-table"]                       = _datatable(revenue, "revenue", value_scale=1e6)
    figures["totalStockholdersEquity-table"]       = _datatable(equity,  "equity",  value_scale=1e6)
    figures["freeCashFlow-table"]                  = _datatable(fcf,     "fcf",     value_scale=1e6)
    figures["priceEarningsRatio-table"]            = _datatable(pe_series, "pe_series") if not pe_series.empty else \
        {"data": go.Figure().data, "layout": go.Figure().layout}

    # max year for display
    all_years = [s.index.max() for s in [revenue, eps, equity, fcf] if not s.empty]
    figures["max_year"] = int(max(all_years)) if all_years else "N/A"
    figures["data_source"] = "SEC EDGAR"

    return figures


# ── Buffett Thumbrules ────────────────────────────────────────────────────────

def _scorecard_entry(label, series, threshold, direction="above", benchmark_str="", fmt=".1%"):
    """
    Build one scorecard dict for a ratio series.
    direction: "above" means passing = value >= threshold
               "below" means passing = value <= threshold
    """
    s = series.dropna().sort_index()
    if s.empty:
        return {"parameter": label, "benchmark": benchmark_str,
                "latest": "—", "score": 0, "total": 0, "pct": 0, "status": "na"}
    total = len(s)
    if direction == "above":
        score = int((s >= threshold).sum())
    else:
        score = int((s <= threshold).sum())
    pct = score / total if total else 0

    # Format latest value
    latest_val = float(s.iloc[-1])
    if fmt == ".1%":
        latest_str = f"{latest_val*100:.1f}%"
    elif fmt == ".2f":
        latest_str = f"{latest_val:.2f}"
    elif fmt == "$B":
        latest_str = f"${latest_val/1e9:.1f}B"
    else:
        latest_str = f"{latest_val:.2f}"

    status = "pass" if pct >= 0.7 else ("warn" if pct >= 0.4 else "fail")
    return {
        "parameter": label,
        "benchmark": benchmark_str,
        "latest": latest_str,
        "score": score,
        "total": total,
        "pct": round(pct * 100),
        "status": status,
        "series": s,           # kept for trend charts, stripped before JSON
    }


def edgar_buffettScreeningReport(ticker):
    """
    EDGAR-sourced Buffett Thumbrules Scorecard.
    Returns figure dict with scorecard list + trend charts + indicators table.
    """
    ticker = ticker.upper()
    inc, bal, cf = _fetch_edgar(ticker)

    # ── Raw series ───────────────────────────────────────────────────────────
    revenue      = _xbrl_series(inc, ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"])
    gross_profit = _xbrl_series(inc, ["GrossProfit"])
    net_income   = _xbrl_series(inc, ["NetIncomeLoss", "ProfitLoss"])
    op_income    = _xbrl_series(inc, ["OperatingIncomeLoss"])
    sga          = _xbrl_series(inc, ["SellingGeneralAndAdministrativeExpense",
                                      "SellingAndMarketingExpense"])
    rnd          = _xbrl_series(inc, ["ResearchAndDevelopmentExpense"])
    interest     = _xbrl_series(inc, ["InterestExpense", "InterestExpenseDebt"]).abs()
    tax_exp      = _xbrl_series(inc, ["IncomeTaxExpenseBenefit"])
    pretax       = _xbrl_series(inc, [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"])
    da           = _xbrl_series(cf, ["DepreciationDepletionAndAmortization"])
    capex        = _xbrl_series(cf, ["PaymentsToAcquirePropertyPlantAndEquipment"]).abs()

    cash_bal     = _xbrl_series(bal, ["CashAndCashEquivalentsAtCarryingValue",
                                      "CashCashEquivalentsAndShortTermInvestments"])
    ltd          = _xbrl_series(bal, ["LongTermDebtNoncurrent", "LongTermDebt"])
    ltd_cur      = _xbrl_series(bal, ["LongTermDebtCurrent"])
    total_liab   = _xbrl_series(bal, ["Liabilities"])
    equity       = _xbrl_series(bal, ["StockholdersEquity",
                                      "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"])
    retained     = _xbrl_series(bal, ["RetainedEarningsAccumulatedDeficit"])
    preferred    = _xbrl_series(bal, ["PreferredStockValue",
                                      "PreferredStockSharesAuthorized"])

    # ── Derived ratios ───────────────────────────────────────────────────────
    def _ratio(num, den, scale=1.0, abs_den=False):
        if num.empty or den.empty:
            return pd.Series(dtype=float)
        common = num.index.intersection(den.index)
        d = den[common].abs() if abs_den else den[common]
        return (num[common] / d.replace(0, np.nan) * scale).round(4)

    gross_margin   = _ratio(gross_profit, revenue)
    net_margin     = _ratio(net_income,   revenue)
    sga_margin     = _ratio(sga,          gross_profit)
    rnd_margin     = _ratio(rnd,          gross_profit)
    da_margin      = _ratio(da,           gross_profit)
    interest_margin= _ratio(interest,     op_income, abs_den=True)
    tax_rate       = _ratio(tax_exp,      pretax).clip(0, 0.6)
    capex_margin   = _ratio(capex,        net_income, abs_den=True)
    debt_eq        = _ratio(total_liab,   equity, abs_den=True)

    # Total debt = LT debt + current portion
    if not ltd.empty and not ltd_cur.empty:
        common_d = ltd.index.intersection(ltd_cur.index)
        total_debt = ltd.reindex(common_d).fillna(0) + ltd_cur.reindex(common_d).fillna(0)
    elif not ltd.empty:
        total_debt = ltd.copy()
    else:
        total_debt = pd.Series(dtype=float)

    # Cash > Debt flag (1 = pass, 0 = fail) per year
    if not cash_bal.empty and not total_debt.empty:
        common_cd = cash_bal.index.intersection(total_debt.index)
        cash_gt_debt = (cash_bal[common_cd] > total_debt[common_cd]).astype(float)
    else:
        cash_gt_debt = pd.Series(dtype=float)

    # Preferred stock check (0 = no preferred = pass)
    if not preferred.empty:
        pref_ok = (preferred < 1).astype(float)
    else:
        # If tag absent, assume no preferred stock → pass
        pref_ok = pd.Series(dtype=float)

    # ── Scorecard entries ────────────────────────────────────────────────────
    rules = [
        _scorecard_entry("Gross Margin",          gross_margin,    0.40, "above", "≥ 40%",  ".1%"),
        _scorecard_entry("SG&A / Gross Profit",   sga_margin,      0.30, "below", "≤ 30%",  ".1%"),
        _scorecard_entry("R&D / Gross Profit",     rnd_margin,      0.30, "below", "≤ 30%",  ".1%"),
        _scorecard_entry("D&A / Gross Profit",     da_margin,       0.25, "below", "≤ 25%",  ".1%"),
        _scorecard_entry("Interest / Op. Income",  interest_margin, 0.15, "below", "< 15%",  ".1%"),
        _scorecard_entry("Effective Tax Rate",     tax_rate,        0.35, "below", "< 35%",  ".1%"),
        _scorecard_entry("Net Profit Margin",      net_margin,      0.20, "above", "≥ 20%",  ".1%"),
        _scorecard_entry("Cash > Total Debt",      cash_gt_debt,    0.99, "above", "Cash > Debt", ".2f"),
        _scorecard_entry("Debt / Equity",          debt_eq,         0.80, "below", "≤ 0.80", ".2f"),
        _scorecard_entry("No Preferred Stock",     pref_ok,         0.99, "above", "= 0",    ".2f"),
        _scorecard_entry("CapEx / Net Income",     capex_margin,    0.25, "below", "< 25%",  ".1%"),
    ]

    # Pull series out before JSON serialisation
    series_map = {r["parameter"]: r.pop("series", pd.Series(dtype=float)) for r in rules}

    # ── Trend charts ─────────────────────────────────────────────────────────
    figures = {}

    figures["margins_chart"] = _line_figure(
        {"Gross Margin": gross_margin, "Net Margin": net_margin},
        colors=["#10b981", "#3b82f6"], y_fmt=".1%")

    figures["sga_rnd_chart"] = _line_figure(
        {"SG&A / GP": sga_margin, "R&D / GP": rnd_margin, "D&A / GP": da_margin},
        colors=["#f59e0b", "#a855f7", "#64748b"], y_fmt=".1%")

    figures["leverage_chart"] = _line_figure(
        {"Debt / Equity": debt_eq, "Interest / Op. Income": interest_margin},
        colors=["#ef4444", "#f59e0b"], y_fmt=".2f")

    figures["capex_tax_chart"] = _line_figure(
        {"CapEx / Net Income": capex_margin, "Tax Rate": tax_rate},
        colors=["#3b82f6", "#64748b"], y_fmt=".1%")

    # ── Indicators data table ─────────────────────────────────────────────────
    all_idx = sorted(set().union(*[s.index for s in series_map.values() if not s.empty]))
    ind_df = pd.DataFrame(index=all_idx)
    ind_df.index.name = "year"
    label_map = {
        "Gross Margin":         gross_margin,
        "Net Margin":           net_margin,
        "SG&A / Gross Profit":  sga_margin,
        "R&D / Gross Profit":   rnd_margin,
        "D&A / Gross Profit":   da_margin,
        "Interest / Op Income": interest_margin,
        "Tax Rate":             tax_rate,
        "CapEx / Net Income":   capex_margin,
        "Debt / Equity":        debt_eq,
        "Cash ($B)":            cash_bal / 1e9 if not cash_bal.empty else pd.Series(dtype=float),
        "Total Debt ($B)":      total_debt / 1e9 if not total_debt.empty else pd.Series(dtype=float),
        "Retained Earnings ($B)": retained / 1e9 if not retained.empty else pd.Series(dtype=float),
    }
    for col_name, s in label_map.items():
        ind_df[col_name] = s.reindex(all_idx)
    ind_df = ind_df.round(4)

    figures["buffett_indicators"] = _fool_datatable(ind_df)
    # Raw records for the interactive dropdown section
    raw = ind_df.reset_index()
    raw.columns = [str(c) for c in raw.columns]
    figures["indicators_raw"]     = raw.where(pd.notna(raw), None).to_dict(orient="records")
    figures["indicators_columns"] = [c for c in ind_df.columns.tolist()]
    figures["scorecard"]  = rules
    figures["max_year"]   = int(max(all_idx)) if all_idx else "N/A"
    figures["data_source"]= "SEC EDGAR"

    return figures


# ── Motley Fool Workbook ──────────────────────────────────────────────────────

def _line_figure(series_dict, title="", y_fmt=None, colors=None, height=300):
    """Multi-series line chart. series_dict = {label: pd.Series}."""
    default_colors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#a855f7"]
    fig = go.Figure()
    for i, (label, s) in enumerate(series_dict.items()):
        if s.empty:
            continue
        clr = (colors or default_colors)[i % len(default_colors)]
        fig.add_trace(go.Scatter(x=s.index, y=s.values, name=label,
                                 line=dict(color=clr, width=2), mode="lines+markers"))
    fig.update_layout(height=height, margin=dict(t=30, b=30, l=30, r=20),
                      paper_bgcolor="white", plot_bgcolor="#f8fafc",
                      legend=dict(orientation="h", y=-0.25))
    if y_fmt:
        fig.update_yaxes(tickformat=y_fmt)
    return {"data": fig.data, "layout": fig.layout}


def _bar_line_figure(bar_series, line_series, bar_label, line_label,
                     bar_color="#3b82f6", line_color="#10b981", height=300):
    """Bar chart with an optional overlaid line."""
    fig = go.Figure()
    if not bar_series.empty:
        fig.add_trace(go.Bar(x=bar_series.index, y=bar_series.values / 1e9,
                             name=bar_label, marker_color=bar_color, opacity=0.8))
    if not line_series.empty:
        fig.add_trace(go.Scatter(x=line_series.index, y=line_series.values / 1e9,
                                 name=line_label, line=dict(color=line_color, width=2),
                                 mode="lines+markers"))
    fig.update_yaxes(title_text="$B")
    fig.update_layout(height=height, margin=dict(t=30, b=30, l=30, r=20),
                      paper_bgcolor="white", plot_bgcolor="#f8fafc",
                      legend=dict(orientation="h", y=-0.25),
                      barmode="group")
    return {"data": fig.data, "layout": fig.layout}


def _fool_datatable(df):
    """Full Motley Fool data table, indexed by year."""
    if df is None or df.empty:
        fig = go.Figure()
        return {"data": fig.data, "layout": fig.layout}
    display = df.copy().sort_index(ascending=False).reset_index()
    display.columns = [c.replace("_", " ").title() for c in display.columns]
    # round floats
    for c in display.columns:
        if display[c].dtype == float:
            display[c] = display[c].round(4)
    fig = go.Figure(data=[go.Table(
        header=dict(values=list(display.columns),
                    fill_color="#1e293b", font_color="white",
                    align="left", font_size=10),
        cells=dict(values=[display[c] for c in display.columns],
                   fill_color=["#f8fafc", "#ffffff"],
                   align="left", font_size=10),
    )])
    fig.update_layout(height=350, margin=dict(t=10, b=10, l=10, r=10))
    return {"data": fig.data, "layout": fig.layout}


def edgar_MotleyFoolWorkbook(ticker):
    """
    EDGAR-sourced Motley Fool Workbook.
    Returns same figure key structure as rule1estimations.MotleyFoolWorkbook().
    """
    ticker = ticker.upper()
    inc, bal, cf = _fetch_edgar(ticker)

    # ── Raw series ───────────────────────────────────────────────────────────
    revenue = _xbrl_series(inc, [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues", "SalesRevenueNet",
    ])
    cost_of_rev = _xbrl_series(inc, [
        "CostOfGoodsAndServicesSold", "CostOfRevenue",
        "CostOfGoodsAndServicesSoldDepreciation",
    ])
    gross_profit = _xbrl_series(inc, ["GrossProfit"])
    net_income   = _xbrl_series(inc, ["NetIncomeLoss", "ProfitLoss"])
    tax_exp      = _xbrl_series(inc, ["IncomeTaxExpenseBenefit"])
    pretax       = _xbrl_series(inc, [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
    ])

    cash_bal      = _xbrl_series(bal, [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments",
    ])
    ltd           = _xbrl_series(bal, [
        "LongTermDebtNoncurrent", "LongTermDebt",
    ])
    inventory     = _xbrl_series(bal, ["InventoryNet", "Inventories"])
    receivables   = _xbrl_series(bal, [
        "AccountsReceivableNetCurrent", "ReceivablesNetCurrent",
    ])
    payables      = _xbrl_series(bal, [
        "AccountsPayableCurrent", "AccountsPayable",
    ])
    current_assets = _xbrl_series(bal, ["AssetsCurrent"])
    current_liab   = _xbrl_series(bal, ["LiabilitiesCurrent"])

    op_cf  = _xbrl_series(cf, ["NetCashProvidedByUsedInOperatingActivities"])
    capex  = _xbrl_series(cf, ["PaymentsToAcquirePropertyPlantAndEquipment"]).abs()

    # ── Derived ratios (aligned by year) ────────────────────────────────────
    def _safe_ratio(num, den, scale=1.0):
        if num.empty or den.empty:
            return pd.Series(dtype=float)
        common = num.index.intersection(den.index)
        return (num[common] / den[common].replace(0, np.nan) * scale).round(4)

    gross_margin     = _safe_ratio(gross_profit, revenue)
    net_margin       = _safe_ratio(net_income,   revenue)
    cost_ratio       = _safe_ratio(cost_of_rev,  revenue)
    tax_rate         = _safe_ratio(tax_exp, pretax).clip(0, 0.6)
    inv_days         = _safe_ratio(inventory,   revenue, scale=365)
    rec_days         = _safe_ratio(receivables, revenue, scale=365)
    pay_days         = _safe_ratio(payables,    revenue, scale=365)

    # Flow Ratio = (Current Assets - Cash) / Current Liabilities
    if not current_assets.empty and not cash_bal.empty and not current_liab.empty:
        common_fr = current_assets.index.intersection(cash_bal.index).intersection(current_liab.index)
        flow_ratio = ((current_assets[common_fr] - cash_bal[common_fr])
                      / current_liab[common_fr].replace(0, np.nan)).round(3)
    else:
        flow_ratio = pd.Series(dtype=float)

    # FCF for reference
    if not op_cf.empty and not capex.empty:
        common_fcf = op_cf.index.intersection(capex.index)
        fcf = op_cf[common_fcf] - capex[common_fcf]
    else:
        fcf = op_cf.copy() if not op_cf.empty else pd.Series(dtype=float)

    # ── Latest scalar summary values ─────────────────────────────────────────
    def _latest(s):
        return float(s.iloc[-1]) if not s.empty else None

    summary = {
        "gross_margin":  _latest(gross_margin),
        "net_margin":    _latest(net_margin),
        "flow_ratio":    _latest(flow_ratio),
        "cash_B":        _latest(cash_bal) / 1e9 if _latest(cash_bal) else None,
        "ltd_B":         _latest(ltd) / 1e9 if _latest(ltd) else None,
        "cost_ratio":    _latest(cost_ratio),
        "tax_rate":      _latest(tax_rate),
    }

    # ── Combined DataFrame for data table ───────────────────────────────────
    all_idx = sorted(set(revenue.index) | set(gross_margin.index) | set(net_margin.index))
    fool_df = pd.DataFrame(index=all_idx)
    fool_df.index.name = "year"

    def _align(s):
        return s.reindex(fool_df.index)

    fool_df["revenue_$B"]       = _align(revenue) / 1e9
    fool_df["cost_of_rev_$B"]   = _align(cost_of_rev) / 1e9
    fool_df["gross_profit_$B"]  = _align(gross_profit) / 1e9
    fool_df["net_income_$B"]    = _align(net_income) / 1e9
    fool_df["gross_margin"]     = _align(gross_margin)
    fool_df["net_margin"]       = _align(net_margin)
    fool_df["cost_ratio"]       = _align(cost_ratio)
    fool_df["tax_rate"]         = _align(tax_rate)
    fool_df["cash_$B"]          = _align(cash_bal) / 1e9
    fool_df["ltd_$B"]           = _align(ltd) / 1e9
    fool_df["op_cf_$B"]         = _align(op_cf) / 1e9
    fool_df["fcf_$B"]           = _align(fcf) / 1e9
    fool_df["inv_days"]         = _align(inv_days)
    fool_df["rec_days"]         = _align(rec_days)
    fool_df["pay_days"]         = _align(pay_days)
    fool_df["flow_ratio"]       = _align(flow_ratio)
    fool_df = fool_df.round(3)

    # ── Build figures ────────────────────────────────────────────────────────
    figures = {}

    # Balance sheet
    figures["cash"]  = _line_figure({"Cash": cash_bal}, colors=["#3b82f6"])
    figures["debt"]  = _bar_line_figure(ltd, fcf, "LT Debt", "FCF",
                                        bar_color="#ef4444", line_color="#10b981")
    figures["inventory_payments"] = _line_figure(
        {"Inventory Days": inv_days, "Receivable Days": rec_days, "Payable Days": pay_days},
        colors=["#f59e0b", "#3b82f6", "#10b981"])
    figures["flowRatio"] = _line_figure({"Flow Ratio": flow_ratio}, colors=["#a855f7"])

    # Income statement
    figures["revenue"]     = _bar_line_figure(revenue, cost_of_rev,
                                              "Revenue", "Cost of Revenue",
                                              bar_color="#3b82f6", line_color="#ef4444")
    figures["costOfSales"] = _line_figure({"Cost of Sales Ratio": cost_ratio}, colors=["#ef4444"])
    figures["grossMargin"] = _line_figure({"Gross Margin": gross_margin,
                                           "Net Margin": net_margin},
                                          colors=["#10b981", "#3b82f6"], y_fmt=".1%")
    figures["tax"]         = _line_figure({"Tax Rate": tax_rate}, colors=["#f59e0b"], y_fmt=".1%")

    # Cash flow
    figures["netCash"]     = _bar_line_figure(op_cf, fcf,
                                              "Operating CF", "Free Cash Flow",
                                              bar_color="#10b981", line_color="#3b82f6")

    # Data table
    figures["fooldata"] = _fool_datatable(fool_df)

    # Summary for chips
    figures["summary"] = summary

    all_years = [s.index.max() for s in [revenue, gross_margin, op_cf] if not s.empty]
    figures["max_year"]    = int(max(all_years)) if all_years else "N/A"
    figures["data_source"] = "SEC EDGAR"

    return figures


# ── Financial Ratios Dashboard ────────────────────────────────────────────────

def _ratio_series(num: pd.Series, den: pd.Series, scale: float = 1.0) -> pd.Series:
    """Compute num/den on common years; returns empty Series on failure."""
    if num.empty or den.empty:
        return pd.Series(dtype=float)
    common = num.index.intersection(den.index)
    if len(common) == 0:
        return pd.Series(dtype=float)
    result = (num[common] / den[common].replace(0, np.nan) * scale).dropna()
    return result.round(4)


def _ratio_table(ratios: dict) -> dict:
    """
    Build a Plotly table showing each ratio's most recent value and 5-year avg.
    ratios = {label: pd.Series(year-indexed)}
    """
    rows = []
    for label, s in ratios.items():
        if s.empty:
            continue
        s = s.sort_index()
        latest_yr  = int(s.index.max())
        latest_val = s.iloc[-1]
        avg5       = float(s.tail(5).mean())
        rows.append((label, latest_yr, latest_val, avg5))

    if not rows:
        return {"data": go.Figure().data, "layout": go.Figure().layout}

    fig = go.Figure(data=[go.Table(
        columnwidth=[200, 80, 100, 100],
        header=dict(
            values=["<b>Ratio</b>", "<b>Year</b>", "<b>Latest</b>", "<b>5-yr Avg</b>"],
            fill_color="#f8fafc", font=dict(size=12, color="#64748b"),
            align="left", line_color="#e2e8f0",
        ),
        cells=dict(
            values=[
                [r[0] for r in rows],
                [r[1] for r in rows],
                [f"{r[2]:.2f}" for r in rows],
                [f"{r[3]:.2f}" for r in rows],
            ],
            fill_color="white", align="left",
            font=dict(size=11, color="#1e293b"),
            line_color="#f1f5f9", height=28,
        ),
    )])
    fig.update_layout(margin=dict(t=10, b=10, l=0, r=0), height=min(80 + len(rows) * 30, 400))
    return {"data": fig.data, "layout": fig.layout}


def edgar_financial_ratios(ticker: str) -> dict:
    """
    Compute and plot financial ratios over 10 years from SEC EDGAR data.

    Categories
    ----------
    Profitability : Gross Margin, Operating Margin, Net Margin, ROE, ROA, ROIC
    Liquidity     : Current Ratio, Quick Ratio, Cash Ratio
    Debt          : Debt/Equity, Debt/Assets, Interest Coverage, Net Debt/EBITDA
    Efficiency    : Asset Turnover, FCF Margin, Operating CF Margin
    Valuation     : P/E, P/B, P/S  (yfinance year-end prices)
    """
    ticker = ticker.upper()
    inc, bal, cf = _fetch_edgar(ticker)

    # ── Raw series ────────────────────────────────────────────────────────────
    revenue = _xbrl_series(inc, [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues", "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ])
    gross_profit = _xbrl_series(inc, ["GrossProfit"])
    op_income    = _xbrl_series(inc, ["OperatingIncomeLoss"])
    net_income   = _xbrl_series(inc, [
        "NetIncomeLoss", "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ])
    interest_exp = _xbrl_series(inc, [
        "InterestExpense", "InterestAndDebtExpense",
        "InterestExpenseDebt",
    ]).abs()
    tax_exp  = _xbrl_series(inc, ["IncomeTaxExpenseBenefit"])
    pretax   = _xbrl_series(inc, [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"
    ])

    equity        = _xbrl_series(bal, [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ])
    total_assets  = _xbrl_series(bal, ["Assets"])
    total_liab    = _xbrl_series(bal, ["Liabilities"])
    current_assets = _xbrl_series(bal, ["AssetsCurrent"])
    current_liab   = _xbrl_series(bal, ["LiabilitiesCurrent"])
    inventory      = _xbrl_series(bal, ["InventoryNet"])
    cash           = _xbrl_series(bal, [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsAndShortTermInvestments",
    ])
    ltd = _xbrl_series(bal, [
        "LongTermDebtNoncurrent", "LongTermDebt",
        "LongTermDebtAndCapitalLeaseObligations",
    ])
    shares = _xbrl_series(inc, [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ])

    op_cf = _xbrl_series(cf, ["NetCashProvidedByUsedInOperatingActivities"])
    capex = _xbrl_series(cf, [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "CapitalExpendituresIncurredButNotYetPaid",
    ]).abs()
    da    = _xbrl_series(cf, [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
    ])

    eps = _xbrl_series(inc, ["EarningsPerShareDiluted", "EarningsPerShareBasic"])
    if eps.empty and not net_income.empty and not shares.empty:
        common = net_income.index.intersection(shares.index)
        eps = (net_income[common] / shares[common]).round(4)

    # FCF
    if not op_cf.empty and not capex.empty:
        common_fcf = op_cf.index.intersection(capex.index)
        fcf = op_cf[common_fcf] - capex[common_fcf]
    else:
        fcf = op_cf.copy()

    # EBIT for interest coverage & EBITDA
    ebit = op_income.copy()
    ebitda = pd.Series(dtype=float)
    if not ebit.empty and not da.empty:
        c = ebit.index.intersection(da.index)
        ebitda = ebit[c] + da[c]

    # Tax rate
    if not pretax.empty and not tax_exp.empty:
        ct = pretax.index.intersection(tax_exp.index)
        tax_rate = float((tax_exp[ct] / pretax[ct]).clip(0, 0.5).mean())
    else:
        tax_rate = 0.21

    # ROIC = EBIT*(1-t) / IC
    roic_series = pd.Series(dtype=float)
    if not ebit.empty and not equity.empty:
        ic = (ltd.reindex(equity.index, fill_value=0)
              + equity
              - cash.reindex(equity.index, fill_value=0))
        c = ebit.index.intersection(ic.index)
        if len(c):
            roic_series = (ebit[c] * (1 - tax_rate) / ic[c].abs().replace(0, np.nan)).round(4)

    # ── Profitability ratios ──────────────────────────────────────────────────
    gross_margin = _ratio_series(gross_profit, revenue, scale=100)
    op_margin    = _ratio_series(op_income,    revenue, scale=100)
    net_margin   = _ratio_series(net_income,   revenue, scale=100)
    roe          = _ratio_series(net_income,   equity,  scale=100)
    roa          = _ratio_series(net_income,   total_assets, scale=100)
    roic_pct     = (roic_series * 100).round(2) if not roic_series.empty else pd.Series(dtype=float)

    prof_ratios = {
        "Gross Margin %":     gross_margin,
        "Operating Margin %": op_margin,
        "Net Margin %":       net_margin,
        "ROE %":              roe,
        "ROA %":              roa,
        "ROIC %":             roic_pct,
    }

    # ── Liquidity ratios ──────────────────────────────────────────────────────
    current_ratio = _ratio_series(current_assets, current_liab)

    quick_assets = pd.Series(dtype=float)
    if not current_assets.empty and not inventory.empty:
        c = current_assets.index.intersection(inventory.index)
        quick_assets = current_assets[c] - inventory[c]
    elif not current_assets.empty:
        quick_assets = current_assets.copy()
    quick_ratio = _ratio_series(quick_assets, current_liab)
    cash_ratio  = _ratio_series(cash, current_liab)

    liq_ratios = {
        "Current Ratio": current_ratio,
        "Quick Ratio":   quick_ratio,
        "Cash Ratio":    cash_ratio,
    }

    # ── Debt ratios ───────────────────────────────────────────────────────────
    debt_equity     = _ratio_series(ltd,        equity,      scale=1)
    debt_assets     = _ratio_series(total_liab, total_assets, scale=1)
    interest_cov    = _ratio_series(ebit,       interest_exp, scale=1)
    net_debt_ebitda = pd.Series(dtype=float)
    if not ltd.empty and not cash.empty and not ebitda.empty:
        c = ltd.index.intersection(cash.index).intersection(ebitda.index)
        nd = ltd[c] - cash[c]
        net_debt_ebitda = (nd / ebitda[c].replace(0, np.nan)).round(3)

    debt_ratios = {
        "Debt / Equity":       debt_equity,
        "Debt / Assets":       debt_assets,
        "Interest Coverage":   interest_cov,
        "Net Debt / EBITDA":   net_debt_ebitda,
    }

    # ── Efficiency ratios ─────────────────────────────────────────────────────
    asset_turnover = _ratio_series(revenue, total_assets)
    fcf_margin     = _ratio_series(fcf,     revenue, scale=100)
    ocf_margin     = _ratio_series(op_cf,   revenue, scale=100)

    eff_ratios = {
        "Asset Turnover":    asset_turnover,
        "FCF Margin %":      fcf_margin,
        "Op. CF Margin %":   ocf_margin,
    }

    # ── Valuation ratios (yfinance prices) ───────────────────────────────────
    pe_series = _historical_pe(ticker, eps) if not eps.empty else pd.Series(dtype=float)

    pb_series = pd.Series(dtype=float)
    ps_series = pd.Series(dtype=float)
    try:
        tk   = yf.Ticker(ticker)
        hist = tk.history(period="10y")
        if not hist.empty:
            hist.index = hist.index.tz_localize(None)
            pb, ps = {}, {}
            for year in set(equity.index).union(set(revenue.index)):
                yr_data = hist[hist.index.year == year]
                if yr_data.empty:
                    continue
                price = float(yr_data["Close"].iloc[-1])

                if year in equity.index and year in shares.index and shares[year] > 0:
                    bvps = equity[year] / shares[year]
                    if bvps > 0:
                        pb[year] = round(price / bvps, 2)

                if year in revenue.index and year in shares.index and shares[year] > 0:
                    sps = revenue[year] / shares[year]
                    if sps > 0:
                        ps[year] = round(price / sps, 2)

            pb_series = pd.Series(pb).sort_index()
            ps_series = pd.Series(ps).sort_index()
    except Exception:
        pass

    val_ratios = {
        "P/E":  pe_series,
        "P/B":  pb_series,
        "P/S":  ps_series,
    }

    # ── Build Plotly figures ──────────────────────────────────────────────────
    out: dict = {"ticker": ticker, "data_source": "SEC EDGAR"}

    out["profitability_fig"]   = _line_figure(prof_ratios,  y_fmt=".1f", height=320)
    out["liquidity_fig"]       = _line_figure(liq_ratios,   y_fmt=".2f", height=280)
    out["debt_fig"]            = _line_figure(debt_ratios,  y_fmt=".2f", height=280)
    out["efficiency_fig"]      = _line_figure(eff_ratios,   y_fmt=".2f", height=280)
    out["valuation_fig"]       = _line_figure(val_ratios,   y_fmt=".1f", height=280)

    out["profitability_table"] = _ratio_table(prof_ratios)
    out["liquidity_table"]     = _ratio_table(liq_ratios)
    out["debt_table"]          = _ratio_table(debt_ratios)
    out["efficiency_table"]    = _ratio_table(eff_ratios)
    out["valuation_table"]     = _ratio_table(val_ratios)

    all_years = [s.index.max() for s in [revenue, equity, op_cf] if not s.empty]
    out["max_year"] = int(max(all_years)) if all_years else "N/A"

    return out
