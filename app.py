"""Stock Elf, a self-service stock researcher (standalone): Evaluate, DCF and Technicals pages. Uses only public data (yfinance, SEC EDGAR, Finviz); no accounts or API keys."""
import json
import os
from pathlib import Path

import plotly
from flask import Flask, render_template, request, jsonify

from functions.finvizfinance_api import get_FinViz_profile, finvizfinance
from functions.technicals_api import get_technicals
from valuation.report import INPUTS_DIR as DCF_INPUTS_DIR

app = Flask(__name__, static_url_path='/static')


@app.route("/")
@app.route("/home")
def home():
    return render_template('home.html')


# ── Documentation pages ──────────────────────────────────────────────────────

@app.route("/how-to-use")
def how_to_use():
    return render_template('docs/how_to_use.html')


@app.route("/methodology")
def methodology():
    return render_template('docs/methodology_index.html')


@app.route("/methodology/dcf")
def methodology_dcf():
    return render_template('docs/methodology_dcf.html')


@app.route("/methodology/technicals")
def methodology_technicals():
    return render_template('docs/methodology_technicals.html')


# ── Evaluate ─────────────────────────────────────────────────────────────────

@app.route("/evaluate", methods=['GET'])
def evaluate():
    ticker = (request.args.get('ticker') or '').upper().strip()
    if not ticker:
        return render_template('home.html')
    try:
        finviz_estimates = get_FinViz_profile(ticker)
    except Exception:
        finviz_estimates = []
    try:
        description = finvizfinance(ticker).ticker_description()
        profile = {'logo_url': "https://financialmodelingprep.com/image-stock/" + ticker + ".png", 'longBusinessSummary': description}
    except Exception:
        profile = []
    chart_data = json.dumps({'ticker': ticker, 'profile': profile, 'finviz profile': finviz_estimates},
                            indent=2, cls=plotly.utils.PlotlyJSONEncoder)
    return render_template('evaluation_landing.html', data=chart_data, ticker=ticker)


# ── Technicals ───────────────────────────────────────────────────────────────

@app.route('/technicals', methods=['GET'])
def technicals():
    ticker = request.args.get('ticker', '').upper().strip()
    if not ticker:
        return render_template('layouts/technicals.html', data=json.dumps({}), ticker='')
    try:
        data = get_technicals(ticker)
    except Exception as e:
        data = {'error': str(e), 'ticker': ticker}
    return render_template('layouts/technicals.html', data=json.dumps(data, cls=plotly.utils.PlotlyJSONEncoder), ticker=ticker)


# ── Skill prompts (copy-to-clipboard prompts for any LLM) ────────────────────

@app.route("/skills/catalog")
def skills_catalog():
    from functions.skill_prompts import skill_catalog
    return jsonify(skill_catalog())


@app.route("/skills/prompt")
def skills_prompt():
    from functions.skill_prompts import build_prompt
    try:
        return build_prompt(request.args.get('skill', ''), request.args.get('ticker', '')), 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return str(e), 400, {'Content-Type': 'text/plain; charset=utf-8'}


# ── DCF Calculator (FCFF, researched inputs) ─────────────────────────────────
from valuation.report import build as dcf_build

DCF_FIELDS = ['g1', 'target_margin', 'margin_years', 'wacc1', 'wacc10', 'beta', 'erp', 'rf', 'g_term',
              'tax_end', 't_end', 'roc_cap', 'shares', 'debt', 'cash', 'moat', 'rev0', 'margin0', 's2c', 'moat_years', 'growth_fade']

def _dcf_payload(ticker, ov):
    ov = {k: v for k, v in (ov or {}).items() if v not in (None, '')}
    if 't_end' not in ov and 'tax_end' in ov:
        ov['t_end'] = ov.pop('tax_end')
    r = dcf_build(ticker, ov=ov or None)
    base = dcf_build(ticker)['inputs'] if ov else r['inputs']
    keep = ['g1', 'target_margin', 'margin_years', 'wacc1', 'wacc10', 'beta', 'erp', 'rf', 'g_term', 't_end',
            'roc_cap', 'shares', 'debt', 'cash', 'rev0', 'margin0', 'roc', 'rr', 'cagr', 'analyst_g', 'fund_g', 'price',
            's2c', 'moat_years', 'growth_fade']
    pk = r['pack']
    return {'ticker': r['ticker'], 'name': r['name'], 'sector': r['sector'], 'industry': r['industry'], 'as_of': r['as_of'],
            'price': r['price'], 'fair_value': r['fair_value'], 'gap': r['gap'], 'moat': r['moat'],
            'scenarios': r['scenarios'], 'moat_values': r['moat_values'], 'sensitivity': r['sensitivity'],
            'implied_g1': r['implied_g1'], 'implied_wacc': r['implied_wacc'], 'tv_share': r['tv_share'],
            'fcff': r['fcff'], 'cross': r['cross'], 'flags': r['flags'], 'n_peers': r['n_peers'],
            'inputs': {k: r['inputs'].get(k) for k in keep}, 'defaults': {k: base.get(k) for k in keep},
            'price_hist': pk['price_hist'], 'seconds': r['seconds']}

