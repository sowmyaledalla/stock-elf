#!/usr/bin/env python3
"""
Technical analysis data builder.
Returns a dict of all computed indicators ready for the template.
"""

import numpy as np
import pandas as pd
import ta
import yfinance as yf


def _safe(val):
    """Convert numpy/nan to plain Python float or None."""
    try:
        v = float(val)
        return None if (np.isnan(v) or np.isinf(v)) else round(v, 4)
    except Exception:
        return None


def get_technicals(ticker: str) -> dict:
    ticker = ticker.upper().strip()

    # ── Fetch OHLCV ──────────────────────────────────────────────────────────
    raw = yf.download(ticker, period="2y", interval="1d", progress=False, auto_adjust=True)
    if raw.empty:
        raise ValueError(f"No data returned for {ticker}")
    raw.columns = raw.columns.get_level_values(0)
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy().dropna()

    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]
    vol   = df["Volume"]

    # ── Moving averages ───────────────────────────────────────────────────────
    df["sma50"]  = ta.trend.SMAIndicator(close, 50).sma_indicator()
    df["sma100"] = ta.trend.SMAIndicator(close, 100).sma_indicator()
    df["sma200"] = ta.trend.SMAIndicator(close, 200).sma_indicator()
    df["ema20"]  = ta.trend.EMAIndicator(close, 20).ema_indicator()

    # ── RSI ───────────────────────────────────────────────────────────────────
    df["rsi"] = ta.momentum.RSIIndicator(close, 14).rsi()

    # ── MACD ─────────────────────────────────────────────────────────────────
    macd_obj = ta.trend.MACD(close)
    df["macd"]        = macd_obj.macd()
    df["macd_signal"] = macd_obj.macd_signal()
    df["macd_hist"]   = macd_obj.macd_diff()

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    bb = ta.volatility.BollingerBands(close, 20, 2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_mid"]   = bb.bollinger_mavg()
    df["bb_lower"] = bb.bollinger_lband()

    # ── ATR ───────────────────────────────────────────────────────────────────
    df["atr"] = ta.volatility.AverageTrueRange(high, low, close, 14).average_true_range()

    # ── OBV ───────────────────────────────────────────────────────────────────
    df["obv"] = ta.volume.OnBalanceVolumeIndicator(close, vol).on_balance_volume()

    # ── Volume MA ─────────────────────────────────────────────────────────────
    df["vol_ma20"] = vol.rolling(20).mean()

    # ── Support / Resistance (local pivots, last 1 year) ─────────────────────
    window = 15
    recent_df = df.tail(252)
    local_high = recent_df["High"][
        recent_df["High"] == recent_df["High"].rolling(window, center=True).max()
    ].dropna()
    local_low = recent_df["Low"][
        recent_df["Low"] == recent_df["Low"].rolling(window, center=True).min()
    ].dropna()

    current_price = _safe(close.iloc[-1])
    resistance = sorted(
        {round(v, 2) for v in local_high.values if v > current_price},
    )[:5]
    support = sorted(
        {round(v, 2) for v in local_low.values if v < current_price},
        reverse=True
    )[:5]

    # ── Fibonacci retracements (90-day swing) ─────────────────────────────────
    swing_df   = df.tail(90)
    swing_high = swing_df["High"].max()
    swing_low  = swing_df["Low"].min()
    diff = swing_high - swing_low
    fib_levels = {
        "0.0%":   round(float(swing_high), 2),
        "23.6%":  round(float(swing_high - 0.236 * diff), 2),
        "38.2%":  round(float(swing_high - 0.382 * diff), 2),
        "50.0%":  round(float(swing_high - 0.500 * diff), 2),
        "61.8%":  round(float(swing_high - 0.618 * diff), 2),
        "78.6%":  round(float(swing_high - 0.786 * diff), 2),
        "100.0%": round(float(swing_low), 2),
    }

    # ── Trend direction ───────────────────────────────────────────────────────
    def trend_label(price, sma):
        if sma is None:
            return "N/A"
        return "Uptrend" if price > sma else "Downtrend"

    last = df.iloc[-1]
    price   = _safe(last["Close"])
    sma50   = _safe(last["sma50"])
    sma100  = _safe(last["sma100"])
    sma200  = _safe(last["sma200"])
    ema20   = _safe(last["ema20"])
    rsi     = _safe(last["rsi"])
    macd    = _safe(last["macd"])
    macd_sig= _safe(last["macd_signal"])
    macd_hist = _safe(last["macd_hist"])
    bb_upper= _safe(last["bb_upper"])
    bb_mid  = _safe(last["bb_mid"])
    bb_lower= _safe(last["bb_lower"])
    atr     = _safe(last["atr"])

    # ── Weekly / monthly trend proxy (price vs rolling MAs on daily data) ────
    weekly_trend  = trend_label(price, _safe(df["Close"].rolling(5).mean().iloc[-1]))
    monthly_trend = trend_label(price, _safe(df["Close"].rolling(21).mean().iloc[-1]))
    daily_trend   = trend_label(price, sma50)

    # ── ATR-based stop loss ───────────────────────────────────────────────────
    stop_loss_long  = round(price - 2 * atr, 2) if price and atr else None
    stop_loss_short = round(price + 2 * atr, 2) if price and atr else None

    # ── Volume signal ─────────────────────────────────────────────────────────
    curr_vol   = _safe(last["Volume"])
    avg_vol    = _safe(last["vol_ma20"])
    vol_ratio  = round(curr_vol / avg_vol, 2) if curr_vol and avg_vol else None
    obv_now    = _safe(df["obv"].iloc[-1])
    obv_5ago   = _safe(df["obv"].iloc[-6])
    obv_trend  = "Rising" if obv_now and obv_5ago and obv_now > obv_5ago else "Falling"

    # ── Signal scorecard ──────────────────────────────────────────────────────
    signals = {}

    # MA signals
    signals["Price vs SMA50"]  = "bullish" if price and sma50  and price > sma50  else "bearish"
    signals["Price vs SMA200"] = "bullish" if price and sma200 and price > sma200 else "bearish"
    signals["SMA50 vs SMA200"] = "bullish" if sma50 and sma200 and sma50 > sma200 else "bearish"  # golden/death cross

    # RSI
    if rsi:
        if rsi < 30:   signals["RSI"] = "bullish"   # oversold
        elif rsi > 70: signals["RSI"] = "bearish"   # overbought
        else:          signals["RSI"] = "neutral"

    # MACD
    if macd is not None and macd_sig is not None:
        signals["MACD"] = "bullish" if macd > macd_sig else "bearish"

    # Bollinger Bands
    if price and bb_upper and bb_lower:
        if price < bb_lower:   signals["Bollinger Bands"] = "bullish"   # oversold
        elif price > bb_upper: signals["Bollinger Bands"] = "bearish"   # overbought
        else:                  signals["Bollinger Bands"] = "neutral"

    # Volume
    signals["Volume"] = "bullish" if vol_ratio and vol_ratio > 1.2 else "neutral"

    # Overall score
    bull = sum(1 for v in signals.values() if v == "bullish")
    bear = sum(1 for v in signals.values() if v == "bearish")
    total = len(signals)
    score = bull / total if total else 0.5

    if score >= 0.7:     overall = "Strong Buy"
    elif score >= 0.55:  overall = "Buy"
    elif score >= 0.45:  overall = "Neutral"
    elif score >= 0.3:   overall = "Sell"
    else:                overall = "Strong Sell"

    # ── Chart data (last 1 year for performance) ──────────────────────────────
    chart_df = df.tail(252).copy()
    chart_df.index = chart_df.index.strftime("%Y-%m-%d")

    def series(col):
        return [_safe(v) for v in chart_df[col].values]

    dates = list(chart_df.index)

    # ── Ticker info ───────────────────────────────────────────────────────────
    info = {}
    try:
        info = yf.Ticker(ticker).info
    except Exception:
        pass

    return {
        "ticker": ticker,
        "name": info.get("shortName", ticker),
        "sector": info.get("sector", ""),
        "price": price,
        "atr": atr,

        # Trend
        "daily_trend": daily_trend,
        "weekly_trend": weekly_trend,
        "monthly_trend": monthly_trend,

        # MAs
        "sma50": sma50, "sma100": sma100, "sma200": sma200, "ema20": ema20,

        # Indicators
        "rsi": rsi,
        "macd": macd, "macd_signal": macd_sig, "macd_hist": macd_hist,
        "bb_upper": bb_upper, "bb_mid": bb_mid, "bb_lower": bb_lower,

        # Volume
        "volume": curr_vol, "avg_volume": avg_vol, "vol_ratio": vol_ratio,
        "obv_trend": obv_trend,

        # Levels
        "resistance": resistance,
        "support": support,
        "fib_levels": fib_levels,
        "swing_high": round(float(swing_high), 2),
        "swing_low": round(float(swing_low), 2),

        # Risk
        "stop_loss_long": stop_loss_long,
        "stop_loss_short": stop_loss_short,

        # Scorecard
        "signals": signals,
        "overall": overall,
        "bull_count": bull,
        "bear_count": bear,
        "signal_total": total,

        # Chart series
        "dates": dates,
        "open":   series("Open"),
        "high":   series("High"),
        "low":    series("Low"),
        "close":  series("Close"),
        "volume": series("Volume"),
        "s_sma50":  series("sma50"),
        "s_sma100": series("sma100"),
        "s_sma200": series("sma200"),
        "s_ema20":  series("ema20"),
        "s_rsi":    series("rsi"),
        "s_macd":   series("macd"),
        "s_macd_signal": series("macd_signal"),
        "s_macd_hist":   series("macd_hist"),
        "s_bb_upper": series("bb_upper"),
        "s_bb_lower": series("bb_lower"),
        "s_bb_mid":   series("bb_mid"),
        "s_obv":      series("obv"),
        "s_vol_ma20": series("vol_ma20"),
    }
