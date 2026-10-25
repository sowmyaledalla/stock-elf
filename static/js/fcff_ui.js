// Shared FCFF UI (used by /dcf and /dcf2): editable driver curves, company-type presets, effective margins, historical FCFF build, forecast table.
// Needs from the page: $ , nf, calc() (re-run the valuation), and the elements these functions fill (#drvGrid, #preset, #presetNote, #stageBox, #eff, #effCard, #effWin, #hb, #histCard, #ft).
// State: D = the last /dcf/calc response, TRO = curves the user edited ({driver: [10 values]}).
let D = null, TRO = {}, PASTED_STAGE = '';   // PASTED_STAGE: life-cycle stage named in pasted research (shown next to the SEC-history suggestion)
let EFF = null;
function effective(d){
  const H=d.hist_build, V=k=>H.rows.find(r=>r.key===k).vals, n=H.cols.length, w=$('effWin').value;
  const idx = w==='ttm' ? [n-1] : Array.from({length:+w},(_,j)=>n-2-j).filter(k=>k>=0).reverse();   // fiscal-year columns (the last column is TTM)
  const rev=V('revenue'), sum=(k,ix)=>ix.reduce((a,j)=>a+(V(k)[j]||0),0), okIx=(...ks)=>idx.filter(j=>ks.every(k=>V(k)[j]!=null));
  const dn=okIx('dnwc'), drev=j=>(j>0&&rev[j]!=null&&rev[j-1]!=null)?rev[j]-rev[j-1]:null, dnx=dn.filter(j=>drev(j)!=null);
  const fx=okIx('fcff'), rx=okIx('fcf');
  const e={ op_margin:sum('ebit',idx)/sum('revenue',idx), tax:sum('tax',idx)/sum('ebit',idx), da_pct:sum('da',idx)/sum('revenue',idx), capex_pct:sum('capex',idx)/sum('revenue',idx),
    nwc_pct: dnx.length? dnx.reduce((a,j)=>a+V('dnwc')[j],0)/dnx.reduce((a,j)=>a+drev(j),0) : null,
    fcff_margin: fx.length? fx.reduce((a,j)=>a+V('fcff')[j],0)/fx.reduce((a,j)=>a+rev[j],0) : null,
    fcf_margin: rx.length? rx.reduce((a,j)=>a+V('fcf')[j],0)/rx.reduce((a,j)=>a+rev[j],0) : null };
  e.years = idx.map(j=>H.cols[j]).join(', ');
  e.implied = e.op_margin*(1-e.tax)+e.da_pct-e.capex_pct;   // FCFF margin before working capital
  return e;
}
function drawEffective(){
  if(!D||D.engine!=='fcff') return; const e=EFF=effective(D), p=v=>v==null?'—':(v*100).toFixed(1)+'%';
  const cur_=k=>D.traj[k][0];
  $('eff').innerHTML='<tr><th></th><th>Effective</th><th>Forecast Y1 now</th></tr>'+
    [['EBIT margin','op_margin'],['Tax rate on EBIT','tax'],['D&A % of revenue','da_pct'],['CapEx % of revenue','capex_pct'],['ΔNWC % of change in revenue','nwc_pct']].map(([l,k])=>`<tr><td>${l}</td><td><b>${p(e[k])}</b></td><td>${p(cur_(k))}</td></tr>`).join('')+
    `<tr class="tot"><td>FCFF margin, from these steps (before ΔNWC)</td><td><b>${p(e.implied)}</b></td><td></td></tr><tr><td>FCFF margin, reported years (with ΔNWC)</td><td>${p(e.fcff_margin)}</td><td></td></tr><tr><td>Memo: reported FCF margin (operating cash flow − CapEx)</td><td>${p(e.fcf_margin)}</td><td></td></tr>`+
    `<tr><td colspan="3" class="text-secondary" style="text-align:left">Years used: ${e.years}</td></tr>`;
  $('effCard').style.display='block';
}
function activateEffective(){
  const e=EFF; if(!e) return; PRESET='';
  const flat=v=>Array(10).fill(Math.round(v*10000)/10000);
  ['op_margin','tax','da_pct','capex_pct','nwc_pct'].forEach(k=>{ if(e[k]!=null&&isFinite(e[k])) TRO[k]=flat(e[k]); });
  calc();
}
let EDG_FOR = null;
function drawHistory(d){
  const H=d.hist_build, f=(v,u)=>v==null?'—':u=='pct'?(v*100).toFixed(1)+'%':nf(v,0);
  $('hb').innerHTML='<tr><th></th>'+H.cols.map(c=>`<th>${c}</th>`).join('')+'</tr>'+H.rows.map(r=>
    `<tr class="${r.kind=='total'?'tot':r.kind=='ratio'?'sub':''}"${r.kind=='memo'?' style="color:#94a3b8"':''}><td>${r.label}</td>`+r.vals.map(v=>`<td class="${v!=null&&v<0&&r.unit=='m'?'neg':''}">${f(v,r.unit)}</td>`).join('')+'</tr>').join('');
  $('histCard').style.display='block';
  if($('edgBox') && $('edgBox').style.display!=='none') loadEdgarRaw(d.ticker);
}
function toggleEdgar(){ const b=$('edgBox'); b.style.display=b.style.display==='none'?'block':'none'; if(b.style.display!=='none') loadEdgarRaw(D.ticker); }
async function loadEdgarRaw(t){
  if(EDG_FOR===t) return; const e=await (await fetch('/dcf2/data?ticker='+encodeURIComponent(t))).json(); if(e.error){ $('edg').innerHTML=`<tr><td>${e.error}</td></tr>`; return; }
  let sec='', h='<tr><th></th>'+e.cols.map(c=>`<th>${c}</th>`).join('')+'<th style="text-align:left">XBRL tag (latest)</th></tr>';
  e.rows.forEach(r=>{ if(r.section!=sec){ sec=r.section; h+=`<tr class="sec"><td colspan="${e.cols.length+2}">${sec}</td></tr>`; }
    const last=[...r.src].reverse().find(x=>x), fm=v=>v==null?'—':r.unit=='pct'?(v*100).toFixed(1)+'%':nf(v,r.unit=='n'?1:0);
    h+=`<tr><td>${r.label}</td>`+r.vals.map((v,i)=>{ const s=r.src[i]; return `<td class="${v!=null&&v<0?'neg':''}"${s?` title="${s.tag} · ${s.form} filed ${s.filed} · ${s.accn}`+'"':''}>${fm(v)}</td>`; }).join('')+`<td style="text-align:left;font-size:.7rem;color:#64748b">${last?last.tag:'calculated'}</td></tr>`; });
  $('edg').innerHTML=h; $('edgFilings').innerHTML=e.filings.map(f=>`<a href="${f.url}" target="_blank" rel="noopener">${f.form} ${f.filed}</a>`).join(' · '); EDG_FOR=t;
}
const TRAJ = ['growth','op_margin','tax','da_pct','capex_pct','nwc_pct'];
const STEP = {growth:0.01, op_margin:0.005, tax:0.01, da_pct:0.0025, capex_pct:0.0025, nwc_pct:0.01};
const YL = Array.from({length:10},(_,k)=>'Y'+(k+1));
const DRV = {};            // per driver: {gd, range, hist, drag}
let calcTimer = null, builtFor = null;
const HN = () => Math.min(5, D.history.labels.length);
const cur = k => (TRO[k] || D.traj[k]);
const round3 = v => Math.round(v*1000)/1000;
function scheduleCalc(){ clearTimeout(calcTimer); calcTimer = setTimeout(calc, 350); }
function setCurve(k, arr){ TRO[k] = arr.map(round3); scheduleCalc(); refreshDriver(k); }
function resetDriver(k){ delete TRO[k]; calc(); }
function resetDrivers(){ TRO = {}; PRESET = ''; calc(); }
let PRESET = '';
function applyPreset(k){ PRESET = k; if(!k){ TRO = {}; calc(); return; } TRO = Object.fromEntries(Object.entries(D.presets[k].traj).map(([d,a])=>[d,a.map(round3)])); calc(); }
function drawPresets(d){
  const sel=$('preset'); sel.innerHTML='<option value="">Model default</option>'+['flat','young','growth','mature','declining'].map(k=>`<option value="${k}">${d.presets[k].name}</option>`).join('')+'<option value="_custom" disabled>Custom (edited)</option>';
  const same = PRESET && TRAJ.every(k=>TRO[k] && TRO[k].every((v,j)=>Math.abs(v-round3(d.presets[PRESET].traj[k][j]))<1e-9));
  sel.value = same ? PRESET : (Object.keys(TRO).length ? '_custom' : '');
  const st=d.stage, sk=(PASTED_STAGE&&d.presets[PASTED_STAGE])?PASTED_STAGE:st.key, shown = same ? PRESET : sk, g=d.presets[shown].guide;
  [...sel.options].forEach(o=>{ if(o.value===sk) o.textContent=d.presets[o.value].name+(sk===PASTED_STAGE?' (from your research)':' (suggested)'); });
  $('stageBox').innerHTML=(sk===PASTED_STAGE?`<b>Stage from your pasted research: ${d.presets[sk].name}</b> <span class="text-secondary">(SEC-history rules suggest ${st.name}: ${st.reasons.join('; ')}).</span> `
    :`<b>Suggested stage from SEC history: ${st.name}</b> <span class="text-secondary">— ${st.reasons.join('; ')}.</span> `)+(PRESET===sk&&same?'':`<a href="#" onclick="applyPreset('${sk}');return false">replace curves with the ${d.presets[sk].name} preset</a>`);
  $('presetNote').innerHTML=(same?`<div class="mb-1"><b>${d.presets[PRESET].name} curves:</b> ${d.presets[PRESET].note}</div>`:'')+
    `<div><b>${d.presets[shown].name} companies</b> · ${g.attributes}<br><i>Valuation issue:</i> ${g.issue}<br><i>Solution:</i> ${g.solution}</div>`;
}
function shiftDriver(k, dir){ setCurve(k, cur(k).map(v=>v+dir*STEP[k])); }
function rampDriver(k){ const a=parseFloat($('ra_'+k).value), b=parseFloat($('rb_'+k).value); if(isNaN(a)||isNaN(b)) return;
  setCurve(k, Array.from({length:10},(_,y)=>a/100+(b-a)/100*y/9)); }
function buildDrivers(){
  $('drvGrid').innerHTML = TRAJ.map(k=>`<div class="drv" id="drv_${k}">
    <div class="drv-h"><b>${D.traj_labels[k]}</b><span class="bd" id="bd_${k}">default</span><a onclick="resetDriver('${k}')">reset</a></div>
    <div id="dc_${k}"></div>
    <div class="drv-in">${YL.map(y=>`<div class="yl">${y}</div>`).join('')}${YL.map((y,j)=>`<input id="in_${k}_${j}" onchange="editBox('${k}',${j},this.value)">`).join('')}</div>
    <div class="drv-tools">shift <button class="btn btn-outline-secondary" onclick="shiftDriver('${k}',-1)">−${(STEP[k]*100).toFixed(STEP[k]<0.01?2:0)}pt</button><button class="btn btn-outline-secondary" onclick="shiftDriver('${k}',1)">+${(STEP[k]*100).toFixed(STEP[k]<0.01?2:0)}pt</button>
      &nbsp; ramp Y1 <input id="ra_${k}" placeholder="%"> → Y10 <input id="rb_${k}" placeholder="%"><button class="btn btn-outline-primary" onclick="rampDriver('${k}')">apply</button></div></div>`).join('');
  TRAJ.forEach(k=>{ DRV[k]={gd:$('dc_'+k)}; });
  builtFor = D.ticker;
}
function editBox(k,j,txt){ const v=parseFloat(txt); if(isNaN(v)) { refreshDriver(k); return; } const a=cur(k).slice(); a[j]=v/100; setCurve(k,a); }
function driverTraces(k){
  const H=D.history, n=HN(), hl=H.labels.slice(-n).map(l=>l.startsWith('TTM')?'TTM':"'"+l.slice(2)), start=D.traj_start[k], rg=driverRange(k);
  const hv=H[k].slice(-n).map(v=>v!=null&&v>=rg[0]&&v<=rg[1]?v:null);   // history outside the chart range (loss-year tax, noisy ΔNWC) is left out of the line
  const xs=[...hl,...YL], pad=Array(YL.length).fill(null), lead=Array(n-1).fill(null);
  return [
    {x:xs,y:[...hv,...pad],mode:'lines+markers',name:'history',line:{color:'#94a3b8',width:1.5},marker:{size:5,color:'#94a3b8'},hovertemplate:'%{x}: %{y:.1%}<extra>history</extra>'},
    {x:xs,y:[...lead,start,...D.traj[k]].map(v=>v),name:'default',mode:'lines',line:{color:'#94a3b8',dash:'dash',width:1.5},hoverinfo:'skip'},
    {x:xs,y:[...lead,start,...cur(k)],name:'yours',mode:'lines+markers',line:{color:'#2563eb',width:2.5},marker:{size:[...Array(n).fill(0),...Array(10).fill(9)],color:'#2563eb'},hovertemplate:'%{x}: %{y:.1%}<extra>yours</extra>'}];
}
function driverRange(k){
  const vals=[...D.traj[k],...cur(k),D.traj_start[k]].filter(v=>v!=null&&isFinite(v)); let lo=Math.min(...vals), hi=Math.max(...vals); const span=Math.max(hi-lo,0.04);
  const l0=lo, h0=hi;   // recent history stretches the range when it is within 3 spans of the forecast; wilder values (loss-year tax, noisy ΔNWC) stay off-chart
  D.history[k].slice(-HN()).forEach(v=>{ if(v!=null&&v>=l0-3*span&&v<=h0+3*span){ lo=Math.min(lo,v); hi=Math.max(hi,v); } });
  const sp=Math.max(hi-lo,0.04);
  return [lo-sp*0.15, hi+sp*0.15];
}
function drawDrivers(d){
  if(builtFor!==d.ticker || !$('drv_growth')) buildDrivers();
  TRAJ.forEach(k=>{
    const o=DRV[k], gd=o.gd; o.range=driverRange(k);
    const layout={height:190,margin:{t:6,b:22,l:42,r:8},showlegend:false,dragmode:false,hovermode:'closest',
      xaxis:{type:'category',categoryarray:driverTraces(k)[0].x,fixedrange:true,tickfont:{size:9},tickangle:0},
      yaxis:{range:o.range,tickformat:'.0%',fixedrange:true,tickfont:{size:9},zeroline:true,zerolinecolor:'#e2e8f0'}};
    Plotly.react(gd, driverTraces(k), layout, {displayModeBar:false});
    if(!gd._wired){ gd._wired=true; wireDrag(k); }
    refreshDriver(k, true);
  });
}
function refreshDriver(k, skipPlot){
  const a=cur(k); a.forEach((v,j)=>{ const e=$(`in_${k}_${j}`); if(e && document.activeElement!==e) e.value=(v*100).toFixed(1); });
  const edited=!!TRO[k]; $('drv_'+k).classList.toggle('edited',edited); $('bd_'+k).textContent=edited?'edited':'default';
  if(!skipPlot && DRV[k].gd.data) Plotly.restyle(DRV[k].gd,{y:[[...Array(HN()-1).fill(null),D.traj_start[k],...a]]},[2]);
}
function wireDrag(k){
  const gd=DRV[k].gd; let drag=-1;
  const geom=e=>{ const fl=gd._fullLayout, bb=gd.getBoundingClientRect(); return {fl,bb,x:e.clientX-bb.left,y:e.clientY-bb.top}; };
  const nHist=HN;
  const pick=e=>{ const {fl,x,y}=geom(e), a=cur(k); let best=-1,bd=16;
    a.forEach((v,j)=>{ const px=fl.xaxis._offset+fl.xaxis.l2p(nHist()+j), py=fl.yaxis._offset+fl.yaxis.l2p(v); const dd=Math.hypot(px-x,py-y); if(dd<bd){bd=dd;best=j;} }); return best; };
  gd.addEventListener('mousedown',e=>{ const j=pick(e); if(j>=0){ drag=j; TRO[k]=cur(k).slice(); e.preventDefault(); e.stopPropagation(); } },true);
  window.addEventListener('mousemove',e=>{
    if(drag<0){ if(e.target&&gd.contains(e.target)) gd.style.cursor = pick(e)>=0?'ns-resize':'default'; return; }
    const {fl,y}=geom(e); let v=fl.yaxis.p2l(y-fl.yaxis._offset); const r=DRV[k].range; v=round3(Math.min(Math.max(v,r[0]),r[1]));
    TRO[k][drag]=v; refreshDriver(k); });
  window.addEventListener('mouseup',()=>{ if(drag>=0){ drag=-1; scheduleCalc(); } });
}
function drawForecast(d){
  const R=d.rows, M=v=>nf(v/1e6,0), P=v=>v==null?'–':(v*100).toFixed(1)+'%';
  const line=(l,f,cls)=>`<tr class="${cls||''}"><td>${l}</td>${R.map(r=>`<td>${f(r)}</td>`).join('')}</tr>`;
  $('ft').innerHTML=`<tr><th></th>${R.map(r=>`<th>Y${r.year}</th>`).join('')}</tr>`+
    line('Revenue',r=>M(r.revenue))+line('growth',r=>P(r.growth),'sub')+line('EBIT',r=>M(r.ebit))+line('operating margin',r=>P(r.op_margin),'sub')+
    line('− Tax on EBIT',r=>M(r.ebit-r.nopat))+line('tax rate',r=>P(r.tax_rate),'sub')+line('NOPAT',r=>M(r.nopat),'tot')+
    line('+ D&amp;A',r=>M(r.da))+line('− CapEx',r=>M(r.capex))+line('− ΔNWC',r=>M(r.dnwc))+line('FCFF',r=>M(r.fcff),'tot')+
    line('Discount factor',r=>r.df.toFixed(3),'sub')+line('PV of FCFF',r=>M(r.pv));
}

// ── reverse DCF: what the market price implies (server: fcff.reverse_dcf). Needs #revBox.
function drawReverse(d){
  const R=d.reverse, box=$('revBox'); if(!box) return;
  if(!R){ box.innerHTML='<div class="text-secondary">No share price available, so there is nothing to solve against.</div>'; return; }
  const p1=v=>v==null?'—':(v*100).toFixed(1)+'%', M=v=>v==null?'—':'$'+nf(v/1e6,0)+'M', usd=v=>'$'+nf(v,2), I=d.inputs;
  const note={
    growth:s=>s.implied==null?'no growth path in the tested range reaches the price':`= ${p1(s.extra.cagr10)} a year over 10 years (your curves: ${p1(s.extra.current_cagr10)}); the last 3 fiscal years averaged ${p1(R.hist_growth_avg3)}`,
    op_margin:s=>s.implied==null?'no margin in the tested range reaches the price':`highest fiscal-year EBIT margin in the history: ${p1(s.extra.hist_max)}`+(s.extra.hist_max!=null&&s.implied>s.extra.hist_max?' — the price needs a margin the company has not reached':''),
    g_term:s=>s.implied==null?'not reachable':(s.implied>0.035?'above long-run economic growth (~2–3%): unrealistic, so the price is not explained by terminal growth alone':'within a plausible range'),
    wacc:s=>s.implied==null?'not reachable':`the return you earn if the forecast comes true and you pay today's price; your required return is ${p1(s.current)}`};
  const row=s=>`<tr><td>${s.label}</td><td>${p1(s.current)}</td><td><b>${s.implied==null?'—':p1(s.implied)}</b></td><td style="text-align:left;white-space:normal">${note[s.key](s)}</td><td>${s.curve?`<button class="btn btn-outline-primary btn-sm py-0" onclick="applyReverse('${s.target}')">show curve</button>`:''}</td></tr>`;
  const g=R.tradeoff, gap=(R.price-R.model_value)/R.price;
  const gs=R.solves.find(x=>x.key==='growth'), ms=R.solves.find(x=>x.key==='op_margin');
  box.innerHTML=`
  <div class="subh">1 · Market enterprise value (what the market pays for the whole business)</div>
  <div class="calc">Market cap = ${usd(R.price)} × ${nf(I.shares/1e6,0)}M shares = <span class="res">${M(R.market_cap)}</span><br>+ Debt ${M(R.debt)} − Cash ${M(R.cash)}<br><b>Market EV = <span class="res">${M(R.market_ev)}</span></b> &nbsp;vs&nbsp; your model's EV ${M(R.model_ev)} (value ${usd(R.model_value)} per share, ${Math.abs(gap*100).toFixed(0)}% ${gap>0?'below':'above'} the price)</div>
  <div class="subh">2 · Fixed inputs</div>
  <div class="calc">Baseline FCFF (latest 12 months): <span class="res">${M(R.ttm_fcff)}</span>${R.ttm_fcff!=null&&R.ttm_revenue?` (${p1(R.ttm_fcff/R.ttm_revenue)} of revenue)`:''} &nbsp;·&nbsp; WACC ${p1(R.wacc)} &nbsp;·&nbsp; terminal growth ${p1(I.g_term)} &nbsp;·&nbsp; every other curve as set above</div>
  <div class="subh">3 · What the price implies, one lever at a time</div>
  <div style="overflow-x:auto"><table class="t"><tr><th>Lever</th><th>Your assumption</th><th>Price implies</th><th style="text-align:left">Reading</th><th></th></tr>${R.solves.map(row).join('')}</table></div>
  <div class="subh">4 · Growth and margin together: the trade-off</div>
  <div class="src mb-1">Many growth/margin combinations justify the same price. Each row shifts the growth path, then solves the EBIT margin (every year shifted equally) that brings the value to the price.</div>
  <div style="overflow-x:auto"><table class="t"><tr><th>Year-1 growth</th><th>Revenue growth a year, 10 years</th><th>Required year-10 EBIT margin</th><th></th></tr>${g.map((x,k)=>`<tr><td>${p1(x.growth1)}</td><td>${p1(x.cagr10)}</td><td><b>${p1(x.margin10)}</b></td><td><button class="btn btn-outline-primary btn-sm py-0" onclick="applyReverse('grid',${k})">use both curves</button></td></tr>`).join('')}</table></div>
  <div class="subh">5 · How to read it</div>
  <div class="calc" style="font-family:inherit;line-height:1.6">At ${usd(R.price)}, with your other assumptions, the market is pricing in ${gs.implied==null?'growth outside the tested range':`revenue growth of about <b>${p1(gs.implied)}</b> in year 1 (${p1(gs.extra.cagr10)} a year over 10 years)`}, <i>or</i> an EBIT margin of about <b>${ms.implied==null?'beyond the tested range':p1(ms.implied)}</b> by year 10 (today ${p1(ms.current)}), <i>or</i> a ${p1(R.solves.find(x=>x.key==='wacc').implied)} return. Compare each with the company's history and what you found in your research: the one that looks hardest to reach is what the price depends on. "show curve" loads the solved curve into the editor so you can see it, and "Reset all curves" returns to your own.</div>`;
}
function applyReverse(kind, k){
  const R=D.reverse, rd=x=>x.map(v=>Math.round(v*10000)/10000); PRESET='';
  if(kind==='grid'){ const x=R.tradeoff[k]; TRO.growth=rd(x.growth_curve); if(x.margin_curve) TRO.op_margin=rd(x.margin_curve); }
  else { const s=R.solves.find(x=>x.target===kind); if(s&&s.curve) TRO[kind]=rd(s.curve); }
  calc();
}
