[← Methodology](methodology.md)

# Technical analysis methodology

Technical analysis studies price and volume history to describe trend, momentum and volatility. It says nothing about what a company is worth. Stock Elf computes standard indicators from two years of daily prices and turns seven of them into a simple scorecard.

**On this page**

1. [Data](#1-data)
2. [Trend: moving averages](#2-trend-moving-averages)
3. [Momentum: RSI](#3-momentum-rsi-14)
4. [Momentum: MACD](#4-momentum-macd-12-26-9)
5. [Volatility: Bollinger Bands and ATR](#5-volatility-bollinger-bands-and-atr)
6. [Volume: ratio and OBV](#6-volume-ratio-and-obv)
7. [Levels: support, resistance, Fibonacci](#7-levels-support-resistance-fibonacci)
8. [The scorecard and overall rating](#8-the-scorecard-and-overall-rating)
9. [Limitations](#9-limitations)

## 1. Data

Two years of daily open, high, low, close and volume from Yahoo Finance, adjusted for splits and dividends. Charts show the last 252 trading days (about one year). All indicators use the standard parameters below, computed with the `ta` Python library.

## 2. Trend: moving averages

```text
SMA(n) = average of the last n closes
EMA(n) = α × close + (1 − α) × EMA_prev,   α = 2 / (n + 1)
```

The app plots SMA 50, 100 and 200 and EMA 20. An EMA reacts faster than an SMA because it weights recent prices more.

| Trend label | Rule |
| --- | --- |
| Daily | Uptrend if price > SMA 50, else Downtrend |
| Weekly | Price versus the average of the last 5 closes |
| Monthly | Price versus the average of the last 21 closes |

**Golden cross / death cross.** When SMA 50 is above SMA 200 the app calls it a golden cross (a long-term uptrend); below, a death cross.

> **Example**
>
> Price $105, SMA 50 = $100, SMA 200 = $98. Price is above both averages, and SMA 50 is above SMA 200, so all three moving-average signals are **bullish**. If price fell to $97, the "Price vs SMA 50" and "Price vs SMA 200" signals would both turn bearish while the golden cross would still hold.

## 3. Momentum: RSI (14)

The relative strength index measures the balance of recent gains and losses on a 0–100 scale. It uses Wilder's smoothing over 14 days.

```text
RS  = average gain / average loss   (14-day, Wilder smoothing)
RSI = 100 − 100 / (1 + RS)
```

| RSI | Reading | Signal in the scorecard |
| --- | --- | --- |
| below 30 | Oversold | Bullish (a bounce is more likely) |
| 30 to 70 | Normal | Neutral |
| above 70 | Overbought | Bearish (a pullback is more likely) |

> **Example**
>
> Average daily gain 1.2, average daily loss 0.8. RS = 1.2 / 0.8 = 1.5. RSI = 100 − 100 / 2.5 = **60**: neutral. If the average loss were 0.3 instead, RS = 4 and RSI = 80: overbought, so bearish.

## 4. Momentum: MACD (12, 26, 9)

```text
MACD line   = EMA(12) − EMA(26)
Signal line = EMA(9) of the MACD line
Histogram   = MACD line − Signal line
```

When the MACD line is above its signal line, short-term momentum is stronger than the recent average: **bullish**. Below it: **bearish**. The histogram shows the gap.

> **Example**
>
> EMA(12) = 52.0 and EMA(26) = 50.5 give a MACD of 1.5. If the signal line is 1.1, the histogram is +0.4 and the MACD signal is bullish.

## 5. Volatility: Bollinger Bands and ATR

```text
Middle band = SMA(20)
Upper band  = SMA(20) + 2 × standard deviation of the last 20 closes
Lower band  = SMA(20) − 2 × standard deviation of the last 20 closes

True range = max(high − low, |high − prev close|, |low − prev close|)
ATR(14)    = 14-day average of the true range
```

**Bollinger signal:** price below the lower band is bullish (stretched down), above the upper band is bearish (stretched up), otherwise neutral.

**ATR stop distance:** the app shows long and short stop levels at 2 × ATR from the current price, as a volatility-based reference.

> **Example**
>
> SMA(20) = 100 and standard deviation = 5, so the bands are 90 and 110. A price of 112 is above the upper band: bearish. With ATR = 3 and price 100, a long stop sits at 100 − 2 × 3 = **94**.

## 6. Volume: ratio and OBV

```text
Volume ratio = today's volume / 20-day average volume
OBV = running total: add volume on up days, subtract it on down days
```

**Volume signal:** bullish if the ratio is above 1.2 (activity well above normal), otherwise neutral. OBV is displayed with a rising/falling label (today versus five days ago) but does not enter the score.

## 7. Levels: support, resistance, Fibonacci

**Support and resistance.** Over the last year the app finds local pivots: a day whose high is the highest of a centred 15-day window is a pivot high; a day whose low is the lowest of the window is a pivot low. Pivot highs above the current price are resistance and pivot lows below it are support. The five nearest levels of each are shown.

**Fibonacci retracements.** Over the last 90 trading days, take the swing high and low.

```text
level(x) = swing high − x × (swing high − swing low),   x = 0, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%
```

> **Example**
>
> Swing high $120 and swing low $100, a range of $20. The 61.8% level is 120 − 0.618 × 20 = **$107.64**, a place where a pullback is often watched for support.

## 8. The scorecard and overall rating

Seven signals are scored. Each is bullish, bearish or neutral.

| # | Signal | Bullish when | Bearish when |
| --- | --- | --- | --- |
| 1 | Price vs SMA 50 | price > SMA 50 | otherwise |
| 2 | Price vs SMA 200 | price > SMA 200 | otherwise |
| 3 | SMA 50 vs SMA 200 | SMA 50 > SMA 200 | otherwise |
| 4 | RSI | RSI < 30 | RSI > 70 |
| 5 | MACD | MACD > signal | MACD < signal |
| 6 | Bollinger Bands | price < lower band | price > upper band |
| 7 | Volume | ratio > 1.2 | never (neutral otherwise) |

```text
score = bullish signals / total signals

score ≥ 0.70  Strong Buy
score ≥ 0.55  Buy
score ≥ 0.45  Neutral
score ≥ 0.30  Sell
below 0.30  Strong Sell
```

> **Example**
>
> Price is above SMA 50 and SMA 200, and SMA 50 is above SMA 200 (3 bullish). RSI is 60 (neutral). MACD is above its signal (bullish). Price is inside the bands (neutral). Volume ratio is 0.9 (neutral). That is 4 bullish out of 7, a score of 0.57: **Buy**.

> Note how the scorecard works: neutral signals count in the total, and RSI and Bollinger Bands treat oversold as bullish (contrarian), while the moving averages follow the trend. A strong uptrend therefore tends to land at Buy, not Strong Buy, unless volume and momentum also line up.

## 9. Limitations

- The rating is a mechanical tally of seven rules, equally weighted. It is a summary of what the chart looks like, not a forecast.
- Moving averages lag; RSI can stay overbought for months in a strong trend; MACD gives false signals in sideways markets.
- Parameters (14, 20, 50, 200, 12/26/9) are conventions, not optimised values.
- Support, resistance and Fibonacci levels are approximate zones, and their usefulness is debated.
- Daily data on thinly traded stocks can be noisy or have gaps.

Reference: John Murphy, *Technical Analysis of the Financial Markets*; J. Welles Wilder, *New Concepts in Technical Trading Systems* (RSI, ATR).
