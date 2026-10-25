"""python3 -m valuation.report TICKER [--moat narrow] [--erp 4.5] [--g1 0.05] [--out reports] [--json]
Writes reports/<TICKER>_<date>.html, .md and .json (the data pack an LLM reads for the narrative step)."""
import argparse, datetime as dt, json, time
from pathlib import Path
import numpy as np, pandas as pd
from .data import company_pack
from .peers import peer_table, peer_beta, medians
from . import dcf
import plotly.graph_objects as go

OUT = Path(__file__).resolve().parent.parent / "reports"
INPUTS_DIR = Path(__file__).resolve().parent.parent / "inputs"


def build(ticker, moat=None, erp=0.045, g1=None, ov=None):
    t0 = time.time()
    p = company_pack(ticker)
    peers = peer_table(ticker, p["sector"])
    i = dcf.build_inputs(p, erp, peer_beta(peers), ov)
    moat = moat or i.get("moat") or "narrow"
    if g1 is not None:
        i["g1"] = g1
    base, flows, det = dcf.value(i, moat, detail=True)
    sc, mt, sens = dcf.scenarios(i, moat), dcf.moat_table(i), dcf.sensitivity(i, moat)
    impl = dcf.implied_growth(i, moat)
    iw = dcf.implied_wacc(i, moat)
    price, med = i["price"], medians(peers)
    ebitda = p["ebit"] + abs(p["da"] or 0)
    pe_val = med["trailingPE"] * p["eps"] if p.get("eps") else None
    ev_val = (med["enterpriseToEbitda"] * ebitda + i["cash"] - i["debt"]) / i["shares"] if ebitda > 0 else None
    cross = [v for v in (pe_val, ev_val) if v]
    cross_v = float(np.mean(cross)) if cross else None
    gap = (base - price) / max(base, price)
    flags = []
    if cross_v and abs(base - cross_v) / min(base, cross_v) > 0.5:
        flags.append(f"Intrinsic (${base:.0f}) and peer-multiple (${cross_v:.0f}) values differ by more than 50%.")
    if det["tv_share"] > 0.7:
        flags.append(f"Terminal value is {det['tv_share']:.0%} of enterprise value; result is assumption-sensitive.")
    if i["roc"] > 1:
        flags.append(f"Return on capital {i['roc']:.0%} (capital excludes goodwill); projection caps it at {dcf.ROC_CAP:.0%}.")
    if abs(i["fund_g"] - i["cagr"]) > 0.05:
        flags.append(f"Fundamental growth ({i['fund_g']:.1%}) and 3y revenue CAGR ({i['cagr']:.1%}) disagree; year-1 growth is their blend.")
    flags.append("Data: yfinance TTM + SEC XBRL history; peers = S&P 500 sector, peer-median beta; ERP is an input, not market-implied.")
    r = dict(ticker=p["ticker"], name=p["name"], sector=p["sector"], industry=p["industry"], as_of=p["as_of"],
             price=price, fair_value=base, gap=gap, moat=moat, inputs=i, scenarios=sc, moat_values=mt, sensitivity=sens,
             implied_g1=impl, implied_wacc=iw, tv_share=det["tv_share"], fcff=flows, peer_medians=med, n_peers=len(peers),
             cross={"pe": pe_val, "ev_ebitda": ev_val, "avg": cross_v}, flags=flags, pack=p,
             peers=peers.head(8).to_dict("records"), seconds=round(time.time() - t0, 1))
    return r


def _f(x, k="x"):
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else (f"{x:.1f}x" if k == "x" else f"{x:.1%}")


