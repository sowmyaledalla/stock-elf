[← Methodology](methodology.md)

# DCF methodology

A discounted cash flow (DCF) values a business as the present value of the free cash flow it can pay out to all of its capital providers. Stock Elf uses the textbook free-cash-flow-to-firm (FCFF) form, with ten explicit forecast years and a terminal value.

**On this page**

1. [The idea](#1-the-idea)
2. [Free cash flow to the firm](#2-free-cash-flow-to-the-firm)
3. [The six drivers and their defaults](#3-the-six-drivers-and-their-defaults)
4. [Growth, reinvestment and return on capital](#4-growth-reinvestment-and-return-on-capital)
5. [Discount rate (WACC)](#5-discount-rate-wacc)
6. [Terminal value](#6-terminal-value)
7. [From enterprise value to value per share](#7-from-enterprise-value-to-value-per-share)
8. [Worked example](#8-worked-example)
9. [Scenarios and sensitivity](#9-scenarios-and-sensitivity)
10. [Reverse DCF](#10-reverse-dcf)
11. [Life-cycle stages](#11-life-cycle-stages)
12. [Limitations](#12-limitations)

## 1. The idea

A dollar received in the future is worth less than a dollar today, so each forecast cash flow is divided by (1 + r) raised to the number of years. Add up the discounted cash flows for the forecast years and for all the years after (the terminal value), and you have the value of the operating business. Adjust for cash and debt to get the value belonging to shareholders.

```text
Enterprise value = Σ FCFF_t / (1 + WACC)^t  (t = 1..10)  +  TV / (1 + WACC)^10
```

Valuation is a systematic process rooted in fundamentals, not a black box. Whatever the company or its stage, intrinsic value rests on three pillars:

1. **Cash flows** from assets already in place and from future growth investments.
2. **Growth** in those cash flows, which depends on how much is reinvested and how well (the return earned on it).
3. **Risk**, which enters through the discount rate and through the probability that the company fails or becomes distressed.

There are two equivalent routes, depending on how debt is treated. **Enterprise valuation (FCFF)** discounts pre-debt operating cash flows at the cost of capital, then adds cash and subtracts debt to reach equity value. **Equity valuation (FCFE)** discounts post-debt cash flows to shareholders at the cost of equity. Stock Elf uses the FCFF route, because it keeps the operating forecast separate from financing choices.

## 2. Free cash flow to the firm

FCFF is the cash left from operations after taxes and after the investment needed to sustain growth, before paying any lenders or shareholders.

```text
FCFF = EBIT × (1 − tax rate) + D&A − CapEx − ΔNWC

EBIT   = revenue × operating margin
D&A    = revenue × D&A %
CapEx  = revenue × CapEx %
ΔNWC  = NWC % × (revenue_t − revenue_t-1)
```

Equivalently, FCFF is after-tax operating income minus reinvestment:

```text
FCFF = EBIT × (1 − tax rate) − Reinvestment
Reinvestment = Net CapEx + ΔNWC,   Net CapEx = CapEx − D&A
```

The first term, EBIT × (1 − tax), is after-tax operating profit (NOPAT). D&A is added back because it is a non-cash charge. CapEx and the change in net working capital (NWC) are the cash the business must reinvest.

## 3. The six drivers and their defaults

Each driver is a list of ten yearly values, so you can shape every year. Defaults come from the company's SEC filings (trailing twelve months, TTM) and are deliberately simple.

| Driver | Default curve |
| --- | --- |
| Revenue growth | Year-1 growth `g1` held for years 1–5 (last reported annual growth, limited to 2%–20%), then a straight line down to terminal growth in year 10. |
| Operating margin | TTM operating margin, ramping toward a target margin over `margin_years` (default: target equals today, so flat). |
| Tax rate on EBIT | TTM effective tax rate (limited to 10%–28%), moving in a straight line to 25% by year 10. |
| D&A % of revenue | TTM level, held flat. |
| CapEx % of revenue | D&A % plus TTM net CapEx (CapEx − D&A) scaled by growth ÷ g1, so net investment shrinks as growth fades and the terminal year stays consistent. |
| ΔNWC % of revenue change | Historical average, limited to ±30%, held flat. |

Other defaults: terminal growth 2.5%; equity risk premium 4.23% (Damodaran's published figure; edit it); risk-free rate from the 10-year Treasury yield; beta from Yahoo Finance; cost of debt = risk-free rate + 1%.

## 4. Growth, reinvestment and return on capital

Growth is not free. Operating income can only grow if the company reinvests, and how fast it grows depends on how much it reinvests and on the return that investment earns. This is the fundamental growth equation:

```text
Expected growth in operating income = Reinvestment rate × Return on capital (ROC)

Reinvestment rate = (Net CapEx + ΔNWC) / after-tax operating income
After-tax ROC     = EBIT × (1 − tax) / (book debt + book equity − cash)
```

It works as a consistency check on any set of curves. If you forecast fast growth while the drivers show very little reinvestment, the forecast implicitly assumes an unrealistically high return on capital. The page reports the implied terminal reinvestment rate and return on capital for this reason.

> **Example**
>
> A company reinvests 40% of its after-tax operating income and earns 15% on new capital. Its operating income can grow 0.40 × 15% = **6%** a year. To grow at 10% with the same 15% return, it would have to reinvest 67%.

The same logic fixes the terminal year. In a going-concern perpetuity the stable reinvestment rate must be:

```text
Stable reinvestment rate = g_stable / stable ROC
TV = NOPAT_n+1 × (1 − stable reinvestment rate) / (cost of capital_stable − g_stable)
```

> **Why this matters: a check on the worked example below**
>
> In the made-up company of section 8, the default curves leave a terminal reinvestment rate of only **3.1%** of NOPAT, which implies a return of about **80%** on new capital. That is generous. If instead we assume the company earns a stable ROC of 10%, then reinvestment must be 2.5% / 10% = 25% of NOPAT. FCFF<sub>11</sub> falls from 329.9 to 340.5 × 0.75 = 255.4, the terminal value from 5,075 to 3,929, and the value from $36.77 to about **$31.93** per share. Always read the implied terminal ROC next to the value.

For young companies, reinvestment is usually modelled through a **sales-to-capital ratio**: each dollar of invested capital supports some dollars of revenue, so reinvestment = Δrevenue / (sales-to-capital). Stock Elf takes CapEx and ΔNWC as percentages of revenue instead; to use a sales-to-capital view, convert it to those percentages when you edit the curves.

## 5. Discount rate (WACC)

The weighted average cost of capital blends what equity holders and lenders each require, using market-value weights.

```text
Cost of equity (CAPM):  k_e = r_f + β × ERP
After-tax cost of debt: k_d × (1 − tax)
Weights:                E = price × shares,   D = debt,   w_d = D / (D + E)

WACC = (1 − w_d) × k_e + w_d × k_d × (1 − tax)
```

One constant WACC discounts all ten years and the terminal value. The general framework lets the discount rate change over time, for example stepping beta and WACC down toward a mature-company level as a growth company's risk normalises; Stock Elf keeps one rate for simplicity, so use the WACC override (and the sensitivity grid) to explore that effect. You can override it on the page. WACC must exceed terminal growth, otherwise the terminal value is undefined and the page shows an error.

## 6. Terminal value

After year 10 the model assumes the company grows forever at a stable rate g (default 2.5%, below the economy's long-run growth). The year-11 cash flow is built from the same drivers as year 10, with revenue growing at g, and capitalised with the Gordon growth formula.

```text
TV = FCFF_11 / (WACC − g)
PV of TV = TV / (1 + WACC)^10
```

The page reports the terminal value's share of enterprise value and the implied terminal reinvestment rate and return on invested capital, as consistency checks. Stable growth needs reinvestment: a firm cannot grow at g while reinvesting nothing, because g = reinvestment rate × return on capital.

## 7. From enterprise value to value per share

```text
Equity value = Enterprise value + cash − debt
Value per share = Equity value / diluted shares

If you set a probability of failure p and a liquidation value L per share:
Value per share = DCF value × (1 − p) + L × p
```

The gap shown on the page compares this value with the market price.

**Distress.** For declining or highly levered firms a conventional DCF overstates value, because it assumes the business survives. Weight a going-concern scenario against a liquidation scenario:

```text
Firm value = Going-concern DCF × (1 − P_distress) + Liquidation value × P_distress
```

P<sub>distress</sub> can be taken from cumulative default-probability tables by bond rating. Use the page's probability-of-failure and liquidation-value inputs for this.

## 8. Worked example

A made-up company, so the arithmetic is easy to follow. It has revenue of $1,000M, a 20% operating margin, 21% tax, D&A of 4% and CapEx of 5% of revenue, and working capital of 10% of any revenue increase. It has no debt, $100M of cash and 100M shares. Growth is 10% for years 1–5, fading to 2.5% by year 10.

> **Step 1: WACC**
>
> r<sub>f</sub> = 4%, β = 1.0, ERP = 5%. So k<sub>e</sub> = 4% + 1.0 × 5% = 9%. With no debt, **WACC = 9%**.
>
> **Step 2: Year 1 cash flow**
>
> Revenue = 1,000 × 1.10 = 1,100. EBIT = 1,100 × 20% = 220. Tax = 220 × 21% = 46.2, so NOPAT = 173.8.
> D&A = 44.0, CapEx = 55.0, ΔNWC = 10% × (1,100 − 1,000) = 10.0.
> FCFF = 173.8 + 44.0 − 55.0 − 10.0 = **152.8**. Discounted one year: 152.8 / 1.09 = 140.2.
>
> **Step 3: The ten-year table ($M)**
>
> | Year | Growth | Revenue | NOPAT | D&A | CapEx | ΔNWC | FCFF | PV |
> | --- | --- | --- | --- | --- | --- | --- | --- | --- |
> | 1 | 10.0% | 1,100.0 | 173.8 | 44.0 | 55.0 | 10.0 | 152.8 | 140.2 |
> | 2 | 10.0% | 1,210.0 | 191.2 | 48.4 | 60.5 | 11.0 | 168.1 | 141.5 |
> | 3 | 10.0% | 1,331.0 | 210.3 | 53.2 | 66.6 | 12.1 | 184.9 | 142.8 |
> | … | … | … | … | … | … | … | … | … |
> | 10 | 2.5% | 2,102.7 | 332.2 | 84.1 | 89.4 | 5.1 | 321.8 | 136.0 |
>
> Years 4–9 (omitted) follow the same pattern as growth fades. The sum of all ten present values is **1,432.8**.
>
> **Step 4: Terminal value**
>
> FCFF<sub>11</sub> = 329.9 (year-10 drivers, revenue growing 2.5%). TV = 329.9 / (9% − 2.5%) = **5,075.3**. Discounted ten years: 5,075.3 / 1.09<sup>10</sup> = **2,143.9**.
>
> **Step 5: Value**
>
> Enterprise value = 1,432.8 + 2,143.9 = **3,576.7**. Add cash of 100, subtract debt of 0: equity value = 3,676.7. Divide by 100M shares: **$36.77 per share**.
>
> The terminal value is 60% of the total, which is typical. If the stock traded at $20, the model would say it is priced well below this set of assumptions; the next sections explain how to test whether the assumptions deserve that confidence.

You can reproduce this example in code: it is the output of `valuation.fcff.run` with the inputs above.

## 9. Scenarios and sensitivity

**Scenarios.** Bear, Base and Bull re-run the model with shifted assumptions.

|  | Growth (years 1–5, tapering to year 10) | Operating margin (every year) | WACC |
| --- | --- | --- | --- |
| Bear | −3 pts | −2 pts | +1 pt |
| Base | as set | as set | as set |
| Bull | +3 pts | +3 pts | −1 pt |

**Sensitivity grid.** Value per share across WACC (±2 pts in 1-pt steps) and terminal growth (±1 pt in 0.5-pt steps). Cells where WACC does not exceed terminal growth are left blank. The spread of the grid is a quick measure of how fragile the valuation is.

## 10. Reverse DCF

Instead of asking "what is it worth?", ask "what does the price assume?". The reverse DCF takes the market price as fixed and solves, one lever at a time with everything else unchanged, for the value that makes the model equal to the price:

- **Revenue growth:** the year 1–5 growth rate (the path shifts, tapering to terminal growth).
- **Operating margin:** the margin level, applied to every year.
- **Terminal growth:** the perpetual growth rate.
- **Discount rate:** the return an investor earns by buying at today's price if the cash flows come true.

It also shows a growth-versus-margin trade-off table and compares the market's enterprise value (market cap + debt − cash) with the model's. If the price implies growth far above anything in the company's history, the market is optimistic; if it implies a margin below current levels, the market is pessimistic.

> **Example**
>
> The made-up company above is worth $36.77 per share in the model. Suppose it trades at $60. Solving one lever at a time, the price implies: year 1–5 growth of **19.3%** instead of 10%; or an operating margin of **32.2%** instead of 20%; or terminal growth of **5.8%** instead of 2.5%; or a discount rate of **6.6%** instead of 9%. Each is a way of asking the same question: is that believable for this business?

## 11. Life-cycle stages

The mathematics of the model is the same for every company; what changes with the life-cycle stage are the assumptions, the projection variables and the risk adjustments. The page suggests a stage from simple rules on the SEC history (margin sign and trend, 3-year revenue growth, years of history, interest cover) and offers a preset curve set for each. The detector is a hint, not a verdict: override it when you know the business better.

| Life-cycle stage | 1. Common attributes for the group | 2. Valuation issues | 3. Valuation solutions (variables and formulas) | 4. Relative valuation (multiples and formulas) |
| --- | --- | --- | --- | --- |
| **Young growth**<br>(e.g., Evergreen Solar) | • No historical performance data.<br>• Small or zero revenues with operating losses.<br>• High probability of failure.<br>• Illiquid / low float.<br>• Multiple claims on equity. | • *Intrinsic:* Negative cash flows; estimating future revenues, target margins and survival time is extremely difficult.<br>• *Relative:* Current scaling variables are tiny or negative; book values are meaningless. | • **Revenue growth** (g<sub>rev</sub>): forecast via total market size and market share captured.<br>• **Target margins** (EBIT / Sales): evolve over the forecast period (t = 1…n) to mature peer levels.<br>• **Survival adjustment:**<br>`Value = DCF value × (1 − probability of failure)` | • Use forward revenues or earnings projected further down the life cycle (t = 5).<br>• Adjust the forward multiple to reflect lower terminal growth.<br>• Discount the forward value back for the time value of money and survival risk. |
| **Growth**<br>(e.g., Under Armour) | • Dynamic, fast-changing financials.<br>• Size disconnect: market values vastly exceed book values.<br>• Low debt relative to value.<br>• Short, unstable market history. | • *Intrinsic:* Rapidly changing scale means past growth cannot continue; predicting how fast growth fades is hard.<br>• *Relative:* High growth and risk make matching comparables complex. | • **Fundamental growth:**<br>`g = Reinvestment rate × ROC`<br>where `Reinvestment rate = (Net CapEx + ΔWC) / After-tax EBIT`<br>• **FCFF projection:**<br>`FCFF_t = EBIT_t × (1 − t) − Reinvestment_t`<br>• **Terminal value:**<br>`TV_n = FCFF_n+1 / (Cost of capital − g_stable)` | • Use the **PEG ratio** (PE ÷ expected growth) to screen for relative value.<br>• Run multiple regressions of multiples against growth, risk and payout to control for peer differences. |
| **Mature**<br>(e.g., Coca-Cola, Hormel Foods) | • Revenue growth converges with macro growth (2%–3%).<br>• Established, stable margins.<br>• High excess returns.<br>• High debt capacity and cash build-up. | • *Intrinsic:* Complacency: relying on past operating data can undervalue firms with operating slack.<br>• *Relative:* Too many choices of multiples; leverage changes skew equity multiples. | • **Operating restructuring:** optimise existing assets to improve EBIT and ROC.<br>• **Financial restructuring:** raise the debt ratio to optimal industry levels to lower the cost of capital (WACC).<br>• **Terminal reinvestment:**<br>`Reinvestment rate = g_stable / ROC` | • Rich availability of multiples (PE, P/BV, EV/EBITDA, EV/Sales).<br>• Enterprise multiples (EV/EBITDA) are preferred over equity multiples when capital structures and debt ratios fluctuate. |
| **Declining**<br>(e.g., General Motors, Sears) | • Stagnant or declining revenues.<br>• Shrinking or negative margins and loss of pricing power.<br>• Frequent asset divestitures.<br>• High default risk and leverage. | • *Intrinsic:* Depressed historical data, negative returns and a high probability of default.<br>• *Relative:* Earnings and book values break down; distressed firms trade at low multiples because of high bankruptcy risk. | • **Going concern vs. liquidation:**<br>`Firm value = Going-concern value × (1 − P_distress) + Liquidation value × P_distress`<br>where P<sub>distress</sub> comes from cumulative bond-rating default tables.<br>• **Liquidation value:** estimated from an asset breakup or book-value recovery rates. | • Exercise extreme caution with equity multiples (PE and P/BV) because of negative earnings and book values.<br>• Adjust enterprise multiples for distress probabilities to avoid value traps. |

### How each driver typically behaves by stage

| Driver | Young growth | Growth | Mature | Declining |
| --- | --- | --- | --- | --- |
| EBIT (revenue × margin) | Starts deeply negative and converges upward to mature peer margins over `margin_years`. | Positive and expanding; plateaus as competition and scale limits arrive. | Steady; check for slack where cost cuts would raise EBIT. | Depressed or contracting as pricing power fades; may recover if a turnaround works. |
| Tax rate | 0% at first because accumulated losses (NOLs) shield income. | Moves to statutory rates as income becomes consistent. | Stable statutory rate throughout. | Erratic or 0% while losing money; normalises if the company recovers. |
| D&A (% of revenue) | Starts low and rises as the asset base is built. | Tracks revenue growth as capacity expands. | Constant; roughly equal to CapEx in steady state. | High relative to shrinking revenue, or falls if assets are sold. |
| CapEx (% of revenue) | Heavy; best linked to revenue growth through a sales-to-capital ratio. | High to fund expansion, tapering toward maintenance. | Predictable maintenance level, constant. | Cut sharply; capacity investment stops and assets are divested. |
| ΔNWC (% of revenue change) | Tied to rapid growth; inventory and receivables absorb cash. | Scales with growth; stabilises as the cycle becomes efficient. | Constant, following the historical operating cycle. | Often negative: shrinking revenue releases working capital as cash. |

### DCF components by life-cycle stage

The same five building blocks of a DCF look different at each stage: the cash flows from existing assets, the expected growth, how long the growth lasts, the risk, and the terminal value.

| DCF component | 1. Young growth<br>(e.g., Evergreen Solar) | 2. Growth<br>(e.g., Under Armour) | 3. Mature<br>(e.g., Hormel Foods, Coca-Cola) | 4. Declining<br>(e.g., Las Vegas Sands) |
| --- | --- | --- | --- | --- |
| **1. Cash flows from existing assets** | • Typically negative or close to zero.<br>• Start with operating losses and account for accumulated net operating losses (NOLs) to shelter future taxes. | • Positive, but free cash flow to the firm (FCFF) may be low or negative early on because of heavy reinvestment needs (CapEx and working capital). | • Robust, stable and positive.<br>• The vast majority of the company's value comes from these assets in place (but check for operating slack or inefficiencies). | • Depressed, shrinking or negative because of lost pricing power.<br>• Often tied to liquidating assets or selling off divisions to raise cash. |
| **2. Expected growth** | • Driven by total market size and market share captured.<br>• High initial revenue growth (e.g., 40%) that tapers over time, paired with target operating margins of mature peers. | • Rapid revenue growth that scales down systematically because of size and competition.<br>• Driven fundamentally by reinvestment rate × ROIC (ensuring ROIC exceeds the cost of capital). | • Low and stable, converging on nominal macroeconomic growth (about 2% to 3%).<br>• Driven by minor efficiency gains, pricing power or disciplined reinvestment. | • Negative or zero revenue and earnings growth as the business contracts and sheds market share. |
| **3. Time of growth (forecast period)** | • A longer runway (e.g., 10 years) to allow time to move from operating losses to stable scale. | • Typically 5 to 10 years, depending on how long the firm can sustain its competitive advantage before hitting scale limits. | • A shorter forecast period (typically 5 years), since the company is already close to steady state. | • A short period (3 to 5 years) to test for a realistic operational turnaround, or skipped entirely for liquidation. |
| **4. Risk (discount rate)** | • Exceptionally high early on (e.g., beta of 1.60), scaled down gradually toward industry norms.<br>• Crucially adjusted for survival risk through a multi-step probability of failure. | • Starts moderately high (e.g., beta of 1.30) during rapid expansion and declines gradually over the forecast period as the firm stabilises. | • Stable and close to industry averages throughout (beta near 1.0, debt ratios near optimal). | • Exceptionally high because of severe default risk and high leverage relative to shrinking operating earnings. |
| **5. Terminal value** | • Makes up 80% to over 100% of total value, since early cash flows need capital infusions.<br>• Perpetual growth at stable macroeconomic growth, a beta of 1.0 and sustainable reinvestment. | • Calculated at the end of the high-growth period using perpetual growth (2% to 3%), a beta of 1.0 and modest excess returns (ROIC above the cost of capital). | • Perpetual growth, with modest reinvestment tied directly to stable growth and return on capital. | • Replaced or adjusted by a cumulative probability of default or distress (from bond-rating tables), or replaced entirely by a liquidation value. |

> How this maps to Stock Elf: the app always uses a ten-year forecast and one constant WACC, so the stage-specific forecast lengths (3–5 years for declining or mature firms) and the beta that steps down over time are not modelled directly. To approximate them, let growth fade to the terminal rate sooner in the growth curve, use the WACC override, and use the probability-of-failure and liquidation-value inputs for young and declining companies.

### The presets in the app

| Preset | Shape of the curves |
| --- | --- |
| Flat | Everything held at TTM values; growth uses the default fade. A baseline, not a life-cycle stage. |
| Young growth | High growth that fades; margin climbs to a mature level; no tax for 4 years, then rising; heavy CapEx tapering. Pair with a probability of failure. |
| Growth | Growth held for 3 years then fading, margin widens, tax normalises, CapEx tapers so year-10 reinvestment matches g ÷ ROC. |
| Mature | Growth capped near the economy's, margins flat, reinvestment consistent with stable growth. |
| Declining | Shrinking revenue, margin erosion, cash released from working capital. Use a distress probability and liquidation value. |

The relative-valuation column is guidance for cross-checking a DCF with multiples (PEG, EV/EBITDA and so on); Stock Elf does not compute peer multiples itself, but the Evaluate page shows the company's own P/E and forward P/E for a quick comparison.

## 12. Limitations

- **Garbage in, garbage out.** The defaults extrapolate the recent past. A DCF is a way to organise a view of the business, not a source of one.
- **Terminal value dominates.** Typically 50–75% of the value comes from after year 10. Small changes in WACC or terminal growth move the result a lot (see the sensitivity grid).
- **Unusual companies.** Banks, insurers and REITs need different models. Companies with negative cash flows need explicit judgement on when and how profits arrive.
- **Constant discount rate.** One WACC is applied to every year, so risk that normalises over time is not modelled except through overrides.
- **Reinvestment consistency.** The curves are free-form, so nothing forces growth, reinvestment and return on capital to agree. Check the implied terminal ROC.
- **Stock-based compensation.** It is a real cost to shareholders. Check how it affects margin and share count before trusting an estimate.
- **Data.** SEC tags differ between companies, so some fields use fallbacks. The page lists any fallback it used.

Reference: Aswath Damodaran, *The Little Book of Valuation* (Wiley), and *Investment Valuation*.