def _dcf_payload_staged(ticker, ov, stages):
    """The /dcf response for the staged engine (valuation/staged.py, the same engine as /dcf2), in the shape the /dcf page already shows."""
    import time
    from valuation import staged as stg
    from valuation.methodology import wacc_parts
    from valuation.edgar_table import edgar_table
    t0 = time.time()
    E = edgar_table(ticker)
    D = E['defaults']
    i, st, wacc, explicit = stg.apply_overrides(D, ov, stages)
    r = stg.full(i, st, wacc=wacc)
    if r.get('error'):
        raise ValueError(r['error'])
    price = i['price']
    gap = r['gap']
    scen = {k: dict(value=v['value'], g1=v['g1'], margin=next(iter(v['margins'].values())), margins=v['margins'], wacc=v['wacc'], g_term=v['g_term'])
            for k, v in r['scenarios'].items()}
    rows, n = r['rows'], r['stages']['n']
    stage_rows = []
    for stage, length, m in ((1, st['len1'], st['m1']), (2, st['len2'], st['m2'])):
        sr = [x for x in rows if x['stage'] == stage]
        if sr:
            stage_rows.append(dict(stage=stage, first=sr[0]['year'], last=sr[-1]['year'], method=m, name=stg.NAMES[m], growth_first=sr[0]['growth'],
                                   growth_last=sr[-1]['growth'], margin_first=sr[0]['fcf_margin'], margin_last=sr[-1]['fcf_margin']))
    keep = ['g1', 'g_term', 'beta', 'erp', 'rf', 'kd', 'tax', 'shares', 'debt', 'cash', 'rev0', 'price', 'fcf_margin']
    dcfg = stg.default_stage_config(D)
    state = dict(len1=st['len1'], len2=st['len2'], m1=st['m1'], m2=st['m2'], p1=explicit['p1'], p2=explicit['p2'])
    for k in ('g2_start', 'g2_end', 'g2_list'):
        if explicit.get(k) is not None:
            state[k] = explicit[k]
    return {'engine': 'staged', 'ticker': E['ticker'], 'name': E['name'], 'sector': 'Simple DCF', 'industry': '', 'as_of': E['ends'][-1],
            'price': price, 'fair_value': r['per_share'], 'gap': gap, 'moat': 'n/a',
            'scenarios': scen, 'moat_values': {}, 'sensitivity': r['sensitivity'], 'stage_rows': stage_rows, 'tv_multiple': r['tv_multiple'],
            'implied_g1': stg.implied_g1(i, st, wacc=wacc), 'implied_wacc': stg.implied_wacc(i, st),
            'tv_share': r['tv_share'], 'fcff': r['fcf'], 'cross': {'pe': None, 'ev_ebitda': None}, 'n_peers': 0,
            'flags': r['flags'], 'horizon': n,
            'inputs': {**{k: i[k] for k in keep}, 'growth_fade': r['growth'][5:], 'wacc1': r['wacc']},
            'defaults': {**{k: D[k] for k in keep}, 'growth_fade': stg.default_growth_fade(D), 'wacc1': wacc_parts(D)['w_calc']},
            'stage_state': state, 'stage_defaults': dict(p1=dcfg['p1'], p2=dcfg['p2']),
            'price_hist': E['price_hist'], 'seconds': round(time.time() - t0, 1)}