def markdown(r):
    i, p = r["inputs"], r["pack"]
    verdict = "overvalued" if r["gap"] < 0 else "undervalued"
    L = [f"# {r['name']} ({r['ticker']}) — valuation, {dt.date.today()}", "",
         f"**Fair value (base DCF): ${r['fair_value']:.2f}** vs price **${r['price']:.2f}** → **{abs(r['gap']):.0%} {verdict}**  ",
         f"{r['sector']} · {r['industry']} · financials through {r['as_of']} · moat: {r['moat']}", "",
         "## Scenarios", "| Case | Yr-1 growth | Target margin | WACC | Terminal g | Value |", "|---|---|---|---|---|---|"]
    for k, s in r["scenarios"].items():
        L.append(f"| {k} | {s['g1']:.1%} | {s['margin']:.1%} | {s['wacc']:.1%} | {s['g_term']:.1%} | ${s['value']:.2f} |")
    L += ["", f"At ${r['price']:.2f} the market prices in ~{_f(r['implied_g1'], '%')} growth for years 1–5 "
          f"(base assumes {i['g1']:.1%}). Holding the forecast fixed, the price implies a market discount rate of ~{_f(r['implied_wacc'], '%')} vs the model's {i['wacc1']:.1%}.", "", "## Key figures", "| Metric | Value |", "|---|---|"]
    for k, v in [("Market cap", f"${p['mcap']/1e9:.1f}B"), ("Revenue TTM", f"${p['revenue']/1e9:.1f}B"),
                 ("Operating income TTM", f"${p['ebit']/1e9:.1f}B ({i['margin0']:.1%})"), ("Net income TTM", f"${p['net_income']/1e9:.1f}B"),
                 ("EPS / P/E", f"{p['eps']} / {_f(p.get('pe'))}"), ("Debt / Cash", f"${i['debt']/1e9:.1f}B / ${i['cash']/1e9:.1f}B"),
                 ("Beta (peer median)", f"{i['beta']:.2f}"), ("Risk-free / ERP", f"{i['rf']:.2%} / {i['erp']:.1%}"),
                 ("WACC", f"{i['wacc1']:.1%} → {i['wacc10']:.1%}"), ("Tax", f"{i['t0']:.1%} → {i['t_end']:.0%}"),
                 ("Return on capital (ex-goodwill)", f"{i['roc']:.0%}"), ("Reinvestment rate", f"{i['rr']:.0%}")]:
        L.append(f"| {k} | {v} |")
    L += ["", "## Peer comparison", f"{r['n_peers']} S&P 500 {r['sector']} peers (median).", "| | " + r["ticker"] + " | Peer median |", "|---|---|---|"]
    pm = r["peer_medians"]
    L += [f"| P/E | {_f(p.get('pe'))} | {_f(pm['trailingPE'])} |",
          f"| EV/EBITDA | {_f((p['mcap']+i['debt']-i['cash'])/(p['ebit']+abs(p['da'] or 0)))} | {_f(pm['enterpriseToEbitda'])} |",
          f"| Operating margin | {i['margin0']:.1%} | {pm['operatingMargins']:.1%} |",
          f"| Net margin | {p['net_income']/p['revenue']:.1%} | {pm['profitMargins']:.1%} |",
          f"| Revenue growth (yoy) | – | {pm['revenueGrowth']:.1%} |", "",
          "| Peer | Mkt cap | P/E | EV/EBITDA |", "|---|---|---|---|"]
    L += [f"| {x['symbol']} | ${x['marketCap']/1e9:.0f}B | {_f(x.get('trailingPE'))} | {_f(x.get('enterpriseToEbitda'))} |" for x in r["peers"]]
    L += ["", "## How the fair value is built", "| Component | Per share |", "|---|---|", f"| DCF (FCFF), {r['moat']} moat | ${r['fair_value']:.2f} |",
          f"| Peer P/E cross-check | {('$%.2f' % r['cross']['pe']) if r['cross']['pe'] else '–'} |",
          f"| Peer EV/EBITDA cross-check | {('$%.2f' % r['cross']['ev_ebitda']) if r['cross']['ev_ebitda'] else '–'} |",
          "", "## Moat sensitivity", "| Moat | Value |", "|---|---|"]
    L += [f"| {k} | ${v:.2f} |" for k, v in r["moat_values"].items()]
    s = r["sensitivity"]
    L += ["", "## Sensitivity (value/share; rows WACC, columns terminal growth)", "| WACC \\ g | " + " | ".join(f"{g:.1%}" for g in s["g"]) + " |", "|---|" + "---|" * 5]
    L += [f"| {w:.1%} | " + " | ".join(f"${v:.0f}" for v in row) + " |" for w, row in zip(s["wacc"], s["grid"])]
    L += ["", "## Projected FCFF ($B)", " · ".join(f"Y{n+1}: {v/1e9:.1f}" for n, v in enumerate(r["fcff"])), "", "## Things to check"]
    L += [f"- {x}" for x in r["flags"]]
    notes = (r.get("overrides") or {}).get("notes")
    if notes:
        L += ["", "## Research notes (inputs)"] + [f"- **{k}:** {v}" for k, v in notes.items()]
    return "\n".join(L)


