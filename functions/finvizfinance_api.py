#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import time
import requests
from bs4 import BeautifulSoup

from finvizfinance.quote import finvizfinance

_FINVIZ_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def _scrape_finviz_fundament(symb: str) -> dict:
    """Direct scraper for Finviz snapshot table — resilient to library breakage."""
    url = f'https://finviz.com/quote.ashx?t={symb.upper()}'
    r = requests.get(url, headers=_FINVIZ_HEADERS, timeout=10)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    tds = soup.find_all('td', class_='snapshot-td2')
    pairs = {}
    for i in range(0, len(tds) - 1, 2):
        pairs[tds[i].text.strip()] = tds[i + 1].text.strip()
    # Also grab sector/industry/country from the header area
    for tag in soup.find_all('a', class_=lambda c: c and 'tab-link' in c):
        href = tag.get('href', '')
        if 'sec=' in href and 'Sector' not in pairs:
            pairs['Sector'] = tag.text.strip()
        elif 'ind=' in href and 'Industry' not in pairs:
            pairs['Industry'] = tag.text.strip()
        elif 'geo=' in href and 'Country' not in pairs:
            pairs['Country'] = tag.text.strip()
    # Grab company name and price from header
    name_tag = soup.find('h2', class_=lambda c: c and 'quote-header' in str(c))
    if not name_tag:
        name_tag = soup.find('h1')
    if name_tag and 'Company' not in pairs:
        pairs['Company'] = name_tag.text.strip().split('(')[0].strip()
    return pairs

def getFinvizInfo_stocklist(stocklist,symbol="Symbol"):
    finviz_records = []

    for index,row in stocklist.iterrows():
        time.sleep(1)
        symb = row[symbol]
        try:
            stock = finvizfinance(symb)
            a = stock.ticker_fundament()
            b = {key:str(a[key]) for key in a}
            b['ticker'] = symb
            finviz_records.append(b)
            print(symb, "success")
        except Exception as e:
            print(symb," - error :: ",e)
            pass

    finviz_df = pd.DataFrame.from_dict(finviz_records)
    return finviz_df

def get_FinViz_profile(symb):
    # Try the library first; fall back to direct scraper if it breaks
    try:
        stock = finvizfinance(symb)
        a = stock.ticker_fundament()
        if a:
            result = {key: str(a[key]) for key in a}
        else:
            result = _scrape_finviz_fundament(symb)
    except Exception:
        result = _scrape_finviz_fundament(symb)

    # Sector/Industry are JS-rendered on Finviz — fill from yfinance if missing
    if not result.get('Sector') or not result.get('Industry'):
        try:
            import yfinance as yf
            info = yf.Ticker(symb).info
            if not result.get('Sector'):
                result['Sector'] = info.get('sector', '')
            if not result.get('Industry'):
                result['Industry'] = info.get('industry', '')
            if not result.get('Company'):
                result['Company'] = info.get('shortName', symb)
        except Exception:
            pass

    return result
