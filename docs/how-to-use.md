# How to use Stock Elf

Type a ticker, pick a view, and work from the big picture (Evaluate) to a value estimate (DCF) to timing context (Technicals).

**On this page**

1. [Getting started](#1-getting-started)
2. [The Evaluate page](#2-the-evaluate-page)
3. [The DCF page](#3-the-dcf-page)
4. [The Company Narrative workflow](#4-the-company-narrative-workflow)
5. [The Technicals page](#5-the-technicals-page)
6. [Troubleshooting and FAQ](#6-troubleshooting-and-faq)

## 1. Getting started

1. Open the home page (`/`) and type a US ticker, for example `MSFT`.
2. Click **Evaluate**, **DCF** or **Technicals**. The bar at the top of every page switches between the three and keeps your ticker.
3. The first load of a ticker can take a few seconds because data is fetched live from public sources. Results are cached on disk afterwards.

Tickers use Yahoo-style symbols, so share classes look like `BRK-B`. Only US-listed companies with SEC filings work in the DCF.

## 2. The Evaluate page

A one-screen snapshot of the company, meant for a first look.

- **Company Profile:** business description, sector and industry.
- **Key Metrics:** price, EPS, P/E, forward P/E, target price, 52-week range, market cap, beta and ROE from Finviz.
- **Quick Links:** jump to the same ticker on Yahoo Finance, Finviz, Morningstar, GuruFocus, FinPrep and Seeking Alpha for a second opinion.
- **Price Chart:** an interactive TradingView chart with MACD and a moving average.
- **Finviz Financials:** price, fundamentals, momentum and analyst-target fields grouped by category.
- **Skill prompts:** click a chip to copy a ready-made research prompt for any LLM (see the narrative workflow below).

## 3. The DCF page

Estimates what the business is worth from the cash it can produce. The method is explained on the [DCF methodology page](methodology-dcf.md); this section is just how to drive the page.

1. **Read the source table first.** The top of the page shows ten years of reported figures from SEC filings plus a trailing-twelve-month (TTM) column. Every default assumption is derived from these numbers.
2. **Check the assumptions.** Revenue growth, operating margin, tax, D&A, CapEx and working capital are shown as ten-year curves. The defaults are mechanical, so they are a starting point, not a view.
3. **Pick a life-cycle preset.** The page suggests a stage (young, growth, mature, declining) from the company's history. Applying a preset reshapes all the curves at once; you can then edit single years.
4. **Edit what you disagree with.** Changed values are highlighted in blue; clearing a box returns it to the default.
5. **Read the output.** Compare the value per share with the market price, then look at the Bear/Base/Bull scenarios and the WACC-versus-terminal-growth sensitivity grid. Note the share of value that comes from the terminal value; a high share means the answer rests on the far future.
6. **Use the reverse DCF.** It takes today's price as given and solves for what growth, margin, terminal growth or discount rate the market is assuming. This is often more useful than the point estimate.

The Quick DCF link (`/dcf`) on the step-by-step page opens a compact single-screen version of the same engine.

## 4. The Company Narrative workflow

Good DCF inputs need judgment about the business, which a formula cannot supply. Stock Elf has no built-in LLM; instead it gives you a prompt to use with any assistant that can browse the web.

1. On the DCF page, click **Company narrative prompt**. It copies a prompt for your ticker to the clipboard.
2. Paste it into an LLM with web access. It researches the company and returns a short narrative plus one JSON block of DCF inputs.
3. Back on the DCF page, click **Paste inputs…** and paste the whole reply. The page loads the numbers and shows warnings for anything it had to clip or ignore.
4. Use **Research notes** to re-read the assumptions behind each number. Edit any value and click **Apply & recalculate** to update the valuation.

> Treat LLM output as a draft. Check key facts against the company's filings before trusting a valuation built on them.

## 5. The Technicals page

Shows what the price chart is doing, not what the company is worth. See the [Technicals methodology page](methodology-technicals.md) for every rule.

- **Header:** price, an overall rating (Strong Sell to Strong Buy) and a count of bullish and bearish signals.
- **Trend direction:** daily, weekly and monthly trend, price against the 50-, 100- and 200-day averages, and golden/death cross status.
- **Charts:** one year of candles with moving averages and Bollinger Bands, plus RSI, MACD and volume panels.
- **Levels:** nearby support and resistance, Fibonacci retracements and an ATR-based stop-loss distance.

The rating is a simple tally of mechanical rules. Use it to see whether trend, momentum and volume agree, not as a trade signal.

## 6. Troubleshooting and FAQ

**"No data" or an error for a ticker.** Check the symbol. Foreign listings, recent IPOs and funds often lack SEC filings, so the DCF cannot run for them.

**Numbers differ from another site.** Sources define metrics differently (TTM versus fiscal year, GAAP versus adjusted) and update at different times. The DCF page labels where each figure comes from.

**The DCF value looks absurd.** The default curves are mechanical. Check growth and margin first, then the WACC and terminal growth; WACC must exceed terminal growth. Banks and insurers do not fit a free-cash-flow model.

**Pages are slow the first time.** Data is fetched live. Fetched data is cached under `data/cache/`; delete that folder to force a refresh.

**SEC rate limits.** The SEC asks clients to identify themselves. Set the `SEC_USER_AGENT` environment variable to your own contact, as described in the README.
