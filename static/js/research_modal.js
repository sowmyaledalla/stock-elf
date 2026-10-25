// Research notes modal: turns a pasted company-narrative JSON (values + [F]/[J] notes) into an infographic you can keep next to the model.
// Used by /dcf and /dcf2. Needs Bootstrap, $, and (optionally) D = last /dcf/calc response for "page default" comparisons.
let RES = null;   // {notes, vals, stage, ticker}
const RN = { good:'#16a34a', judg:'#2563eb', warn:'#d97706', grey:'#94a3b8' };
const RN_STAGES = [['young','Young growth','#a855f7'],['growth','Growth','#2563eb'],['mature','Mature','#16a34a'],['declining','Declining','#ef4444']];
const RN_CURVES = [['growth','Revenue growth'],['op_margin','EBIT margin'],['tax','Tax rate on EBIT'],['da_pct','D&A % of revenue'],['capex_pct','CapEx % of revenue'],['nwc_pct','ΔNWC % of Δ revenue']];
// [note key, value key, label, kind]; kind: pct | usd | M (millions of dollars or shares) | n
const RN_INPUTS = [['revenue','rev0','Starting revenue','$B'],['g_term','g_term','Terminal growth','pct'],['risk_free','rf','Risk-free rate','pct'],['beta','beta','Beta','n'],['erp','erp','Equity risk premium','pct'],
  ['cost_debt','kd','Cost of debt','pct'],['tax','tax','Tax rate (debt shield)','pct'],['price','price','Share price','usd'],['shares','shares','Shares','M'],['debt','debt','Debt','$M'],
  ['cash','cash','Cash + ST investments','$M'],['p_fail','p_fail','Failure probability','pct'],['liq_ps','liq_ps','Liquidation value / share','usd'],['wacc','wacc1','WACC override','pct']];
const RN_SOURCES = /10-K|10-Q|8-K|earnings call|investor day|release|Damodaran|Yahoo|WSJ|YCharts|Trading Economics|Zacks|Economic Times|Bloomberg|Reuters|consensus|guidance|FactSet|Morningstar|S&P|Moody|Fitch/gi;
const rnEsc = s => String(s==null?'':s).replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

