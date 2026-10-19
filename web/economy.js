'use strict';
const Econ={filters:{population:'regular',stage:'all',days:7,early:39,mid:74},tab:'overview',data:null,request:0,itemSearch:'',itemCategory:'all',itemSort:'stock',itemGrade:'all',limit:50,activity:'all',sourceSearch:'',noteTitle:'',noteBody:''};
const ecoNumber=n=>n===null||n===undefined?'—':Number(n).toLocaleString('en-GB',{maximumFractionDigits:1});
const ecoCompact=n=>n===null||n===undefined?'—':Number(n).toLocaleString('en-GB',{notation:'compact',maximumFractionDigits:2});
const ecoDate=t=>new Date(t*1000).toLocaleString('en-GB',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
const ecoPercent=n=>n===null||n===undefined?'Not enough data':`${n>0?'+':''}${ecoNumber(n)}%`;
const ecoLabels={all:'Whole server',early:'Early game',mid:'Midgame',late:'Late / endgame'};

async function loadEconomy(fresh=false,capture=false){
  const request=++Econ.request;
  if(!$('#economy-view'))renderEconomyShell();
  $('#eco-status').textContent=capture?'Collecting and saving a snapshot…':'Reading the live database…';
  $$('#eco-refresh,#eco-capture,#eco-export').forEach(button=>button.disabled=true);
  try{
    const data=capture?await api('/api/economy/capture',Econ.filters):await api('/api/economy?'+new URLSearchParams({...Econ.filters,...(fresh?{fresh:1}:{})}));
    if(request!==Econ.request||S.page!=='economy')return;
    Econ.data=data;
    $('#eco-status').textContent=data.connected?`Observed ${ecoDate(data.at)} · read-only database access`:data.lastSaved?`Game database offline · last saved observation: ${ecoDate(data.lastSaved.at)}`:'Game database offline · no saved observation matches these filters';
    $('#eco-connection').textContent=data.connected?'LIVE DATABASE':data.lastSaved?'SAVED SNAPSHOT · OFFLINE':'OFFLINE';
    $('#eco-connection').classList.toggle('good',data.connected);
    renderEconomyView();
    if(capture)toast('Economy snapshot saved in Studio. Game data was not changed.');
  }catch(error){
    if(request===Econ.request&&S.page==='economy'){
      $('#eco-status').textContent='Economy lookup failed';
      $('#economy-view').innerHTML=`<div class="notice">${esc(error.message)}</div>`;
    }
  }finally{if(request===Econ.request&&S.page==='economy'){$('#eco-refresh').disabled=false;$('#eco-capture').disabled=!Econ.data?.connected}}
}
function renderEconomyShell(){
  const f=Econ.filters;
  $('#content').innerHTML=head('WORLD BALANCE','Economy','Follow currency, goods and progression across your whole world.','<span id="eco-connection" class="status neutral">CONNECTING</span>')+
    `<section class="eco-controls" aria-label="Economy filters"><div class="field"><label for="eco-population">Population</label><select id="eco-population">${[['regular','Regular economy · no GMs'],['human','Humans · no GMs'],['bot','Playerbots · no GMs'],['gm','GM accounts only'],['all','Everyone · including GMs'],['unknown','Unknown ownership']].map(([key,label])=>`<option value="${key}" ${key===f.population?'selected':''}>${label}</option>`).join('')}</select></div>
    <div class="field"><label for="eco-stage">Progression stage</label><select id="eco-stage">${Object.entries(ecoLabels).map(([key,label])=>`<option value="${key}" ${key===f.stage?'selected':''}>${label}${key==='early'?` · 1–${f.early}`:key==='mid'?` · ${f.early+1}–${f.mid}`:key==='late'?` · ${f.mid+1}+`:''}</option>`).join('')}</select></div>
    <div class="field"><label for="eco-days">Log period</label><select id="eco-days">${[1,7,28].map(days=>`<option value="${days}" ${days===f.days?'selected':''}>Last ${days} ${days===1?'day':'days'}</option>`).join('')}</select></div>
    <div class="eco-control-actions"><button id="eco-refresh" class="button">↻ Refresh</button><button id="eco-export" class="button" disabled>↓ Export report</button><button id="eco-capture" class="button primary">Save snapshot</button></div></section>
    <div class="eco-subbar"><span id="eco-status" role="status">Reading economy…</span><details class="eco-boundaries"><summary>Stage boundaries</summary><form id="eco-boundary-form"><label>Early game ends at<input id="eco-early" type="number" min="1" max="118" value="${f.early}"></label><label>Midgame ends at<input id="eco-mid" type="number" min="2" max="120" value="${f.mid}"></label><button class="button small">Update view</button><small>View filters only. Character levels and game settings are unchanged.</small></form></details></div>
    <div class="tabs eco-tabs" role="tablist" aria-label="Economy sections">${[['overview','Overview'],['items','Items & demand'],['activity','Activities & drops'],['journal','Event journal'],['coverage','Data coverage']].map(([key,label])=>`<button role="tab" id="eco-tab-${key}" data-eco-tab="${key}" aria-controls="economy-view">${label}</button>`).join('')}</div><div id="economy-view" role="tabpanel"></div>`;
  for(const [id,key] of [['eco-population','population'],['eco-stage','stage'],['eco-days','days']])$('#'+id).addEventListener('change',e=>{Econ.filters[key]=key==='days'?Number(e.target.value):e.target.value;loadEconomy()});
  $('#eco-refresh').addEventListener('click',()=>loadEconomy(true));
  $('#eco-capture').addEventListener('click',()=>loadEconomy(true,true));
  $('#eco-export').addEventListener('click',openEconomyExport);
  $$('[data-eco-tab]').forEach(button=>button.addEventListener('click',()=>{Econ.tab=button.dataset.ecoTab;if(Econ.data)renderEconomyView()}));
  $('.eco-tabs').addEventListener('keydown',e=>{const buttons=$$('[data-eco-tab]'),index=buttons.indexOf(document.activeElement);if(index<0)return;let next;if(e.key==='ArrowRight')next=(index+1)%buttons.length;if(e.key==='ArrowLeft')next=(index+buttons.length-1)%buttons.length;if(e.key==='Home')next=0;if(e.key==='End')next=buttons.length-1;if(next!==undefined){e.preventDefault();buttons[next].click();buttons[next].focus()}});
  $('#eco-boundary-form').addEventListener('submit',e=>{e.preventDefault();const early=Number($('#eco-early').value),mid=Number($('#eco-mid').value);if(!Number.isInteger(early)||!Number.isInteger(mid)||early<1||early>118||mid<=early||mid>120)return toast('Choose stage boundaries from 1 to 120, with midgame ending after early game.',true);Econ.filters.early=early;Econ.filters.mid=mid;renderEconomyShell();loadEconomy()});
}
function openEconomyExport(){
  const dialog=$('#economy-export'),filters={...Econ.data.filters};
  const population={regular:'Regular economy · no GMs',human:'Humans · no GMs',bot:'Playerbots · no GMs',gm:'GM accounts only',all:'Everyone · including GMs',unknown:'Unknown ownership'};
  $('#eco-export-scope').textContent=`${population[filters.population]} · ${ecoLabels[filters.stage]} · last ${filters.days} ${filters.days===1?'day':'days'}`;
  $('#eco-export-detail').textContent=`${Econ.data.connected?`All ${ecoNumber(Econ.data.items.length)} live item rows in this view`:`Live measurements are unavailable; the last matching saved observation has ${ecoNumber(Econ.data.lastSaved?.items.length||0)} item IDs`}. Includes all matching saved snapshots and journal notes. Search does not limit the export.`;
  $('#eco-export-status').textContent='Uses the latest available observation. Exporting does not save a snapshot.';
  $$('[data-eco-download]').forEach(button=>{button.disabled=false;button.onclick=()=>downloadEconomyExport(button.dataset.ecoDownload,filters)});
  dialog.showModal();
}
async function downloadEconomyExport(format,filters){
  const buttons=$$('[data-eco-download]'),status=$('#eco-export-status');
  buttons.forEach(button=>button.disabled=true);status.textContent='Preparing your report…';
  try{
    const response=await fetch('/api/economy/export?'+new URLSearchParams({...filters,format}));
    if(!response.ok){const error=await response.json();throw new Error(error.error||'The export could not be created.');}
    const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
    link.href=url;link.download=response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]||`metin2-economy.${format}`;
    document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
    status.textContent=`${format==='zip'?'CSV pack':'JSON report'} ready. Check your browser downloads.`;
  }catch(error){status.textContent='Export failed: '+error.message;}
  finally{buttons.forEach(button=>button.disabled=false);}
}
function renderEconomyView(){
  hideItemHelp();
  $$('[data-eco-tab]').forEach(button=>{const selected=button.dataset.ecoTab===Econ.tab;button.classList.toggle('selected',selected);button.setAttribute('aria-selected',selected);button.tabIndex=selected?0:-1});
  $('#economy-view').setAttribute('aria-labelledby','eco-tab-'+Econ.tab);
  const d=Econ.data;
  $('#eco-export').disabled=false;
  $('#economy-view').innerHTML=(!d.connected?`<div class="notice eco-offline"><strong>Live data is unavailable</strong><p>${esc(d.error)}</p><p>${d.lastSaved?'Saved figures below are from '+esc(ecoDate(d.lastSaved.at))+', for exactly these population, stage and period filters. They are not current balances.':'Your saved observations are retained. Try the population, stage and period filters used when they were collected.'}</p></div>`:'')+(d.alerts.length?`<div class="notice eco-data-notes">${d.alerts.map(alert=>`<p>${esc(alert)}</p>`).join('')}</div>`:'')+(!d.connected&&Econ.tab==='overview'?economySavedOverview():!d.connected&&Econ.tab==='items'?economySavedItems():({overview:economyOverview,items:economyItems,activity:economyActivity,journal:economyJournal,coverage:economyCoverage}[Econ.tab])());
  if(Econ.tab==='items'){if(d.connected)bindEconomyItems();else bindSavedEconomyItems()}
  if(Econ.tab==='activity')bindEconomyActivity();
  if(Econ.tab==='journal')bindEconomyJournal();
  bindImages($('#economy-view'));
}
function economySavedOverview(){
  const d=Econ.data,s=d.lastSaved;
  if(!s)return ecoPanel('No saved data for this view','Waiting for the first successful observation','<p class="eco-caption">Start Docker Desktop and your world using the game launcher, then Refresh. You can save a snapshot once the database connects. Activities & drops still shows your configured sources; the journal and saved history remain available.</p>');
  const m=s.metrics;
  return `<div class="eco-cards">${ecoCard('Saved wallet Yang',ecoCompact(m.wallet),'Snapshot · '+ecoDate(s.at))}${ecoCard('Saved held item units',ecoNumber(m.stock),'Includes equipped and listed stock')}${ecoCard('Saved active accounts',ecoNumber(m.activeAccounts),'Activity in the saved log window')}${ecoCard('Saved shop turnover',ecoCompact(m.turnover),'Yang in the saved log window')}</div>`+ecoPanel('Last saved observation',ecoDate(s.at),`<p class="eco-caption">${s.items.length} item IDs were recorded. Open Items & demand to search their saved stock, listings and prices. Missing measurements remain unavailable. Start the game and Refresh to return to live data.</p><button class="button" id="eco-saved-items">Browse saved items</button>`)+ecoPanel('Saved wallet history','Same population, stage, boundaries and period',ecoLine(d.history.filter(p=>p.wallet!==null)));
}
function economySavedItems(){
  const s=Econ.data.lastSaved;
  if(!s)return '<div class="empty">No saved item observation matches these filters. Connect the world database to read current inventory stock.</div>';
  return ecoPanel('Saved item stock','Snapshot · '+ecoDate(s.at),`<div class="editor-filters"><label>Search saved items<input type="search" id="eco-saved-search" value="${esc(Econ.savedSearch||'')}" placeholder="Item name or ID…"></label></div><div id="eco-saved-table"></div><p class="eco-caption">Prices and trades refer to the log period at capture time. Recorded stock changes are not inferred as production or consumption. Current holdings may differ.</p>`);
}
function bindSavedEconomyItems(){
  const input=$('#eco-saved-search');if(!input)return;
  const render=()=>{const q=(Econ.savedSearch||'').toLowerCase(),rows=Econ.data.lastSaved.items.filter(r=>`${r.name} ${r.id}`.toLowerCase().includes(q)).sort((a,b)=>(b.stock||0)-(a.stock||0));$('#eco-saved-table').innerHTML=`<div class="table-wrap"><table><thead><tr><th>Item</th><th>Held units</th><th>Listed</th><th>Shop trades</th><th>Median unit price</th><th>Account owners</th></tr></thead><tbody>${rows.slice(0,150).map(r=>`<tr><th>${itemReference(r.id,{fallback:r.name})}</th><td>${ecoNumber(r.stock)}</td><td>${ecoNumber(r.listed)}</td><td>${ecoNumber(Econ.data.lastSaved.available.includes('sales')?r.sales:null)}</td><td>${ecoNumber(r.unitPrice)}</td><td>${ecoNumber(r.owners)}</td></tr>`).join('')||'<tr><td colspan="6">No saved items match.</td></tr>'}</tbody></table></div><p class="eco-caption">Showing ${Math.min(150,rows.length)} of ${rows.length} matching item IDs. Narrow the search to see others.</p>`};
  input.oninput=()=>{Econ.savedSearch=input.value;render();bindImages($('#eco-saved-table'))};render();bindImages($('#eco-saved-table'));
}
function ecoCard(label,value,hint,kind=''){return `<article class="eco-card ${kind}"><span>${label}</span><strong>${value}</strong><small>${hint}</small></article>`}
function ecoPanel(title,hint,body){return `<section class="panel eco-panel"><div class="panel-header"><h2>${title}</h2><span>${hint}</span></div>${body}</section>`}
function ecoLine(points){
  if(points.length<2)return '<div class="eco-empty">Save snapshots over time to reveal the trend. Snapshots are collected when you press Save snapshot.</div>';
  const max=Math.max(...points.map(point=>point.wallet)),min=Math.min(...points.map(point=>point.wallet)),span=max-min||1,width=720,height=115;
  const first=points[0].at,timeSpan=points.at(-1).at-first||1;
  const path=points.map((point,index)=>`${index?'L':'M'}${10+(point.at-first)/timeSpan*(width-20)},${height-8-(point.wallet-min)/span*(height-20)}`).join(' ');
  return `<svg class="eco-line" viewBox="0 0 ${width} ${height}" role="img" aria-label="Wallet Yang across saved snapshots. Minimum ${ecoNumber(min)}; maximum ${ecoNumber(max)}"><path d="${path}"/></svg><div class="eco-chart-axis"><span>${ecoDate(first)}</span><span>${ecoDate(points.at(-1).at)}</span></div>`;
}
function economyOverview(){
  const d=Econ.data,m=d.metrics,f=d.filters;
  const gmScope=f.population==='gm'?'GM accounts only':f.population==='all'?'Includes GM accounts':f.population==='unknown'?'Unattributed ownership':'GM accounts excluded';
  const gmInfo=d.gm.identified?`${ecoNumber(d.gm.accounts)} GM ${d.gm.accounts===1?'account':'accounts'} identified · ${ecoCompact(d.gm.wallet)} wallet Yang${['regular','human','bot'].includes(f.population)?' kept outside this view':''} · ${ecoNumber(d.gm.involvedTrades)} GM-involved shop trades in the period`:'GM registry unavailable; separation cannot be verified.';
  const bands=d.bands.map(row=>`<tr class="${f.stage===row.key?'eco-selected':''}"><th scope="row">${ecoLabels[row.key]}<small>${row.key==='early'?`1–${f.early}`:row.key==='mid'?`${f.early+1}–${f.mid}`:`${f.mid+1}+`}</small></th><td>${ecoNumber(d.available.includes('active')?row.active:null)} / ${ecoNumber(d.available.includes('players')?row.accounts:null)}</td><td>${ecoCompact(d.available.includes('players')?row.wallet:null)}</td><td>${ecoCompact(d.available.includes('sales')?row.turnover:null)}</td><td>${ecoNumber(d.available.includes('refines')?row.attempts:null)}</td></tr>`).join('');
  const flows=d.money.map(row=>`<tr><th scope="row">${esc(row.type)}</th><td class="eco-positive">${ecoNumber(row.created)}</td><td>${ecoNumber(row.removed)}</td></tr>`).join('');
  const signals=[];
  if(d.prices.percent!==null)signals.push(['Comparable goods',`${ecoPercent(d.prices.percent)} against the preceding ${f.days} days, across ${d.prices.matched} matched item IDs. Review individual goods before changing supply.`]);
  else signals.push(['Build a price baseline',`${d.prices.matched} commodity IDs have enough trades in both periods. Three are needed for a combined price movement figure.`]);
  if(m.attempts)signals.push(['Equipment progression',`${ecoNumber(m.attempts)} upgrade attempts; ${ecoNumber(m.burns)} equipment-destruction log records. ${ecoNumber(m.scrollAttempts)} attempts used a named scroll method; this alone does not prove protection.`]);
  const top=Object.entries(d.activity).sort((a,b)=>b[1]-a[1]),kills=top.reduce((n,row)=>n+row[1],0);
  if(kills)signals.push(['Farming concentration',`${S.mobMap[top[0][0]]?.name||'#'+top[0][0]} accounts for ${ecoNumber(top[0][1]/kills*100)}% of ${ecoNumber(kills)} recorded Metin/boss kills. Kill share is not item-production share.`]);
  const accumulating=d.items.filter(row=>row.stockChange>0&&row.sales===0).sort((a,b)=>b.stockChange-a.stockChange);
  if(accumulating.length)signals.push(['Stock review',`${accumulating.length} item IDs increased in held stock without a recorded shop sale during the log period. Check their uses and transfers before calling this overproduction.`]);
  const quality=[['+0 to +3',0,3],['+4 to +6',4,6],['+7 and above',7,Infinity]].map(([label,low,high])=>{const rows=d.items.filter(row=>row.grade!==null&&row.grade!==undefined&&row.grade>=low&&row.grade<=high);return `<tr><th scope="row">${label}</th><td>${ecoNumber(d.available.includes('stock')?rows.reduce((n,row)=>n+row.stock,0):null)}</td><td>${ecoNumber(d.available.includes('stock')?rows.reduce((n,row)=>n+row.equipped,0):null)}</td><td>${ecoNumber(d.available.includes('stock')?rows.reduce((n,row)=>n+row.listed,0):null)}</td></tr>`}).join('');
  return `<div class="eco-gm-scope"><strong>${gmScope}</strong><span>${gmInfo}</span></div><div class="eco-cards">${ecoCard('Character-wallet Yang',ecoCompact(m.wallet),d.baseline?`${ecoPercent(d.baseline.walletChange)} since ${ecoDate(d.baseline.at)}`:'Current balance · banks and Won separate')}${ecoCard('Recorded shop turnover',ecoCompact(m.turnover),`${ecoNumber(m.trades)} Yang-only sales · ${ecoNumber(m.buyers)} distinct buyer characters`)}${ecoCard('Active accounts',ecoNumber(m.activeAccounts),`${ecoNumber(m.accounts)} accounts in this view · active within ${f.days} days`)}${ecoCard('Held item units',ecoCompact(m.stock),'Current stock · includes listed and equipped items')}${ecoCard('Upgrade success',m.successRate===null?'—':ecoNumber(m.successRate)+'%',`${ecoNumber(m.attempts)} attempts · downgrade detail rows excluded`)}${ecoCard('Comparable goods prices',d.prices.percent===null?'—':ecoPercent(d.prices.percent),`${d.prices.matched} matched IDs · preceding ${f.days}-day comparison`)}</div>
  <p class="eco-caption">GM status applies to the whole account, including alts and storage. Regular economy includes humans and bots with known ownership; GM-involved trades are excluded from normal sales and prices. Stage uses current levels; in the GM view, trade stage follows the GM party. Bank balances follow population across all levels. Currency-flow logs remain mixed and global.</p>
  ${ecoPanel('Progression balance','Same measures, every stage',`<div class="eco-table-wrap"><table class="eco-table"><thead><tr><th>Stage / level</th><th>Active / accounts</th><th>Wallet Yang</th><th>Sales Yang</th><th>Upgrade attempts</th></tr></thead><tbody>${bands}</tbody></table></div>`)}
  <div class="eco-two">${ecoPanel('Mixed global Yang logs','Includes possible GM activity · partial coverage',`<p class="eco-caption">These logs have no actor ID. Their amounts cannot be split into regular and GM economies and do not follow the population filter.</p><div class="eco-flow-totals"><span>Recorded in<strong>${ecoCompact(m.recordedIn)}</strong></span><span>Recorded out<strong>${ecoCompact(m.recordedOut)}</strong></span><span>Balance<strong>${ecoCompact(m.recordedNet)}</strong></span></div><div class="eco-table-wrap"><table class="eco-table"><thead><tr><th>Source label</th><th>In</th><th>Out</th></tr></thead><tbody>${flows||'<tr><td colspan="3">No currency-flow records available.</td></tr>'}</tbody></table></div><p class="eco-caption">A positive logged balance alone does not prove inflation. Unlogged flows and transfers prevent a full reconciliation.</p>`)}
  ${ecoPanel('Signals to investigate','Evidence before changing rewards',`<div class="eco-signals">${signals.map(([title,text])=>`<article><strong>${esc(title)}</strong><p>${esc(text)}</p></article>`).join('')}</div>`)}</div>
  ${ecoPanel('Wallet history','GM-aware snapshots · current filters',ecoLine(d.history.filter(row=>row.wallet!==null))+`<p class="eco-caption">${d.history.length} ${d.history.length===1?'snapshot':'snapshots'} for this population, stage, period and boundary selection. ${d.baseline?'Stock changes compare against '+ecoDate(d.baseline.at)+'.':d.history.length?'Baseline saved; comparisons become available after one minute and a refresh.':'Save a new baseline for this GM separation; comparisons appear after a later snapshot or refresh.'}</p>${d.legacyHistory.length?`<details class="eco-legacy"><summary>Earlier snapshots · previous mixed definitions (${d.legacyHistory.length})</summary><p>Preserved for reference and excluded from this chart and stock comparisons.</p><table class="eco-table"><thead><tr><th>Captured</th><th>Previous wallet Yang</th></tr></thead><tbody>${d.legacyHistory.map(row=>`<tr><td>${ecoDate(row.at)}</td><td>${ecoNumber(row.wallet)}</td></tr>`).join('')}</tbody></table></details>`:''}`)}
  ${ecoPanel('Equipment supply by upgrade grade','Selected population and stage',`<div class="eco-table-wrap"><table class="eco-table"><thead><tr><th>Catalog grade</th><th>Held units</th><th>Equipped units</th><th>Listed units</th></tr></thead><tbody>${quality}</tbody></table></div><p class="eco-caption">Grade follows the installed catalog name, not bonus quality. Listed units belong to shops with remaining duration; they are included in held stock. Browse Items & demand to inspect individual weapons and armour.</p>`)}
  <div class="eco-two">${ecoPanel('Wallet distribution','Selected population and stage',`<div class="eco-flow-totals"><span>Median per account<strong>${ecoCompact(m.medianWallet)}</strong></span><span>Top 10% hold<strong>${m.top10Share===null?'—':ecoNumber(m.top10Share)+'%'}</strong></span><span>Won held<strong>${ecoNumber(m.won)}</strong></span></div><p class="eco-caption">Balances aggregate characters by account. Wallet Yang is not total wealth, and dormant accounts are included.</p>`)}${ecoPanel('Bank balances','Selected population · all levels',`<div class="eco-bank-list">${d.banks.map(row=>`<div><span>${esc(row[0])}</span><strong>${ecoNumber(row[1])}</strong></div>${row[0]==='Shop safebox Yang'?`<div><span>Shop safebox Won</span><strong>${ecoNumber(row[2])}</strong></div>`:''}`).join('')||`<p>${d.available.includes('banks')||d.available.includes('shopbanks')?'No bank balances recorded for this population.':'Bank balances unavailable.'}</p>`}</div><p class="eco-caption">Account and shop storage follow their owner’s GM/account classification. Bank balances do not follow the progression-stage filter.</p>`)}</div>`;
}
function economyItems(){
  const categories=[...new Set(Econ.data.items.map(row=>row.category))].sort();
  return ecoPanel('Item stock & demand','Observed stock, completed sales and log records',`<div class="eco-item-tools"><input id="eco-item-search" aria-label="Search economy items" placeholder="Search item names or IDs…" value="${esc(Econ.itemSearch)}"><select id="eco-item-category" aria-label="Economy item category"><option value="all">All item categories</option>${categories.map(key=>`<option value="${esc(key)}" ${key===Econ.itemCategory?'selected':''}>${esc(StudioCatalog.groups?.[key]?.label||key)}</option>`).join('')}</select><select id="eco-item-sort" aria-label="Sort economy items">${[['stock','Held stock'],['stockChange','Stock increase'],['turnover','Sales value'],['sales','Number of sales'],['uses','Use records'],['burns','Destruction records']].map(([key,label])=>`<option value="${key}" ${key===Econ.itemSort?'selected':''}>${label}</option>`).join('')}</select><select id="eco-item-grade" aria-label="Equipment upgrade grade">${[['all','Any upgrade grade'],['high','Equipment +7 and above'],['low','Equipment +0 to +6']].map(([key,label])=>`<option value="${key}" ${key===Econ.itemGrade?'selected':''}>${label}</option>`).join('')}</select></div><p class="eco-caption">Stock is measured in units. Acquisition, use, NPC-sale and destruction figures are log-record counts; they are not net creation or exact consumption quantities. Historical equipment prices may mix different bonuses. Upgrade grade follows the catalog name; bonuses are not graded.</p><div id="eco-item-table"></div>`);
}
function renderEconomyItemRows(){
  const query=Econ.itemSearch.toLowerCase().trim();
  const rows=Econ.data.items.filter(row=>(Econ.itemCategory==='all'||row.category===Econ.itemCategory)&&(Econ.itemGrade==='all'||row.grade!==null&&row.grade!==undefined&&(Econ.itemGrade==='high'?row.grade>=7:row.grade<=6))&&`${row.name} ${row.id}`.toLowerCase().includes(query)).sort((a,b)=>(b[Econ.itemSort]??-Infinity)-(a[Econ.itemSort]??-Infinity)||Number(a.id)-Number(b.id));
  $('#eco-item-table').innerHTML=`<div class="eco-table-wrap"><table class="eco-table eco-items"><thead><tr><th>Item / where used</th><th>Held units</th><th>Stock Δ</th><th>Listed units</th><th>Units sold</th><th>Unit price*</th><th>Acquire / use records</th><th>NPC-sale / burn records</th></tr></thead><tbody>${rows.slice(0,Econ.limit).map(row=>`<tr><th scope="row">${itemReference(row.id,{fallback:row.name})}</th><td>${ecoNumber(row.stock)}<small>${ecoNumber(row.equipped)} equipped</small></td><td>${row.stockChange===null?'—':`${row.stockChange>0?'+':''}${ecoNumber(row.stockChange)}`}</td><td>${ecoNumber(Econ.data.available.includes('stock')?row.listed:null)}</td><td>${ecoNumber(Econ.data.available.includes('sales')?row.unitsSold:null)}<small>${ecoNumber(row.sales)} trades</small></td><td>${ecoNumber(row.unitPrice)}<small>${row.priceChange===null?'':ecoPercent(row.priceChange)}</small></td><td>${ecoNumber(Econ.data.available.includes('actions')?row.acquisitions:null)} / ${ecoNumber(Econ.data.available.includes('actions')?row.uses:null)}</td><td>${ecoNumber(Econ.data.available.includes('actions')?row.npcSales:null)} / ${ecoNumber(Econ.data.available.includes('actions')?row.burns:null)}</td></tr>`).join('')||'<tr><td colspan="8">No observed items match these filters.</td></tr>'}</tbody></table></div><div class="eco-table-foot"><span>${ecoNumber(Math.min(Econ.limit,rows.length))} of ${ecoNumber(rows.length)} items · *Median Yang per unit per transaction</span>${rows.length>Econ.limit?'<button id="eco-item-more" class="button small">Show 50 more</button>':''}</div>`;
  $('#eco-item-more')?.addEventListener('click',()=>{Econ.limit+=50;renderEconomyItemRows()});bindImages($('#eco-item-table'));
}
function bindEconomyItems(){
  $('#eco-item-search').addEventListener('input',e=>{Econ.itemSearch=e.target.value;Econ.limit=50;renderEconomyItemRows()});
  for(const [id,key] of [['eco-item-category','itemCategory'],['eco-item-sort','itemSort'],['eco-item-grade','itemGrade']])$('#'+id).addEventListener('change',e=>{Econ[key]=e.target.value;Econ.limit=50;renderEconomyItemRows()});
  renderEconomyItemRows();
}
function economyActivity(){
  return ecoPanel('Activities & configured rewards','Recorded kills alongside saved drop definitions',`<div class="eco-item-tools"><input id="eco-source-search" aria-label="Search economy drop targets" placeholder="Search targets by name or ID…" value="${esc(Econ.sourceSearch)}"><select id="eco-activity" aria-label="Economy activity type">${[['all','All target types'],['metin','Metins'],['boss','Bosses'],['monster','Monsters']].map(([key,label])=>`<option value="${key}" ${key===Econ.activity?'selected':''}>${label}</option>`).join('')}</select></div><p class="eco-caption">Stage filters target levels in this table. Recorded kills use the actor’s stage/population filter; a missing or zero count does not prove the target was never farmed. Shared pools and repeated groups are deduplicated when counting configured item IDs. Monster kills are not measured by the available kill logs.</p><div id="eco-source-table"></div>`)+ecoPanel('Upgrade methods','Selected actors · logged attempts',`<div class="eco-methods">${Object.entries(Econ.data.methods).map(([key,value])=>`<div><span>${esc(key)}</span><strong>${ecoNumber(value)}</strong></div>`).join('')||'<p>No upgrade attempts in the available records.</p>'}</div><p class="eco-caption">Named scroll methods describe how an attempt was made. Exact scroll consumption and protection effects are not inferred.</p>`);
}
function bindEconomyActivity(){
  const render=()=>{
    const query=Econ.sourceSearch.toLowerCase(),f=Econ.filters;
    const rows=Econ.data.sources.filter(row=>(Econ.activity==='all'||row.kind===Econ.activity)&&(f.stage==='all'||row.level>0&&(row.level<=f.early?'early':row.level<=f.mid?'mid':'late')===f.stage)&&`${row.name} ${row.id}`.toLowerCase().includes(query));
    $('#eco-source-table').innerHTML=`<div class="eco-table-wrap"><table class="eco-table"><thead><tr><th>Target</th><th>Level / type</th><th>Recorded kills</th><th>Configured item IDs</th><th>Shared pools</th><th>Source</th></tr></thead><tbody>${rows.slice(0,150).map(row=>`<tr><th scope="row">${esc(row.name)}<small>#${esc(row.id)}</small></th><td>${esc(row.level??'?')} · ${esc(row.kind)}</td><td>${['metin','boss'].includes(row.kind)&&Econ.data.available.includes('actions')?ecoNumber(Econ.data.activity[row.id]||0):'—'}</td><td>${ecoNumber(row.items)}</td><td>${ecoNumber(row.pools)}</td><td><button class="subtle-link" data-eco-drop="${esc(row.id)}">Open drop group ↗</button></td></tr>`).join('')||'<tr><td colspan="6">No targets match this view.</td></tr>'}</tbody></table></div><div class="eco-table-foot">Showing ${Math.min(150,rows.length)} of ${rows.length} targets${rows.length>150?' · narrow your search to see others':''}</div>`;
    $$('[data-eco-drop]').forEach(button=>button.addEventListener('click',()=>{const source=Econ.data.sources.find(row=>row.id===button.dataset.ecoDrop).groups[0];openUsageSource({kind:'drop',...source})}));
  };
  $('#eco-source-search').addEventListener('input',e=>{Econ.sourceSearch=e.target.value;render()});
  $('#eco-activity').addEventListener('change',e=>{Econ.activity=e.target.value;render()});render();
}
function economyJournal(){
  return `<div class="eco-two">${ecoPanel('Record a balancing decision','Local notes · no server changes',`<form id="eco-note-form" class="eco-note-form"><label for="eco-note-title">Event or change title</label><input id="eco-note-title" maxlength="120" required placeholder="e.g. Material exchange weekend" value="${esc(Econ.noteTitle)}"><label for="eco-note-body">Hypothesis and measures to watch</label><textarea id="eco-note-body" maxlength="1500" rows="5" placeholder="What changed, which items or activities are affected, and what result would count as success?">${esc(Econ.noteBody)}</textarea><button class="button primary">Save journal note</button><small>Take a snapshot before and after a change. Notes are shared across economy filters and stored only in Studio.</small></form>`)}${ecoPanel('Event & change journal','Newest first',`<div class="eco-journal">${Econ.data.notes.map(note=>`<article><small>${ecoDate(note.at)}</small><h3>${esc(note.title)}</h3><p>${esc(note.body)}</p></article>`).join('')||'<div class="eco-empty">No notes yet. Record your first hypothesis before adjusting a drop or launching an event.</div>'}</div>`)}</div>`;
}
function bindEconomyJournal(){
  $('#eco-note-title').addEventListener('input',e=>Econ.noteTitle=e.target.value);
  $('#eco-note-body').addEventListener('input',e=>Econ.noteBody=e.target.value);
  $('#eco-note-form').addEventListener('submit',async e=>{
    e.preventDefault();const button=$('button',e.target);button.disabled=true;
    try{await api('/api/economy/note',{title:Econ.noteTitle,body:Econ.noteBody});Econ.noteTitle='';Econ.noteBody='';await loadEconomy();toast('Journal note saved locally.')}catch(error){toast(error.message,true);button.disabled=false}
  });
}
function economyCoverage(){
  return ecoPanel('What these figures can tell us','Sources, definitions and missing measurements',`<div class="eco-coverage">${Econ.data.coverage.map(([title,status,text])=>`<article><div><h3>${esc(title)}</h3><span class="pill ${status==='Observed'?'gold':''}">${esc(status)}</span></div><p>${esc(text)}</p></article>`).join('')}</div><div class="eco-caption">${Econ.data.alerts.map(alert=>`<p>${esc(alert)}</p>`).join('')}<p>Bot classification follows the package: playerbot_ account logins or the legacy bot name prefix. No account login, character name, credential or raw player record is saved in snapshots. Collection uses a read-only database transaction; only Studio’s local history and journal are writable.</p></div>`);
}
