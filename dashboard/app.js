/* Presentation only: no financial number, formula or assumption lives here. */
const groups = {
  market: [
    ['tokenized_equity_aum','Tokenized equity AUM'],['tokenized_equity_volume','Tokenized equity volume · TTM'],
    ['global_equity_market','Global equity market'],['tokenized_equity_penetration','Observed penetration'],
    ['tokenized_equity_tam','Modeled TAM scenario'],['model_tokenized_equity_aum','Modeled AUM for UNI economics']
  ],
  uni: [
    ['uni_market_cap','Market cap'],['uni_fdv','Fully diluted value'],['gross_uni_accrual','Gross protocol accrual'],
    ['growth_distribution_value','Growth distribution value'],['other_dilution_value','Other dilution'],
    ['net_uni_accrual','Net UNI accrual'],['net_burn_yield','Net burn yield'],
    ['required_uni_accrual','Required accrual'],['required_uniswap_market_share','Standalone required market share'],
    ['incremental_required_share','Incremental required share']
  ],
  secz: [
    ['secz_price','Synthetic instrument price'],['secz_market_cap','Market cap'],['secz_fdv','Fully diluted value'],['secz_ev','Enterprise value'],['secz_revenue','Total revenue · TTM'],
    ['secz_tokenization_revenue','Tokenization'],['secz_servicing_revenue','Asset servicing'],
    ['secz_transaction_revenue','Transactions'],['secz_issuer_saas_revenue','Issuer SaaS / maintenance'],
    ['secz_fund_admin_revenue','Fund administration'],['secz_other_revenue','Other revenue'],
    ['secz_aum','AUM'],['secz_volume','Transaction volume'],['secz_revenue_growth','Revenue growth'],
    ['secz_aum_growth','AUM growth'],['secz_revenue_efficiency','Revenue efficiency'],
    ['secz_volume_monetization','Volume monetization'],['secz_ebitda','EBITDA'],
    ['secz_operating_leverage','Operating leverage'],['secz_required_revenue','Required revenue'],
    ['secz_required_revenue_cagr','Required revenue CAGR']
  ],
  xlm: [
    ['xlm_market_cap','Market cap'],['xlm_fdv','Fully diluted value'],['xlm_rwa_value','Network RWA value'],['xlm_stablecoin_supply','Stablecoin supply'],
    ['xlm_stablecoin_transfer_volume','Stablecoin transfers · TTM'],['xlm_active_addresses','Active addresses'],['xlm_institutional_issuers','Institutional issuers'],
    ['xlm_transfer_volume','Transfer volume · TTM'],['xlm_operations','Operations · TTM'],
    ['xlm_network_fee_value','Network fees · USD'],['xlm_locked_demand','Locked native demand · XLM'],
    ['xlm_native_demand_growth','Native demand growth'],['xlm_rwa_growth','RWA growth'],
    ['xlm_institutional_growth','Institutional asset growth'],['xlm_economic_capture_ratio','Economic capture ratio']
  ]
};
const knobs = [
  ['tokenized_equity_tam','Tokenized equity TAM'],['turnover','Annual turnover'],
  ['onchain_share','Onchain share'],['amm_share','AMM share'],
  ['effective_protocol_fee_bp','Effective protocol fee'],['uniswap_market_share','Uniswap market share'],
  ['required_yield','Required yield'],['growth_budget_uni','Growth dilution · UNI/year'],
  ['target_fcf_margin','Target FCF margin'],['terminal_multiple','Terminal FCF multiple']
];
const v1scope = id => displayed?.legacy_scopes?.[id]??'V1 · UNMIGRATED';
let base, displayed;
const $ = id => document.getElementById(id);
function node(tag, cls, text) { const x=document.createElement(tag); if(cls)x.className=cls; if(text!==undefined)x.textContent=text; return x; }
function fmt(value, unit) {
  if(value===null || value===undefined || !Number.isFinite(value))return 'Unknown';
  if(unit==='FRACTION')return (value*100).toLocaleString(undefined,{maximumFractionDigits:2})+'%';
  if(unit==='BP')return value.toLocaleString(undefined,{maximumFractionDigits:3})+' bp';
  if(unit==='MULTIPLE')return value.toLocaleString(undefined,{maximumFractionDigits:2})+'×';
  if(unit==='YEARS')return value.toLocaleString()+' years';
  if(unit==='USD_PER_UNI'||unit==='USD_PER_XLM')return '$'+value.toLocaleString(undefined,{maximumFractionDigits:5})+'/'+unit.split('_').pop();
  let sign=value<0?'-':''; let n=Math.abs(value);
  if(n>=1e12)return sign+(unit==='USD'?'$':'')+(n/1e12).toFixed(2)+'T';
  if(n>=1e9)return sign+(unit==='USD'?'$':'')+(n/1e9).toFixed(2)+'B';
  if(n>=1e6)return sign+(unit==='USD'?'$':'')+(n/1e6).toFixed(2)+'M';
  return sign+(unit==='USD'?'$':'')+n.toLocaleString(undefined,{maximumFractionDigits:3})+(unit==='UNI'?' UNI':unit==='XLM'?' XLM':'');
}
function metricCard(id,label,m) {
  const button=node('button','metric');button.type='button';button.addEventListener('click',()=>inspect(id));
  button.append(node('div','label',label),node('div','value',fmt(m.value,m.unit)));
  const t=node('div','tag '+m.classification.toLowerCase()+(m.fixture?' fixture':''),m.classification+(m.fixture?' · DEMO':'')+' · '+v1scope(id));button.append(t);
  return button;
}
function drawMetrics(data){ for(const [group,ids] of Object.entries(groups)){const target=$(group+'-grid');target.replaceChildren(); for(const [id,label] of ids)target.append(metricCard(id,label,data.metrics[id]));} }
function table(headers,rows){const t=node('table');const thead=node('thead');const tr=node('tr');headers.forEach(v=>tr.append(node('th','',v)));thead.append(tr);t.append(thead);const body=node('tbody');rows.forEach(cells=>{const line=node('tr');cells.forEach(c=>{const td=node('td',c?.warning?'warning':'',c?.text??String(c??''));line.append(td)});body.append(line)});t.append(body);return t;}
function drawMatrix(d){const x=d.matrix;const rows=x.turnover.map((turn,i)=>[turn+'×',...x.cells[i].map(v=>({text:fmt(v,'FRACTION'),warning:v!==null&&v>1}))]);$('matrix').replaceChildren(table(['Turnover / fee',...x.fee_bp.map(f=>f+' bp')],rows));}
function svg(tag, attrs, text){const v=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,val] of Object.entries(attrs))v.setAttribute(k,val);if(text!==undefined)v.textContent=text;return v;}
function drawGraph(d){const target=$('network');target.replaceChildren();const ids=Object.keys(d.assets);const coords={};ids.forEach((id,i)=>{const col=i%4,row=Math.floor(i/4);coords[id]={x:117+col*228,y:72+row*152};});target.setAttribute('viewBox','0 0 920 '+(Math.ceil(ids.length/4)*152+65));
  for(const edge of d.graph.edges){const a=coords[edge.from],b=coords[edge.to];if(a.x===b.x&&a.y===b.y){target.append(svg('circle',{cx:a.x,cy:a.y,r:66,fill:'none',stroke:'#efb170','stroke-dasharray':'5 5'}));continue;}target.append(svg('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,class:edge.economic_transmission?'economic':''}));}
  for(const id of ids){const {x,y}=coords[id];target.append(svg('rect',{x:x-71,y:y-24,width:142,height:48,rx:8}));target.append(svg('text',{x,y:y+5,'text-anchor':'middle'},id));}
  const edges=$('edges');edges.replaceChildren();for(const e of d.graph.edges){const item=node('span',e.economic_transmission?'economic':'',`${e.from} → ${e.to} · ${e.type} · ${e.evidence}`);edges.append(item);}
  const events=$('events');events.replaceChildren();for(const e of d.events)events.append(node('span','',`${e.type}: ${e.status}${e.fixture?' · DEMO':''}`));
}
function drawThesis(d){
  const target=$('thesis-grid');target.replaceChildren();
  const keyMetrics={UNI:['net_burn_yield','required_uniswap_market_share'],SECZ:['secz_aum_growth','secz_revenue_growth'],XLM:['xlm_rwa_growth','xlm_native_demand_growth','xlm_economic_capture_ratio']};
  for(const [asset,entry] of Object.entries(d.thesis)){
    const card=node('article','thesis-card');card.append(node('h3','',asset));
    card.append(node('strong',entry.state==='HEALTHY'?'':'stress',entry.state??'UNKNOWN DATA'),node('p','',entry.why),node('p','',`Last changed: ${entry.last_changed??'unknown'}`));
    for(const id of keyMetrics[asset]){const metric=d.metrics[id];const b=node('button','dep',`${id}: ${fmt(metric.value,metric.unit)}`);b.onclick=()=>inspect(id);card.append(b);}
    if(entry.triggered_rules.length){for(const rule of entry.triggered_rules)card.append(node('p','',`${rule.rule_id}: ${rule.why} (${rule.supporting_periods.map(x=>x.date).join(', ')})`));}
    else card.append(node('p','','Triggered rules: none'));
    if(entry.insufficient_rules.length)card.append(node('p','',`Insufficient evidence: ${entry.insufficient_rules.map(x=>x.rule_id).join(', ')}`));
    target.append(card);
  }
}
function drawComparison(d){const c=d.comparison;if(!c){$('version-summary').textContent='No earlier snapshot. Run bootstrap-demo or take another validated snapshot.';$('diff').replaceChildren();return;}
  $('version-summary').textContent=`${c.previous_date} (${c.previous_id}) → ${c.current_date} (${c.current_id}) · ${Object.keys(c.changes).length} lineage/value changes`;
  const rows=Object.entries(c.changes).sort((a,b)=>a[0].localeCompare(b[0])).map(([name,x])=>[name,fmt(x.previous,x.unit),fmt(x.current,x.unit),x.reason]);$('diff').replaceChildren(table(['Metric','Previous','Current','Reason'],rows));}
function facts(container,label,value){const item=node('div','fact');item.append(node('b','',label),node('span','',String(value??'—')));container.append(item);}
function inspect(id){const m=displayed.metrics[id];if(!m)return;$('inspection-title').textContent=id;const detail=$('inspection-detail');detail.replaceChildren();const grid=node('div','facts');facts(grid,'VALUE',fmt(m.value,m.unit));facts(grid,'UNIT',m.unit);facts(grid,'CLASSIFICATION',m.classification+(m.fixture?' · DEMO':''));facts(grid,'ECONOMIC SCOPE',v1scope(id));facts(grid,'AS OF',m.as_of_date??'—');facts(grid,'CONFIDENCE',m.confidence);facts(grid,'FORMULA',m.formula_id?`${m.formula_id}@${m.formula_version}`:'—');facts(grid,'RECORD VERSION',m.record_ids.join(', ')||'—');facts(grid,'PERIOD',m.period?`${m.period.basis}: ${m.period.start} → ${m.period.end}`:'—');detail.append(grid);
  if(m.reason)detail.append(node('p','',`Unavailable: ${m.reason}`));
  detail.append(node('h3','','Direct dependencies'));const deps=node('div');for(const dep of m.dependencies){const b=node('button','dep',dep);b.onclick=()=>inspect(dep);deps.append(b);}if(!m.dependencies.length)deps.append(node('span','', 'Leaf input'));detail.append(deps);
  detail.append(node('h3','','Transitive formula versions'));const fl=node('ul');for(const f of m.lineage.formulas)fl.append(node('li','',`${f.id}@${f.version}`));if(!m.lineage.formulas.length)fl.append(node('li','','None'));detail.append(fl);
  detail.append(node('h3','','Input records / evidence'));const ul=node('ul');for(const leaf of m.lineage.leaves){const line=node('li');line.append(node('strong','',`${leaf.metric_id} · ${fmt(leaf.value,leaf.unit)} · ${leaf.classification}${leaf.fixture?' · DEMO':''}`));line.append(node('div','',`Record ${leaf.record_id}; as-of ${leaf.as_of_date??'—'}; source IDs: ${leaf.source_ids.join(', ')||'none'}`));if(leaf.rationale)line.append(node('div','',`Rationale: ${leaf.rationale}`));if(leaf.scenario_name)line.append(node('div','',`Scenario: ${leaf.scenario_name}`));if(leaf.period)line.append(node('div','',`Period: ${leaf.period.basis} ${leaf.period.start} → ${leaf.period.end}`));ul.append(line);}if(!m.lineage.leaves.length)ul.append(node('li','','No resolved evidence'));detail.append(ul);
  detail.append(node('h3','','Source records'));const sl=node('ul');for(const source of m.sources){const li=node('li','',`${source.id} · ${source.publisher} · ${source.title} · published ${source.date} · retrieved ${source.retrieved_at} · tier ${source.tier} · `);if(source.url.startsWith('https://')||source.url.startsWith('http://')){const a=node('a','',source.url);a.href=source.url;a.target='_blank';a.rel='noopener noreferrer';li.append(a);}else li.append(node('span','',source.url));sl.append(li);}if(!m.sources.length)sl.append(node('li','','No external source: this input is an assumption or scenario.'));detail.append(sl);
  $('inspector').scrollIntoView({behavior:'smooth',block:'start'});
}
function drawKnobs(d){const target=$('sensitivity-inputs');target.replaceChildren();for(const [id,label] of knobs){const m=d.metrics[id];const wrap=node('div','field');const lab=node('label','',label);lab.htmlFor='knob-'+id;const input=node('input');input.type='number';input.step='any';input.id='knob-'+id;input.name=id;input.value=m.value??'';wrap.append(lab,input,node('small','',m.unit));target.append(wrap);}}
function render(d){displayed=d;$('mode').textContent=d.mode==='DEMO'?'DEMO / SYNTHETIC':'RESEARCH / SOURCED ONLY';$('banner').textContent=d.disclaimer;$('asof').textContent=`As-of ${d.as_of_date}`;$('snapshot-count').textContent=`${d.snapshots.length} immutable snapshot(s)`;drawMetrics(d);drawMatrix(d);drawGraph(d);drawThesis(d);drawComparison(d);const warnings=d.issues.filter(x=>x.level==='WARNING');$('sensitivity-status').textContent=warnings.length?`${warnings.length} validation warning(s): ${warnings.map(x=>x.code).join(', ')}`:'';}
async function fetchState(){const response=await fetch('/api/state');const data=await response.json();if(!response.ok)throw Error(data.error||'State unavailable');base=data;render(data);drawKnobs(data);}
$('sensitivity-form').addEventListener('submit',async event=>{event.preventDefault();const overrides={};for(const [id] of knobs){const raw=$('knob-'+id).value;if(raw.trim()===''||!Number.isFinite(Number(raw))){$('sensitivity-status').textContent=`Invalid input: ${id}`;return;}if(Number(raw)!==base.metrics[id].value)overrides[id]=Number(raw);}if(!Object.keys(overrides).length){render(base);return;}$('sensitivity-status').textContent='Calculating…';try{const response=await fetch('/api/sensitivity',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({overrides})});const d=await response.json();if(!response.ok)throw Error(d.error||d.issues?.filter(x=>x.level==='ERROR').map(x=>x.message).join('; ')||'Invalid override');render(d);$('sensitivity-status').textContent='Unsaved scenario recalculated; snapshots unchanged.';}catch(error){$('sensitivity-status').textContent=error.message;}});
$('reset').addEventListener('click',()=>{render(base);drawKnobs(base);});
$('scope-form').addEventListener('submit',async event=>{event.preventDefault();const params=new URLSearchParams(new FormData(event.currentTarget));$('scope-status').textContent='Selecting evidence…';try{const response=await fetch('/api/economics?'+params);const data=await response.json();if(!response.ok)throw Error(data.error??'Scope query failed');const target=$('scope-results');target.replaceChildren();for(const [id,m] of Object.entries(data.metrics)){const card=node('article','metric');card.append(node('div','label',id.replaceAll('_',' ')),node('div','value',fmt(m.value,m.unit)),node('div','tag derived',`${m.scope} · DERIVED · ${m.formula_id}@${m.formula_version}${m.fixture?' · DEMO':''}`),node('small','',`Inputs: ${m.dependencies.join(', ')}; records: ${m.record_ids.join(', ')||'none'}; sources: ${m.source_ids.join(', ')||'none'}${m.reason?'; '+m.reason+': '+m.missing_inputs.join(', '):''}`));target.append(card);}$('scope-status').textContent=`${data.knowledge_policy} · quarter ${data.realized_quarter_end} · horizon ${data.horizon_end}${data.warnings.length?' · '+data.warnings.join(', '):''}`;}catch(error){$('scope-status').textContent=error.message;}});
fetchState().catch(error=>{$('banner').textContent=error.message;$('mode').textContent='ERROR';});