function rnClass(text){
  const t=(text||'').trim();
  if(/^(\[(F|J)\]\s*)?unverified/i.test(t)) return 'warn';   // only a note that leads with "Unverified" counts as unverified; a judgment that mentions one gap stays a judgment
  if(t.startsWith('[F]')) return 'good';
  if(t.startsWith('[J]')) return 'judg';
  return 'grey';
}
const rnLabel = {good:'FACT',judg:'JUDGMENT',warn:'UNVERIFIED',grey:'NOTE'};
const rnBody = t => rnEsc((t||'').replace(/^\s*\[(F|J)\]\s*/,''));
function rnChips(text){
  const dates=[...new Set((text||'').match(/\d{4}-\d{2}-\d{2}/g)||[])], src=[...new Set(((text||'').match(RN_SOURCES)||[]).map(x=>x.replace(/^\w/,c=>c.toUpperCase())))];
  return [...src.map(x=>`<span class="rn-chip src">${rnEsc(x)}</span>`), ...dates.map(x=>`<span class="rn-chip dt">${x}</span>`)].join('');
}
function rnFmt(v,kind){
  if(v==null) return '—';
  if(kind==='pct') return (v*100).toFixed(2).replace(/\.?0+$/,'')+'%';
  if(kind==='usd') return '$'+v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
  if(kind==='$B') return '$'+(v/1e9).toFixed(2)+'B';
  if(kind==='$M') return '$'+Math.round(v/1e6).toLocaleString('en-US')+'M';
  if(kind==='M') return (v/1e6).toLocaleString('en-US',{maximumFractionDigits:0})+'M';
  return String(+v.toFixed(3));
}
function rnSpark(vals, def, color){
  const W=250,H=72,P=8, all=[...vals,...(def||[])].filter(x=>x!=null), lo=Math.min(...all), hi=Math.max(...all), sp=(hi-lo)||0.01;
  const X=i=>P+i*(W-2*P)/9, Y=v=>H-P-(v-lo)/sp*(H-2*P), pts=a=>a.map((v,i)=>`${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(' ');
  const f=v=>(v*100).toFixed(1)+'%';
  return `<svg viewBox="0 0 ${W} ${H+14}" class="rn-spark">
    ${def?`<polyline points="${pts(def)}" fill="none" stroke="${RN.grey}" stroke-width="1.5" stroke-dasharray="4 3"/>`:''}
    <polyline points="${pts(vals)}" fill="none" stroke="${color}" stroke-width="2.5"/>
    ${vals.map((v,i)=>`<circle cx="${X(i).toFixed(1)}" cy="${Y(v).toFixed(1)}" r="${i===0||i===9?3.5:2}" fill="${color}"/>`).join('')}
    <text x="${P}" y="${H+11}" font-size="9" fill="#64748b">Y1 ${f(vals[0])}</text><text x="${W-P}" y="${H+11}" font-size="9" fill="#64748b" text-anchor="end">Y10 ${f(vals[9])}</text></svg>`;
}
function rnLifecycle(stage){
  const W=360,H=110,f=t=>Math.exp(-Math.pow((t-0.45)/0.27,2)), X=t=>10+t*340, Y=t=>96-72*f(t);
  const path=Array.from({length:61},(_,k)=>{const t=k/60;return `${k?'L':'M'}${X(t).toFixed(1)},${Y(t).toFixed(1)}`;}).join(' ');
  const bands=[[0,.15],[.15,.4],[.4,.7],[.7,1]], mid=[.075,.275,.55,.85], idx=RN_STAGES.findIndex(s=>s[0]===stage);
  return `<svg viewBox="0 0 ${W} ${H+16}" class="rn-life">
    ${bands.map(([a,b],k)=>`<rect x="${X(a)}" y="6" width="${X(b)-X(a)}" height="${H-12}" fill="${RN_STAGES[k][2]}" opacity="${k===idx?0.20:0.07}"/>`).join('')}
    <path d="${path}" fill="none" stroke="#475569" stroke-width="2"/>
    ${bands.map(([a,b],k)=>`<text x="${(X(a)+X(b))/2}" y="${H+11}" font-size="9.5" text-anchor="middle" fill="${RN_STAGES[k][2]}" font-weight="${k===idx?700:400}">${RN_STAGES[k][1]}</text>`).join('')}
    ${idx>=0?`<circle cx="${X(mid[idx])}" cy="${Y(mid[idx])}" r="7" fill="${RN_STAGES[idx][2]}" stroke="#fff" stroke-width="2"/>`:''}</svg>`;
}
function rnDonut(c){
  const tot=c.good+c.judg+c.warn+c.grey||1, R=44, C=2*Math.PI*R; let off=0;
  const arcs=[['good',RN.good],['judg',RN.judg],['warn',RN.warn],['grey',RN.grey]].map(([k,col])=>{ const len=c[k]/tot*C, s=`<circle r="${R}" cx="60" cy="60" fill="none" stroke="${col}" stroke-width="16" stroke-dasharray="${len} ${C-len}" stroke-dashoffset="${-off}" transform="rotate(-90 60 60)"/>`; off+=len; return s; }).join('');
  return `<svg viewBox="0 0 120 120" class="rn-donut">${arcs}<text x="60" y="58" text-anchor="middle" font-size="22" font-weight="700" fill="#1e293b">${tot}</text><text x="60" y="73" text-anchor="middle" font-size="9" fill="#64748b">notes</text></svg>`;
}
function setResearch(r, open){
  const ov=r.overrides||{}, {notes, ...vals}=ov;
  if(!notes || !Object.keys(notes).length) return;
  RES={notes, vals, stage:r.stage||'', ticker:(r.ticker||'').toUpperCase()};
  const b=$('rnBtn'); if(b) b.style.display='';
  const imp=$('imp');   // the paste dialog is still open: open the notes once it has closed, so the two backdrops do not stack
  if(open){ if(imp&&imp.classList.contains('show')){ imp.addEventListener('hidden.bs.modal',()=>openResearch(),{once:true}); bootstrap.Modal.getOrCreateInstance(imp).hide(); } else openResearch(); }
}
function setResearchSaved(ov, ticker){
  if(!ov||!ov.notes||!Object.keys(ov.notes).length) return;
  const {notes,...vals}=ov; RES={notes,vals,stage:'',ticker:(ticker||'').toUpperCase()}; const b=$('rnBtn'); if(b) b.style.display='';
}
function openResearch(){
  if(!RES) return;
  if(!$('rnModal')){
    document.body.insertAdjacentHTML('beforeend','<div class="modal fade" id="rnModal" tabindex="-1"><div class="modal-dialog modal-xl modal-dialog-scrollable"><div class="modal-content"><div class="modal-header py-2"><h5 class="modal-title" id="rnTitle"></h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body" id="rnBody" style="background:#f8fafc"></div></div></div></div>');
  }
  const {notes, vals, stage, ticker}=RES, defs=(typeof D!=='undefined'&&D&&D.defaults)||{}, dtraj=(typeof D!=='undefined'&&D&&D.traj_default)||{};
  const used=new Set(['ticker','stage','traj','stock_based_compensation','capital_structure','data_quality','unverified']);
  const cnt={good:0,judg:0,warn:0,grey:0}; Object.values(notes).forEach(t=>cnt[rnClass(t)]++);
  const st=RN_STAGES.find(s=>s[0]===(stage||(/growth|mature|young|declining/i.exec(notes.stage||'')||[''])[0].toLowerCase()))||null;
  const cutoff=((notes.data_quality||'').match(/\d{4}-\d{2}-\d{2}/)||[''])[0];
  $('rnTitle').innerHTML=`Research notes · <b>${rnEsc(ticker||'')}</b>`;
  const badge=k=>`<span class="rn-badge ${k}">${rnLabel[k]}</span>`;
  const curve=([k,label])=>{
    const v=(vals.traj||{})[k], n=notes['traj.'+k], c=rnClass(n), df=dtraj[k];
    if(!v) return `<div class="rn-card"><div class="rn-h">${label}${badge('warn')}</div><div class="rn-na">Not supplied: the page keeps its own default curve.</div>${n?`<div class="rn-note">${rnBody(n)}</div>`:''}</div>`;
    const d10=df?(v[9]-df[9]):null;
    return `<div class="rn-card"><div class="rn-h">${label}${badge(c)}</div>${rnSpark(v,df,RN[c==='grey'?'judg':c])}
      <div class="rn-legend"><span><i style="background:${RN[c==='grey'?'judg':c]}"></i>pasted</span>${df?'<span><i class="dash"></i>model default</span>':''}${d10!=null?`<span class="rn-delta">yr 10 vs default: ${d10>=0?'▲':'▼'} ${(Math.abs(d10)*100).toFixed(1)} pts</span>`:''}</div>
      <div class="rn-note">${rnBody(n)}</div><div>${rnChips(n)}</div></div>`; };
  const inp=([nk,vk,label,kind])=>{
    used.add(nk); const n=notes[nk]; let v=vals[vk]; const c=n?rnClass(n):'grey', dflt=defs[vk];
    const missing=v==null;
    return `<div class="rn-card sm"><div class="rn-h">${label}${n?badge(c):''}</div><div class="rn-val">${missing?'<span class="rn-na">not supplied</span>':rnFmt(v,kind)}</div>
      ${dflt!=null&&!missing&&Math.abs(dflt-v)>1e-9?`<div class="rn-def">page default ${rnFmt(dflt,kind)}</div>`:''}${missing&&dflt!=null?`<div class="rn-def">using default ${rnFmt(dflt,kind)}</div>`:''}
      ${n?`<div class="rn-note">${rnBody(n)}</div><div>${rnChips(n)}</div>`:''}</div>`; };
  RN_INPUTS.forEach(x=>used.add(x[0])); used.add('short_term_investments'); used.add('traj'); Object.keys(notes).filter(k=>k.startsWith('traj.')).forEach(k=>used.add(k));
  const ctx=[['stock_based_compensation','Stock-based compensation'],['capital_structure','Capital structure'],['data_quality','Data quality'],['stage','Stage rationale'],['traj','Curve basis'],['short_term_investments','Short-term investments']]
    .filter(([k])=>notes[k]).map(([k,l])=>`<div class="rn-card sm"><div class="rn-h">${l}${badge(rnClass(notes[k]))}</div><div class="rn-note">${rnBody(notes[k])}</div><div>${rnChips(notes[k])}</div></div>`).join('');
  const extra=Object.keys(notes).filter(k=>!used.has(k)&&!['ticker'].includes(k)).map(k=>`<div class="rn-card sm"><div class="rn-h">${rnEsc(k)}${badge(rnClass(notes[k]))}</div><div class="rn-note">${rnBody(notes[k])}</div></div>`).join('');
  const gaps=[...(notes.unverified?[notes.unverified.replace(/^\s*\[(F|J)\]\s*Unverified:?\s*/i,'')]:[]).flatMap(t=>t.replace(/\.$/,'').split(/,\s*(?:and\s+)?/)).filter(Boolean),
    ...Object.entries(notes).filter(([k,t])=>k!=='unverified'&&rnClass(t)==='warn').map(([k])=>`${k.replace(/_/g,' ')} (flagged)`)];
  $('rnBody').innerHTML=`
  <div class="rn-hero"><div class="rn-hero-l"><div class="rn-big" style="color:${st?st[2]:'#475569'}">${st?st[1]:'Stage not stated'}</div><div class="rn-note" style="max-width:340px">${rnBody(notes.stage)}</div>
      ${cutoff?`<div class="rn-chip dt mt-1">research cutoff ${cutoff}</div>`:''}</div>
    <div>${rnLifecycle(st?st[0]:'')}</div>
    <div class="rn-hero-r">${rnDonut(cnt)}<div class="rn-key"><div>${badge('good')} ${cnt.good} facts</div><div>${badge('judg')} ${cnt.judg} judgments</div><div>${badge('warn')} ${cnt.warn} unverified</div></div></div></div>
  <div class="rn-sec">Driver curves <span>pasted vs the model's default</span></div><div class="rn-grid">${RN_CURVES.map(curve).join('')}</div>
  <div class="rn-sec">Inputs <span>with the page's own default when different</span></div><div class="rn-grid sm">${RN_INPUTS.map(inp).join('')}</div>
  ${ctx?`<div class="rn-sec">Context</div><div class="rn-grid sm">${ctx}</div>`:''}
  ${extra?`<div class="rn-sec">Other notes</div><div class="rn-grid sm">${extra}</div>`:''}
  ${gaps.length?`<div class="rn-sec">Gaps to check before you trust it</div><div class="rn-gaps">${gaps.map(g=>`<span class="rn-chip gap">${rnEsc(g)}</span>`).join('')}</div>`:''}`;
  bootstrap.Modal.getOrCreateInstance($('rnModal')).show();
}
