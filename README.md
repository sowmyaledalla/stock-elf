# Stock Elf

*A self-service stock researcher.*

Stock Elf is a small web app that helps you research a US stock on your own. Type a ticker and get a company snapshot, a free-cash-flow valuation you can adjust, and a technical-analysis read of the chart. It runs locally and uses only public data: no accounts, API keys or brokerage logins.

![Stock Elf](static/img/hero-banner.jpg)

## Features

| Page | What it does |
|---|---|
| **Evaluate** `/evaluate?ticker=MSFT` | Company profile, key metrics, TradingView chart, Finviz fundamentals, quick links, and a copy-to-clipboard "Company Narrative" prompt for any LLM. |
| **DCF** `/dcf2?ticker=MSFT` | Textbook FCFF discounted cash flow built from SEC filings, with editable ten-year driver curves, life-cycle presets, Bear/Base/Bull scenarios, a sensitivity grid and a reverse DCF. A compact version lives at `/dcf`. |
| **Technicals** `/technicals?ticker=MSFT` | Moving averages, RSI, MACD, Bollinger Bands, ATR, volume, support/resistance and Fibonacci levels, plus a transparent seven-signal scorecard. |
| **How to use** `/how-to-use` | A walkthrough of every page and the Company Narrative workflow. |
| **Methodology** `/methodology` | The formulas, defaults, worked examples and limits behind the DCF and the technical indicators. |

## Quick start

Requires Python 3.10 or newer.

```bash
git clone https://github.com/sowmyaledalla/stock-elf.git
cd stock-elf
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:8000 and enter a ticker. Use `PORT=8080 python app.py` to change the port.

The SEC asks API clients to identify themselves. Set your own contact before heavy use:

```bash
export SEC_USER_AGENT="StockElf you@example.com"
```

## How the DCF works, in brief

Free cash flow to the firm is `EBIT x (1 - tax) + D&A - CapEx - change in NWC`, forecast for ten years from six editable drivers (revenue growth, operating margin, tax, D&A, CapEx, working capital). It is discounted at a CAPM-based WACC and a Gordon-growth terminal value is added. Defaults are derived from SEC XBRL filings. See the in-app [methodology page](http://127.0.0.1:8000/methodology/dcf) or [`templates/docs/methodology_dcf.html`](templates/docs/methodology_dcf.html) for the formulas and a worked example.

## Company Narrative workflow

Good valuation inputs need judgment. Stock Elf has no built-in LLM; instead, click **Company narrative prompt** on the DCF page, paste it into any assistant with web access, then paste the JSON it returns into **Paste inputs...** to load researched assumptions. Details are on the How to use page.

## Data sources

| Source | Used for |
|---|---|
| [SEC EDGAR](https://www.sec.gov/edgar) (XBRL company facts) | Financial statement history for the DCF |
| [yfinance](https://github.com/ranaroussi/yfinance) | Prices, beta, Treasury yield, split history |
| [Finviz](https://finviz.com) | Evaluate-page metrics and company description |
| [TradingView](https://www.tradingview.com) widget | Interactive chart on the Evaluate page |

Fetched data is cached under `data/cache/` (git-ignored). Delete the folder to force a refresh.

## Project layout

```
app.py                Flask routes
functions/            Technicals, Finviz and EDGAR helpers, prompt builder
valuation/            DCF engine (fcff.py), EDGAR table, WACC, importer
templates/            Pages; templates/docs/ holds How to use and Methodology
static/               Styles, scripts, logo and images
prompts/              Company Narrative prompt
tests/                Unit and smoke tests
```

## Tests

```bash
pip install pytest
pytest
```

## Limitations

Defaults extrapolate the recent past and are a starting point, not a forecast. The DCF does not suit banks and insurers. Free data sources can be delayed, revised or briefly unavailable. Technical signals describe past price behavior only.

## Disclaimer

Stock Elf is an educational research tool and is not investment advice. Do your own research before making any investment decision.

## License

[MIT](LICENSE) &copy; 2026 Sowmya Ledalla
