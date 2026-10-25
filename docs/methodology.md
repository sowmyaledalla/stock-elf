# Methodology

What each page calculates, the formulas behind it, and where its data comes from.

- [**DCF valuation**](methodology-dcf.md): FCFF model, WACC, terminal value, scenarios, sensitivity and the reverse DCF, with a worked example.
- [**Technical analysis**](methodology-technicals.md): every indicator, its parameters, the signal rule and how the overall rating is scored, with worked examples.

## Data sources

| Source | Used for | Notes |
| --- | --- | --- |
| SEC EDGAR (XBRL company facts) | Annual and quarterly revenue, operating income, tax, D&A, CapEx, working capital, debt, cash, share count | Primary source for the DCF history. Free; requires a contact in the request header. |
| yfinance (Yahoo Finance) | Prices and price history, beta, 10-year Treasury yield, split history | Unofficial; can be delayed or occasionally unavailable. |
| Finviz | Evaluate page metrics, company description, fallback fundamentals | Scraped from the public quote page. |
| TradingView widget | Interactive chart on the Evaluate page | Embedded from TradingView's servers in your browser. |

## Limits that apply everywhere

- Models are only as good as their inputs. Defaults are mechanical extrapolations of the past, not forecasts.
- Financial companies (banks, insurers) and companies with no meaningful operating history do not fit the cash-flow model well.
- Technical signals describe past price behavior; they carry no guarantee about the future.
- Data providers restate and revise. Verify anything important against the original filing.

Further reading: Aswath Damodaran, *The Little Book of Valuation*, and his free course materials at [pages.stern.nyu.edu/~adamodar](https://pages.stern.nyu.edu/~adamodar/).
