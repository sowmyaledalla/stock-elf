"""Sector peers from data/sp500.csv; per-ticker yfinance info cached 7 days, fetched in parallel."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np, pandas as pd, yfinance as yf
from .data import _cached, CACHE

SP500 = Path(__file__).resolve().parent.parent / "data" / "sp500.csv"
SECTOR_MAP = {"Consumer Cyclical": "Consumer Discretionary", "Consumer Defensive": "Consumer Staples",
              "Technology": "Information Technology", "Healthcare": "Health Care", "Financial Services": "Financials",
              "Basic Materials": "Materials", "Real Estate": "Real Estate", "Energy": "Energy", "Utilities": "Utilities"}
FIELDS = ["marketCap", "trailingPE", "enterpriseToEbitda", "revenueGrowth", "operatingMargins",
          "profitMargins", "beta", "shortName", "industry"]


def _info(t):
    def f():
        try:
            i = yf.Ticker(t).info
            return {k: i.get(k) for k in FIELDS}
        except Exception:
            return {}
    v = _cached(f"peer_{t}.json", 24 * 7, f)
    if not v:
        (CACHE / f"peer_{t}.json").unlink(missing_ok=True)
    return v


def peer_table(ticker, sector, workers=16):
    sp = pd.read_csv(SP500)
    sector = SECTOR_MAP.get(sector, sector)
    syms = [s for s in sp.loc[sp["Sector"] == sector, "Symbol"] if s != ticker.upper()]
    syms = [s.replace(".", "-") for s in syms]
    with ThreadPoolExecutor(workers) as ex:
        infos = list(ex.map(_info, syms))
    df = pd.DataFrame([dict(symbol=s, **i) for s, i in zip(syms, infos) if i.get("marketCap")])
    return df.sort_values("marketCap", ascending=False).reset_index(drop=True)


def peer_beta(df):
    b = pd.to_numeric(df.get("beta"), errors="coerce").dropna()
    return float(np.clip(b.median(), 0.6, 1.5)) if len(b) >= 5 else None


def medians(df):
    return {k: float(pd.to_numeric(df[k], errors="coerce").median()) for k in
            ["trailingPE", "enterpriseToEbitda", "revenueGrowth", "operatingMargins", "profitMargins"]}