def md2html(t):
    import re
    out, tbl = [], []
    def flush():
        if tbl:
            rows = [[c.strip() for c in l.strip("|").split("|")] for l in tbl if not set(l) <= set("|-: ")]
            out.append("<table>" + "".join("<tr>" + "".join(f"<{'th' if n == 0 else 'td'}>{c}</{'th' if n == 0 else 'td'}>" for c in row) + "</tr>" for n, row in enumerate(rows)) + "</table>")
            tbl.clear()
    for l in t.split("\n"):
        if l.startswith("|"):
            tbl.append(l); continue
        flush()
        l = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", l.rstrip())
        if l.startswith("# "): out.append(f"<h1>{l[2:]}</h1>")
        elif l.startswith("## "): out.append(f"<h2>{l[3:]}</h2>")
        elif l.startswith("- "): out.append(f"<li>{l[2:]}</li>")
        elif l: out.append(f"<p>{l}</p>")
    flush()
    return "\n".join(out)


def html(r):
    p, i = r["pack"], r["inputs"]
    ph = pd.Series(p["price_hist"])
    f1 = go.Figure([go.Scatter(x=ph.index, y=ph.values, name="Price")])
    f1.add_hline(y=r["fair_value"], line_dash="dash", annotation_text=f"Fair value ${r['fair_value']:.0f}")
    f1.update_layout(height=320, margin=dict(t=20, b=20), title="Price vs. base fair value (5y weekly)")
    f2 = go.Figure([go.Bar(x=[f"Y{n+1}" for n in range(10)], y=[v / 1e9 for v in r["fcff"]])])
    f2.update_layout(height=300, margin=dict(t=30, b=20), title="Projected FCFF, base case ($B)")
    ed = {k: {int(a): b for a, b in v.items()} if isinstance(v, dict) else v for k, v in p["edgar"].items()}
    f3 = go.Figure()
    if ed.get("revenue"):
        ys = sorted(ed["revenue"])
        f3.add_bar(x=ys, y=[ed["revenue"][y] / 1e9 for y in ys], name="Revenue $B")
        f3.add_scatter(x=ys, y=[ed["op_income"].get(y, np.nan) / ed["revenue"][y] * 100 for y in ys], name="Op margin %", yaxis="y2")
        f3.update_layout(yaxis2=dict(overlaying="y", side="right"))
    f3.update_layout(height=320, margin=dict(t=30, b=20), title="Revenue and operating margin by fiscal year")
    figs = "".join(f.to_html(full_html=False, include_plotlyjs=(n == 0 and "cdn")) for n, f in enumerate([f1, f3, f2]))
    body = md2html(markdown(r))
    css = ("body{font:15px/1.5 -apple-system,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}"
           "table{border-collapse:collapse;margin:.5rem 0}td,th{border:1px solid #ddd;padding:4px 10px;text-align:right}"
           "td:first-child,th:first-child{text-align:left}h2{margin-top:2rem;border-bottom:1px solid #eee}")
    return f"<!doctype html><meta charset=utf-8><title>{r['ticker']} valuation</title><style>{css}</style>{body}<h2>Charts</h2>{figs}"


def main():
    a = argparse.ArgumentParser()
    a.add_argument("ticker"); a.add_argument("--moat", choices=list(dcf.MOAT_YEARS)); a.add_argument("--inputs", help="JSON of researched overrides (default inputs/<TICKER>.json if present)")
    a.add_argument("--erp", type=float, default=4.5); a.add_argument("--g1", type=float)
    a.add_argument("--out", default=str(OUT))
    a = a.parse_args()
    tk = a.ticker.upper()
    ovp = Path(a.inputs) if a.inputs else INPUTS_DIR / f"{tk}.json"
    ov = json.loads(ovp.read_text()) if ovp.exists() else None
    r = build(tk, a.moat, a.erp / 100, a.g1 / 100 if a.g1 and a.g1 > 1 else a.g1, ov)
    r["overrides"] = ov
    out = Path(a.out); out.mkdir(exist_ok=True)
    stem = out / f"{r['ticker']}_{dt.date.today()}"
    stem.with_suffix(".md").write_text(markdown(r))
    stem.with_suffix(".html").write_text(html(r))
    slim = {k: v for k, v in r.items() if k != "pack"}
    stem.with_suffix(".json").write_text(json.dumps(slim, default=float, indent=1))
    print(f"{r['ticker']}: fair ${r['fair_value']:.2f} vs price ${r['price']:.2f} ({r['gap']:+.0%}) in {r['seconds']}s → {stem}.html/.md/.json")


if __name__ == "__main__":
    main()