def _dcf_payload_fcff(ticker, ov):
    """The /dcf response for the textbook FCFF engine (valuation/fcff.py): per-year driver trajectories (defaults + yours), history and the full forecast table."""
    import time
    from valuation import fcff
    from valuation.edgar_table import edgar_table
    t0 = time.time()
    E = edgar_table(ticker)
    D = dict(E['defaults'], last_growth=E['last_growth'], p_fail=0.0, liq_ps=0.0)
    i, tr, wacc = fcff.apply_overrides(D, ov)
    r = fcff.full(i, tr, wacc=wacc)
    if r.get('error'):
        raise ValueError(r['error'])
    i0, dtr, _ = fcff.apply_overrides(D, {})
    keep = ['g_term', 'beta', 'erp', 'rf', 'kd', 'tax', 'rev0', 'shares', 'debt', 'cash', 'price', 'p_fail', 'liq_ps']
    return {'engine': 'fcff', 'ticker': E['ticker'], 'name': E['name'], 'sector': 'Textbook FCFF', 'industry': '', 'as_of': E['ends'][-1],
            'price': i['price'], 'fair_value': r['per_share'], 'gap': r['gap'], 'moat': 'n/a',
            'scenarios': r['scenarios'], 'moat_values': {}, 'sensitivity': r['sensitivity'], 'tv_multiple': r['tv_multiple'],
            'implied_g1': fcff.implied_growth(i, tr, wacc=wacc), 'implied_wacc': fcff.implied_wacc(i, tr),
            'tv_share': r['tv_share'], 'fcff': r['fcff'], 'rows': r['rows'], 'cross': {'pe': None, 'ev_ebitda': None}, 'n_peers': 0,
            'flags': r['flags'], 'horizon': 10,
            'wacc_build': {k: r[k] for k in ('ke', 'equity_mv', 'wd', 'we', 'kd_after_tax', 'wacc_calc', 'wacc')},
            'terminal': {k: r[k] for k in ('fcff_next', 'nopat_next', 'terminal_reinvestment_rate', 'implied_terminal_roic', 'tv', 'tv_pv', 'pv_sum', 'ev', 'equity')},
            'tax_wacc': i['tax'], 'fallbacks': E.get('fallbacks', []), 'market_note': E.get('market_note'),
            'reverse': fcff.reverse_dcf(i, tr, wacc=wacc, hb=fcff.history_build(E)), 'presets': fcff.presets(i), 'stage': fcff.detect_stage(E, D), 'dcf_per_share': r['dcf_per_share'], 'hist_build': fcff.history_build(E), 'traj': tr, 'traj_default': dtr, 'traj_start': fcff.start_values(D), 'history': fcff.history(E), 'traj_labels': fcff.LABELS,
            'inputs': {**{k: i[k] for k in keep}, 'wacc1': r['wacc']},
            'defaults': {**{k: D[k] for k in keep}, 'wacc1': r['wacc_calc'] if wacc is None else fcff.run(i0, dtr)['wacc_calc']},
            'price_hist': E['price_hist'], 'seconds': round(time.time() - t0, 1)}

@app.route('/dcf', methods=['GET'])
def dcf_page():
    return render_template('layouts/dcf.html', ticker=request.args.get('ticker', '').upper().strip())

@app.route('/dcf/calc', methods=['POST'])
def dcf_calc():
    body = request.get_json() or {}
    ticker = (body.get('ticker') or '').upper().strip()
    if not ticker:
        return jsonify({'error': 'ticker required'}), 400
    try:
        ov = body.get('overrides')
        if ov is None:  # first load: pick up researched inputs saved by the skill/CLI
            f = DCF_INPUTS_DIR / f'{ticker}.json'
            ov = json.loads(f.read_text()) if f.exists() else {}
        eng = body.get('engine') or 'fcff'
        if eng == 'fcff':
            out = _dcf_payload_fcff(ticker, ov)
        elif eng == 'staged':
            # the simple model: years 1-5 at g1, years 6-10 at growth_fade, FCF = revenue x FCF margin (stage lengths and methods 2/4 are
            # backed up in backups/methods_2_4_staged; any stage set-up sent by the page or saved in a file is ignored)
            out = _dcf_payload_staged(ticker, ov, None)
        elif eng == 'current':
            out = _dcf_payload(ticker, ov)
        else:
            return jsonify({'error': f'unknown engine: {eng}'}), 400
        out['loaded_overrides'] = ov
        return jsonify(out)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/dcf/snapshot', methods=['GET'])
def dcf_snapshot():
    from valuation.snapshot import snapshot
    try:
        return jsonify(snapshot(request.args.get('ticker', '')))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/dcf2', methods=['GET'])
def dcf2_page():
    return render_template('layouts/dcf_steps.html', ticker=request.args.get('ticker', '').upper().strip())

