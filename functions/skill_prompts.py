"""InvestSkill prompts, ready to paste into any LLM: loads prompts/<skill>.md and fills in the ticker."""
import os, re
from pathlib import Path
import pandas as pd

LOCAL_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"  # prompts authored in this repo
SP500 = Path(__file__).resolve().parent.parent / "data" / "sp500.csv"

# (group, skill file, label, one-line hint) — single-stock skills only
SKILLS = [
    ("Evaluate", "company-narrative", "Company Narrative", "Sourced facts + assumptions for every DCF input, as JSON for /dcf2 (no calculations)"),
]
_ALLOWED = {s[1] for s in SKILLS}


def skill_catalog():
    out = {}
    for g, name, label, hint in SKILLS:
        out.setdefault(g, []).append({"skill": name, "label": label, "hint": hint})
    return out


def company_name(ticker):
    try:
        df = pd.read_csv(SP500)
        m = df.loc[df["Symbol"].str.upper() == ticker.upper(), "Name"]
        return m.iloc[0] if len(m) else None
    except Exception:
        return None


def build_prompt(skill, ticker):
    if skill not in _ALLOWED:
        raise ValueError(f"unknown skill: {skill}")
    ticker = re.sub(r"[^A-Za-z0-9.\-]", "", ticker).upper()
    if not ticker:
        raise ValueError("ticker required")
    text = (LOCAL_PROMPTS / f"{skill}.md").read_text(encoding="utf-8")
    name = company_name(ticker)
    who = f"{name} ({ticker})" if name else ticker
    text = re.sub(r"\[TICKER\]|\[SYMBOL\]|\[Ticker\]|<ticker>|\{ticker\}|\{TICKER\}|\bTICKER\b|\$ARGUMENTS", ticker, text)
    if name:
        text = re.sub(r"\[Company Name\]|\[Company\]", name, text)
    head = (f"You are running the \"{skill}\" task below. Subject: **{who}**.\n"
            "Use live web/search data where you can; otherwise ask me to paste figures. Follow the output structure below exactly.\n\n---\n\n")
    return head + text