@app.route('/dcf2/data', methods=['GET'])
def dcf2_data():
    from valuation.edgar_table import edgar_table
    try:
        return jsonify(edgar_table(request.args.get('ticker', '')))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/dcf2/calc', methods=['POST'])
def dcf2_calc():
    from valuation import methodology as mth
    try:
        body = request.get_json() or {}
        raw = {k: float(v) for k, v in body.get('inputs', {}).items() if v is not None and not isinstance(v, (list, str))}
        fade = body.get('inputs', {}).get('growth_fade')
        missing = [k for k in mth.KEYS + mth.TECH_KEYS if k not in raw]
        if missing:
            return jsonify({'error': 'missing inputs: ' + ', '.join(missing)}), 400
        i = {k: raw[k] for k in mth.KEYS}
        i.update({k: raw[k] for k in ('g2', 'two_stage') if k in raw})
        if isinstance(fade, list) and len(fade) == 5 and not raw.get('two_stage'):
            i['growth_fade'] = [float(x) for x in fade]
        out = mth.forecast(i, {k: raw[k] for k in mth.TECH_KEYS + ['roic_term'] if k in raw})
        m = int((request.get_json() or {}).get('method') or 1)
        ch = out['t%d' % m] if m < 4 else out['t1']
        dam_t = {k: raw[k] for k in mth.DAM_KEYS if k in raw}
        dam_t.update(moat=body.get('inputs', {}).get('moat') or 'narrow', moat_years=raw.get('moat_years'))
        dam = mth.damodaran(i, dam_t, wacc=raw.get('wacc'), wacc10=raw.get('wacc10')) if len(dam_t) >= 7 else None
        if dam:
            rv = out['revenue']
            out['t4'] = dict(fcf=dam['fcf'], fcf_next=dam['fcf_next'], rows=dam['rows'], margin=[f / r for f, r in zip(dam['fcf'], rv)], sum=sum(dam['fcf']))
        out['val'] = dam if (m == 4 and dam) else mth.run(i, wacc=raw.get('wacc'), fcf=ch['fcf'], fcf_next=ch['fcf_next'])
        out['method'] = m
        return jsonify(out)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/dcf2/staged', methods=['POST'])
def dcf2_staged():
    """Three-stage DCF (valuation/staged.py): body = {inputs: {...}, stages: {len1, len2, m1, m2, g2_start, g2_end, g2_list}, wacc?}."""
    from valuation import staged as stg
    try:
        body = request.get_json() or {}
        raw = body.get('inputs', {})
        i = {k: float(v) for k, v in raw.items() if v is not None and not isinstance(v, (list, str))}
        st = {k: v for k, v in (body.get('stages') or {}).items() if v is not None}
        for k in ('len1', 'len2', 'm1', 'm2'):
            if k in st:
                st[k] = int(st[k])
        for k in ('g2_start', 'g2_end'):
            if k in st:
                st[k] = float(st[k])
        if st.get('g2_list'):
            st['g2_list'] = [float(x) for x in st['g2_list']]
        for k in ('p1', 'p2'):  # each stage's own method inputs
            if k in st:
                st[k] = {pk: float(pv) for pk, pv in (st[k] or {}).items() if pv is not None and not isinstance(pv, (list, str))}
        w = body.get('wacc')
        return jsonify(stg.full(i, st, wacc=float(w) if w is not None else None))
    except (ValueError, KeyError) as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/dcf/import', methods=['POST'])
def dcf_import():
    from valuation.importer import parse_text, normalize_full
    try:
        ov, ticker, warns, meta = normalize_full(parse_text((request.get_json() or {}).get('text') or ''))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'overrides': ov, 'ticker': ticker, 'warnings': warns, **meta})

@app.route('/dcf/save', methods=['POST'])
def dcf_save():
    body = request.get_json() or {}
    ticker = (body.get('ticker') or '').upper().strip()
    if not ticker.isalnum() and '-' not in ticker:
        return jsonify({'error': 'bad ticker'}), 400
    DCF_INPUTS_DIR.mkdir(exist_ok=True)
    (DCF_INPUTS_DIR / f'{ticker}.json').write_text(json.dumps(body.get('overrides') or {}, indent=2))
    return jsonify({'ok': True, 'path': str(DCF_INPUTS_DIR / f'{ticker}.json')})



if __name__ == "__main__":
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', 8000)), debug=False)
