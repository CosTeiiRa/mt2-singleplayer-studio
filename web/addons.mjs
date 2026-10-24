import {jobActive,transferLabel,watchJob} from './addon_jobs.mjs';
import {escapeHtml as e, descriptionSummary, descriptionMarkup, unwrap, asArray, filterCatalog, installedRecord, addonStatus, compatibilityStatus, formatTime, humanize, changeRows, planMessages, sourceLabel, atlasSpecies, mapRegions, mapBounds, respawnLabel, settingFields, parseSettingValue, isGameExtension, componentRows} from './addon_helpers.mjs';

const paths = {
  overview:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  discover:'m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Zm0 9 8-4.5M12 12 4 7.5M12 12v9',
  installed:'M4 8h16v13H4zM3 3h18v5H3zM9 12h6',
  atlas:'m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2V5Zm6-2v16M15 5v16',
  activity:'M3 12h4l3-8 4 16 3-8h4',
  settings:'M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1 1-3Zm6 9a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  refresh:'M20 7v5h-5M4 17v-5h5M5 8a7.5 7.5 0 0 1 12-3l3 3M4 16l3 3a7.5 7.5 0 0 0 12-3',
  plus:'M12 5v14M5 12h14', arrow:'M5 12h14m-5-5 5 5-5 5',
  search:'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',
  shield:'m12 3 8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6l8-3Zm-4 9 3 3 5-6',
  folder:'M3 6h7l2 3h9v11H3V6Z', check:'m5 12 4 4 10-10',
  warning:'m12 3 10 18H2L12 3Zm0 6v5M12 17h.01',
  close:'m6 6 12 12M6 18 18 6', info:'M12 11v6M12 7h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
  layers:'m12 3 10 5-10 5L2 8l10-5Zm-10 9 10 5 10-5M2 16l10 5 10-5',
  pin:'M19 10c0 5-7 12-7 12S5 15 5 10a7 7 0 1 1 14 0Zm-4 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  clock:'M12 6v6l4 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
  terminal:'m5 7 5 5-5 5M13 17h6', package:'m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Zm0 9 8-4.5M12 12 4 7.5M12 12v9M8 5l8 4.5',
  remove:'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7'
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name] ?? paths.package}"></path></svg>`;
const targetLabel = profile => profile?.kind==='test-client'?'Playable test copy':profile?.kind==='sandbox'?'Pack sandbox':profile?.writable?'Game client':profile?'Read only':'Not connected';

function compatibilityBadge(item) {
  const info=compatibilityStatus(item);
  return `<span class="pill ${info.tone}" title="${e(info.description)}">${e(info.label)}</span>`;
}

function compatibilityDetails(item) {
  const info=compatibilityStatus(item),declared=item.compatibility??{},target=store.state.installation;
  const versions=value=>Array.isArray(value)&&value.length?value.join(', '):'Not declared';
  const rows=[['Current client version',target?.client_version??'Not connected'],
    ['Publisher lists client versions',versions(declared.client_versions)],
    ['Current game version',target?.server_version??'Not connected'],
    ['Publisher lists game versions',versions(declared.server_versions)]];
  return `<section class="source-box"><h3>${e(info.label)}</h3><p>${e(info.description)}</p>${info.notes.length?`<ul class="warning-list">${info.notes.map(note=>`<li>${e(note)}</li>`).join('')}</ul>`:''}<dl class="definition-list">${rows.map(([label,value])=>`<dt>${e(label)}</dt><dd>${e(value)}</dd>`).join('')}</dl></section>`;
}

function referenceMarkup(meta) {
  if(!meta)return '<p class="field-hint">Reference data is generated locally during the installation review.</p>';
  return `<section class="source-box"><h3>Pocket Wiki reference snapshot</h3>${meta.catalogue_current===false?'<p class="field-hint">The catalogue has changed. Review a reference-data refresh to update the in-game wiki.</p>':''}<p>Server ${e(meta.server_version)} · Generated ${e(meta.generated_at)}<br>${Object.entries(meta.counts??{}).map(([key,count])=>`${e(count)} ${e(humanize(key))}`).join(' · ')}</p><p>Snapshot <code>${e(String(meta.snapshot??'').slice(0,16))}</code></p><ul>${(meta.warnings??[]).map(note=>`<li>${e(note)}</li>`).join('')}</ul></section>`;
}
function extensionComponentsMarkup(item){
  const rows=componentRows(item.components);
  return `<section class="source-box addon-components"><h3>Server &amp; client components</h3>${rows.map(row=>`<div class="addon-component"><div><strong>${e(row.name)}</strong>${row.message?`<p>${e(row.message)}</p>`:''}</div><span class="pill ${row.tone}">${e(row.label)}</span></div>`).join('')}<p class="field-hint">Activation uses a server quest. Client-data fixes use your installed game assets. Mounted combat remains separate.</p></section>`;
}
let host = null;
const $ = selector => host?.root?.querySelector(selector) ?? document.querySelector(selector);
const names = {overview:'Overview',discover:'Discover',installed:'Installed',atlas:'Boss atlas',activity:'Activity',settings:'Settings'};
const store = {state:{installed:[]}, catalog:[], history:[], maps:[], mapsMeta:{}, map:null, diagnostics:null, csrf:'',repositories:[],releases:[],updates:[]};
const ui = {page:'overview',query:'',category:'all',mapId:'',busy:false,loaded:false,error:'',atlasFilter:'all',atlasSearch:'',atlasPinned:'',atlasFocus:'',atlasHoverRequest:0,detailsId:null,plan:null,jobWatch:0};
let integrityTimer,checkingIntegrity=false;
const batchSelection=new Set();

function batchItems(){
  return store.catalog.filter(item=>!isGameExtension(item)&&!itemError(item)&&item.valid!==false&&(!installedRecord(item,store.state.installed)||item.update_available));
}

function batchToolbar(){
  const items=batchItems(),selected=items.filter(item=>batchSelection.has(item.id));
  return `<section class="panel addon-batch"><div class="panel-header"><div><h2>Install client add-ons together</h2><p class="field-hint">Select packages below or review all ${items.length} ready ${items.length===1?'package':'packages'}. Bundled and downloaded client packages are included. Server &amp; client extensions have their own review.</p></div><div class="row-actions"><button class="button small" data-action="batch-selected" ${mutation(!selected.length)}>Review selected (${selected.length})</button><button class="button small primary" data-action="batch-all" ${mutation(!items.length)}>Review all (${items.length})</button></div></div><p class="panel-body">One review, one installation. Close the game client once, apply the group, then open it again.</p></section>`;
}

function batchPlanMarkup(plan){
  const items=plan.batch??(['repair','reapply'].includes(plan.action)?(plan.desired_state??plan.installed??[]).map(item=>({...item,action:'reinstall'})):null);
  if(!items?.length)return '';
  return `<section class="source-box"><h3>${items.length} add-ons in one installation</h3><ul>${items.map(item=>`<li><strong>${e(item.name)}</strong> · ${e(humanize(item.action))} · ${item.before_version?e(item.before_version)+' → ':''}${e(item.version)}${item.enabled===false?' · stays disabled':''}</li>`).join('')}</ul><p>Close the game client once before applying. Open it again after all changes complete.</p></section>`;
}

async function reviewBatch(ids){
  if(ui.busy||!ids.length)return;
  const context=host;setBusy(true);
  try{
    const result=await api('plan/batch',{addon_ids:ids});
    if(host!==context||!context.current())return;
    const plan=unwrap(result,'plan');store.state.pending_plan=plan;openPlan(plan);
  }finally{setBusy(false);}
}

async function checkIntegrity(context=host) {
  if(!context?.current()||host!==context||ui.busy||checkingIntegrity||document.hidden)return;
  checkingIntegrity=true;
  const previous=JSON.stringify([store.state.integrity,store.state.installed]);
  try{
    const result=unwrap(await api('state'),'state');
    if(host!==context||!context.current())return;
    store.state=result;
  }catch(error){
    if(host!==context||!context.current())return;
    store.state={...store.state,integrity:{status:'unavailable',message:'Client files could not be checked. Refresh to try again.',repair_available:false},
      installed:store.state.installed.map(item=>({...item,integrity:{status:'unavailable'}}))};
  }finally{checkingIntegrity=false;}
  context.onState?.(store.state);
  if(previous!==JSON.stringify([store.state.integrity,store.state.installed]))render();
}

function watchIntegrity(context) {
  if(typeof window==='undefined')return;
  window.clearTimeout(integrityTimer);
  const tick=async()=>{
    if(host!==context||!context.current())return;
    await checkIntegrity(context);
    if(host===context&&context.current())integrityTimer=window.setTimeout(tick,15000);
  };
  integrityTimer=window.setTimeout(tick,15000);
}

document.addEventListener('visibilitychange',()=>{if(!document.hidden)return checkIntegrity();});
globalThis.window?.addEventListener('focus',()=>checkIntegrity());



async function api(path, data) {
  const result = await host.api('/api/addons/' + path, data);
  if (result.ok === false) throw new Error(result.error || 'The add-on operation failed.');
  return result;
}

function setBusy(value) {
  ui.busy = value;
  document.querySelectorAll('.m2addons [data-mutation]').forEach(button => button.disabled = value || jobActive(store.state.network_job) || button.dataset.blocked === 'true');
  if ($('#ah-refresh')) $('#ah-refresh').disabled = value;
  if (value && !$('.busy-indicator')) {const bar=document.createElement('div');bar.className='busy-indicator';bar.setAttribute('role','progressbar');bar.setAttribute('aria-label','Working');document.body.append(bar);}
  if (!value) $('.busy-indicator')?.remove();
}
const mutation = blocked => `data-mutation data-blocked="${!!blocked}" ${blocked || ui.busy || jobActive(store.state.network_job) ? 'disabled' : ''}`;

function toast(message, error=false) { host.toast(message, error); }

async function refresh({quiet=false,reconnect=false}={}) {
  const context=host;
  const results = await Promise.allSettled([api('state'),api('catalog'),api('history'),api('repositories'),api('releases'),api('updates')]);
  if(host!==context||!context.current())return;
  if (results[0].status === 'rejected') throw results[0].reason;
  store.state = unwrap(results[0].value,'state');
  context.onState?.(store.state);
  store.csrf = results[0].value.csrf_token ?? store.state.csrf_token ?? store.csrf;
  if (results[1].status === 'fulfilled') {const data=unwrap(results[1].value,'catalog');store.catalog=asArray(data.items ?? data);}
  else if (!quiet) toast(`Catalog unavailable: ${results[1].reason.message}`,true);
  if (results[2].status === 'fulfilled') {const data=unwrap(results[2].value,'history');store.history=asArray(data.items ?? data.events ?? data.entries ?? data);}
  else if (!quiet) toast(`Activity unavailable: ${results[2].reason.message}`,true);
  if(results[3].status==='fulfilled')store.repositories=results[3].value.repositories??[];
  if(results[4].status==='fulfilled')store.releases=results[4].value.releases??[];
  if(results[5].status==='fulfilled'){store.updates=results[5].value.updates??[];ui.updatesError='';}
  else {store.updates=[];ui.updatesError=results[5].reason.message;}
  if(ui.page==='activity'){try{store.activity=(await host.api('/api/activity')).items;}catch(error){toast(error.message,true);}}
  ui.loaded=true;ui.error='';
  renderChrome();render();
  if(reconnect&&jobActive(store.state.network_job))monitorNetworkJob(context,store.state.network_job.id);
}

function renderChrome() {}

function heading(eyebrow,title,subtitle,actions='') {
  return `<div class="page-heading"><div><p class="eyebrow">${e(eyebrow)}</p><h1>${e(title)}</h1><p>${e(subtitle)}</p></div>${actions ? `<div class="page-actions">${actions}</div>` : ''}</div>`;
}

function empty(title,text,action='',compact=false,kind='package') {
  return `<div class="empty-state${compact?' compact':''}"><div class="metric-icon">${icon(kind)}</div><h2>${e(title)}</h2><p>${e(text)}</p>${action}</div>`;
}

function networkJobMarkup(){
  const job=store.state.network_job;if(!job)return '';
  const active=jobActive(job),failed=['failed','interrupted'].includes(job.status);
  const message=job.operation==='releases/review'&&job.status==='succeeded'&&!job.result_available?'This download review expired. Review the release again.':job.error||job.message;
  const labels={'repositories/add':'Add repository','repositories/refresh':'Check repository','repositories/check-updates':'Check for add-on updates','releases/review':'Prepare download review','releases/download':'Download package'};
  return `<div class="callout network-job ${failed?'danger':''}" role="status" aria-live="polite"><div><strong>${e(labels[job.operation]??'Repository operation')} · ${e(humanize(job.status))}</strong><p>${e(message)}</p>${active?`<small>${e(transferLabel(job))}</small>`:''}</div>${active?`<button class="button small" data-action="cancel-network-job" data-job="${e(job.id)}" ${job.cancel_requested?'disabled':''}>${job.cancel_requested?'Cancelling…':'Cancel'}</button>`:job.operation==='releases/review'&&job.status==='succeeded'&&job.result_available?`<button class="button small" data-action="network-job-result" data-job="${e(job.id)}">Open download review</button>`:''}</div>`;
}

function monitorNetworkJob(context,ident){
  const generation=++ui.jobWatch;
  const isCurrent=()=>host===context&&context.current()&&ui.jobWatch===generation;
  watchJob({isCurrent,getJob:async()=>{
    const result=await context.api('/api/addons/job?id='+encodeURIComponent(ident));
    if(result.ok===false)throw Error(result.error||'Cannot read repository job.');
    return result.job;
  },onUpdate:job=>{
    store.state.network_job=job;
    const panel=$('#ah-network-job');if(panel)panel.innerHTML=networkJobMarkup();
  },onFinish:async job=>{
    await refresh({quiet:true});if(!isCurrent())return;
    if(job.status==='succeeded'){
      if(job.result?.review)openDownloadReview(job.result.review);
      else if(job.result?.downloaded){$('#ah-download-dialog').close();openDetails(job.result.downloaded);toast('Package verified. Review installation separately.');}
      else if(job.result?.checked_repositories)toast(`Checked ${job.result.checked_repositories.length} repositories${job.result.check_errors?'; '+job.result.check_errors+' need attention':''}. No add-ons were downloaded or updated.`);
      else toast('Repository checked.');
    }else if(job.status==='failed'||job.status==='interrupted')toast(job.error||'Repository operation failed.',true);
  }}).catch(error=>{if(isCurrent())toast('Job status unavailable: '+error.message+'. Refresh to reconnect.',true);});
}

async function startNetworkJob(operation,data){
  if(ui.busy||jobActive(store.state.network_job))return;
  const context=host;setBusy(true);
  try{
    const result=await api('jobs/start',{operation,data});
    if(host!==context||!context.current())return;
    store.state.network_job=result.job;
    if(operation==='releases/download')$('#ah-download-dialog').close();
    if(operation==='releases/review')$('#ah-update-dialog').close();
    render();monitorNetworkJob(context,result.job.id);
  }finally{setBusy(false);}
}

function banners() {
  let output='';const recovery=store.state.recovery;
  if (recovery && recovery.status!=='complete' && recovery.status!=='recovered' && recovery.required!==false) output+=`<div class="callout danger">${icon('warning')}<p><strong>An interrupted change needs attention.</strong><br>${e(typeof recovery==='string'?recovery:recovery.message ?? 'Review recovery before making another change.')}</p><button class="button danger small" data-action="recover" ${mutation(false)}>Recover installation</button></div>`;
  if (store.state.installation && !store.state.installation.writable) output+=`<div class="callout">${icon('shield')}<p><strong>Client changes are currently unavailable.</strong> ${e(store.state.installation.details?.read_only_reason??'Check client support and reconnect in Add-on settings.')}</p></div>`;
  const integrity=store.state.integrity;
  if(integrity&&!['healthy','empty'].includes(integrity.status))output+=`<div class="callout danger" role="status"><div>${icon('warning')}<strong>${integrity.status==='missing'?'Add-ons need reinstalling.':integrity.status==='unavailable'?'Cannot verify installed add-ons.':'Check installed add-on files.'}</strong><p>${e(integrity.message)}</p>${integrity.missing_files?.length||integrity.changed_files?.length?`<details><summary>Affected client files</summary><ul>${[...(integrity.missing_files??[]).map(path=>'Missing: '+path),...(integrity.changed_files??[]).map(path=>'Changed: '+path)].map(note=>`<li><code>${e(note)}</code></li>`).join('')}</ul></details>`:''}</div>${reinstallButton()}</div>`;
  else if(store.state.game_update)output+=`<div class="callout">${icon('info')}<p><strong>The game client changed.</strong> ${e(store.state.game_update.message)}</p>${reinstallButton()}</div>`;
  const warnings=planMessages([...(store.state.warnings??[]),...(store.state.startup_warning?[store.state.startup_warning]:[])]);
  if(warnings.length)output+=`<div class="callout">${icon('info')}<ul class="warning-list">${warnings.map(message=>`<li>${e(message)}</li>`).join('')}</ul></div>`;
  if(store.state.dependencies?.lzokay===false) output+='<div class="callout"><p><strong>Client pack support needs installation.</strong> Run Install Add-on Support.bat once, then restart Studio. Server editors and the atlas remain available.</p></div>';
  return output;
}

function reinstallButton(id='') {
  const missing=store.state.installed.filter(row=>row.integrity?.status==='missing');
  const record=id?store.state.installed.find(row=>row.id===id):missing.every(isGameExtension)?missing.find(isGameExtension):null;
  if(isGameExtension(record)&&record.integrity?.status==='missing')return `<button class="button small primary" data-action="plan" data-operation="reapply" data-id="${e(record.id)}" ${mutation(false)}>Review reapply</button>`;
  const integrity=store.state.integrity;
  const action=integrity?.repair_available?integrity.repair_action:!integrity&&store.state.game_update?.reapply_available?'reapply':null;
  return action?`<button class="button small primary" data-action="${e(action)}" data-id="${e(id)}" ${mutation(false)}>Review reinstall</button>`:'';
}

function setup() {
  const state=store.state;
  const targets=[...(state.source_path?[{path:state.source_path,name:'Normal game client'}]:[]),...(state.sandbox_targets??[])];
  return `<section class="setup-box"><h2>Add-ons for your game client</h2><p>Use the normal game client you already launch. Review and apply add-ons here, then open the game as usual.</p><form id="ah-connect-form"><label class="input-label" for="ah-installation-path">Selected client</label><div class="input-row"><select id="ah-installation-path" ${targets.length?'':'disabled'}>${targets.map(target=>`<option value="${e(target.path)}" ${target.path===state.installation?.path?'selected':''}>${e(target.name)}</option>`).join('')}</select><button class="button" type="submit" ${mutation(!targets.length)}>Connect client</button></div><p class="field-hint">Close this game client before applying changes. The server can stay running. Studio backs up changed pack files; game updates take priority and add-ons can be reviewed again afterwards.</p></form><details class="json-details"><summary>Advanced testing tools</summary><p>Optional separate targets for add-on development. A pack sandbox contains packs only; a playable test copy includes the runtime and assets.</p><div class="input-row"><button class="button" type="button" data-action="sandbox" ${mutation(!state.source_path)}>Create disposable sandbox</button><button class="button" type="button" data-action="test-client" ${mutation(!state.source_path)}>Create playable test copy</button></div></details></section>`;
}

function connection() {
  const profile=store.state.installation;if (!profile) return '';
  return `<div class="panel connection-card"><div class="metric-icon">${icon(profile.kind==='sandbox'?'layers':'folder')}</div><div class="connection-meta"><strong>${e(profile.name ?? profile.id ?? 'Connected installation')}</strong><span>${e(profile.path ?? profile.target_root ?? profile.details?.path ?? '')}</span></div><span class="pill ${profile.writable?'success':'copper'}">${targetLabel(profile)}</span><a class="button small ghost" href="#addonsettings">Manage</a></div>`;
}

function overview() {
  const installed=asArray(store.state.installed);const enabled=installed.filter(addon=>addon.enabled!==false);const profile=store.state.installation;
  return heading('YOUR GAME. YOUR WAY.','A home for your add-ons.','Discover useful additions, understand every change, and keep your installation in your control.')+banners()+
    `<section class="hero"><div><p class="eyebrow">BUILDING THE FOUNDATIONS</p><h2>Small additions.<br>A world of possibilities.</h2><p>A local workspace for Metin2 Singleplayer add-ons. Choose an add-on, review its changes, and apply it to your normal game client.</p><div class="hero-actions"><a class="button primary" href="#addons">Explore add-ons ${icon('arrow')}</a><a class="button ghost" href="#atlas">${icon('atlas')}Open boss atlas</a></div></div><div class="hero-art" aria-hidden="true"><div class="orbit"></div><div class="orbit"></div><div class="center">${icon('package')}</div><div class="orbit-point"></div><div class="orbit-point"></div></div></section>`+
    (profile?connection():setup())+
    `<div class="metric-grid"><div class="metric"><div><div class="metric-label">Your add-ons</div><div class="metric-value">${installed.length}</div><div class="metric-caption">${enabled.length} enabled in this workspace</div></div><div class="metric-icon">${icon('installed')}</div></div><div class="metric"><div><div class="metric-label">In the local catalog</div><div class="metric-value">${store.catalog.length}</div><div class="metric-caption">Bundled and downloaded packages</div></div><div class="metric-icon">${icon('discover')}</div></div><div class="metric"><div><div class="metric-label">Installation mode</div><div class="metric-value small">${targetLabel(profile)}</div><div class="metric-caption">${profile?.writable?(profile.kind==='installation'?'Changed client packs have backups':'Optional separate testing target'):profile?'Inspect without applying changes':'Connect to begin'}</div></div><div class="metric-icon">${icon('shield')}</div></div></div>`+
    (store.state.pending_plan ? `<div class="callout">${icon('info')}<p><strong>You have a change ready to review.</strong><br>${e(store.state.pending_plan.summary ?? humanize(store.state.pending_plan.action))}</p><button class="button small ghost" data-action="review-pending">Review plan</button></div>`:'')+
    `<div class="overview-columns"><section class="panel"><div class="panel-header"><h2>Recent activity</h2><a class="button link" href="#activity">View all ${icon('arrow')}</a></div><div class="small-list">${store.history.length?historyMarkup(store.history.slice(0,3)):empty('A fresh start','Your installation, update, and removal history will appear here.','',true,'activity')}</div></section><section class="panel"><div class="panel-header"><h2>A more considered install</h2>${icon('shield')}</div><div class="feature-row"><span class="step-number">01</span><div><h3>Choose an addition</h3><p>Read its source, requirements, and supported configuration.</p></div></div><div class="feature-row"><span class="step-number">02</span><div><h3>Review the real changes</h3><p>See the file plan and resolve conflicts before applying it.</p></div></div><div class="feature-row"><span class="step-number">03</span><div><h3>Keep a way back</h3><p>Changed pack files have backups, with tracked ownership and transaction recovery.</p></div></div></section></div><div class="overview-notice"><div>${icon('info')}<span><strong>An early foundation for a community.</strong> Subscribe to a creator catalog or try the bundled examples. Community hosting is still being prepared.</span></div><a class="button link" href="#addonsettings">Workspace details ${icon('arrow')}</a></div>`;
}

function addonIcon(item) {return /map|boss|atlas/i.test(`${item.id} ${item.category}`)?'atlas':/legend|coord/i.test(item.id)?'pin':'package';}
function itemError(item) {return item.error ?? planMessages(item.validation_errors).join('; ');}
function catalogCard(item) {
  const status=addonStatus(item,store.state.installed);const record=installedRecord(item,store.state.installed);const error=itemError(item);
  return `<article class="addon-card"><div class="addon-visual">${icon(addonIcon(item))}<span class="pill">${e(item.bundled?'Included with Studio':humanize(item.kind ?? 'client add-on'))}</span></div><div class="addon-card-body"><div class="addon-title-row"><h3>${e(item.name ?? item.id)}</h3><span class="addon-version">v${e(item.version ?? '?')}</span></div><p>${e(error||descriptionSummary(item.description)||'No description provided.')}</p><div class="addon-meta"><span>by ${e(typeof item.author==='object'?item.author.name:item.author ?? 'Unknown author')}</span><span class="category-label">${e(humanize(item.category ?? 'Uncategorized'))}</span></div></div><div class="addon-card-footer"><div class="detail-tags"><span class="pill ${status.tone}">${e(status.label)}</span>${isGameExtension(item)?'<span class="pill copper">Server &amp; client</span>':''}${compatibilityBadge(item)}</div>${!isGameExtension(item)&&!error&&item.valid!==false&&(!record||item.update_available)?`<label class="batch-choice"><input type="checkbox" data-batch-id="${e(item.id)}" ${batchSelection.has(item.id)?'checked':''}> Select for batch</label>`:''}<button class="button small ${record?'ghost':'primary'}" data-action="details" data-id="${e(item.id)}">View add-on ${icon('arrow')}</button></div></article>`;
}

function catalogResults() {
  const items=filterCatalog(store.catalog,ui.query,ui.category);
  return `<div class="result-label">${items.length} ${items.length===1?'add-on':'add-ons'}${ui.query?' matching your search':''} · Local catalog</div>${items.length?`<div class="catalog-grid">${items.map(catalogCard).join('')}</div>`:`<section class="panel">${empty('No add-ons found',store.catalog.length?'Try another search or category.':'This catalog has no readable packages. Check the local catalog directory in Settings.',store.catalog.length?'<button class="button ghost" data-action="clear-filters">Clear filters</button>':'')}</section>`}`;
}

function discover() {
  const categories=[...new Set([...store.catalog,...store.releases].map(item=>item.category).filter(Boolean))].sort();
  return heading('MAKE IT YOURS','Discover add-ons','Import a package or browse your repositories, then review its installation.',`<button class="button primary" data-action="choose-package" ${mutation(false)}>${icon('plus')}Import package</button><input type="file" id="ah-package-file" accept=".m2addon.zip,.zip,application/zip" aria-label="Choose an add-on ZIP" hidden>`)+banners()+
    batchToolbar()+`<div class="catalog-toolbar"><div class="search-field">${icon('search')}<label class="sr-only" for="ah-catalog-search">Search add-ons</label><input type="search" id="ah-catalog-search" placeholder="Search add-ons, authors, or features…" value="${e(ui.query)}" autocomplete="off"></div><label class="sr-only" for="ah-category-filter">Category</label><select id="ah-category-filter"><option value="all">All categories</option>${categories.map(category=>`<option value="${e(category)}" ${ui.category===category?'selected':''}>${e(humanize(category))}</option>`).join('')}</select></div><div id="ah-catalog-results">${catalogResults()}</div><section class="repository-offers"><div class="panel-header"><h2>Repository releases</h2><a class="button small" href="#repositories">Manage repositories</a></div><div id="ah-release-results">${releaseCards()}</div></section><div class="source-box"><strong>Review the source before installation.</strong><p>Choose packages and repositories you trust. Studio checks package integrity and shows file changes before installation.</p></div>`;
}

function releaseCards(){
  const offers=filterCatalog(store.releases,ui.query,ui.category);
  if(!offers.length)return empty('No repository releases in this view','Add a public GitHub repository or catalog URL in Repositories, or adjust your search.','<a class="button" href="#repositories">Open repositories</a>',true);
  return `<div class="catalog-grid">${offers.map(item=>{const latest=item.latest;return `<article class="addon-card remote-release-card" data-repository="${e(item.repository_id)}" data-addon="${e(item.id)}" data-blocked="${!!item.blocked}" data-offline="${!!item.error}"><div class="addon-card-body"><div class="addon-title-row"><h3>${e(item.name)}</h3>${item.update_available?'<span class="pill success">Update available</span>':''}</div><p>${e(item.description)}</p><p>${e(item.repository_name)} · ${e(item.publisher)}</p>${item.collection?`<p class="field-hint">Collection add-on · <code>${e(item.package_path)}</code> · Install independently</p>`:''}${item.error?`<p class="notice">${e(item.error)}</p>`:''}<label class="input-label">Release<select class="ah-release-version" aria-label="Release for ${e(item.name)}">${item.releases.map(release=>`<option value="${e(release.version)}" data-cached="${!!release.cached}" ${release.version===latest?.version?'selected':''} ${release.withdrawn?'disabled':''}>${e(release.kind==='development'?'Development · '+(item.default_branch??release.source_ref):release.version)}${release.cached?' · Cached':''}${release.withdrawn?' · Withdrawn':''}</option>`).join('')||'<option value="">No release in this channel</option>'}</select></label><p class="field-hint">${!latest&&item.source_kind==='github'?'No published release in this channel. Choose Development in Repositories to test the default branch. ':''}${item.installed_version?'Installed '+e(item.installed_version)+'. ':''}${item.selected_version?'Local catalog '+e(item.selected_version)+'. ':''}Downloading does not install it.</p></div><div class="addon-card-footer"><span class="pill">${item.source_kind==='github'?'GitHub':'Repository'}</span><button class="button small primary" data-action="review-download" ${mutation(item.blocked||!latest||!!item.error&&!latest?.cached)}>Review download</button></div></article>`;}).join('')}</div>`;
}

function repositories(){
  return heading('CHOOSE YOUR SOURCES','Repositories','Add a public GitHub repository or a creator’s catalog. Checks run only when you request them.')+
    `<section class="setup-box"><form id="ah-repository-form"><label class="input-label" for="ah-repository-url">GitHub repository or catalog URL</label><div class="input-row"><input type="url" id="ah-repository-url" placeholder="https://github.com/owner/addon" required><label class="sr-only" for="ah-repository-channel">Release channel</label><select id="ah-repository-channel"><option value="stable">Stable releases</option><option value="prerelease">Include prereleases</option><option value="development">Development branch (GitHub)</option></select><button type="submit" class="button primary" ${mutation(false)}>Add repository</button></div><p class="field-hint">GitHub sources use root addon.json, or addons.json listing separate add-on folders. Choose which add-ons to download and install. Use Development explicitly for unreleased branch snapshots. Catalog JSON URLs also work. Adding a source reads metadata; installation is reviewed separately.</p></form></section><div class="settings-stack">${store.repositories.map(repo=>`<section class="panel"><div class="panel-header"><h2>${e(repo.name)}</h2><span class="pill ${repo.blocked?'danger':repo.enabled?'success':'muted'}">${repo.blocked?'Blocked':repo.enabled?'Enabled':'Disabled'}</span></div><div class="panel-body"><p class="mono">${e(repo.url)}</p><p>${e(repo.publisher??'Publisher not loaded')} · ${repo.package_count} packages${repo.kind==='github'?' · GitHub'+(repo.layout==='collection'?' collection':'')+' · default branch '+e(repo.default_branch??'unknown'):''}</p><p class="field-hint">Last checked: ${e(formatTime(repo.checked_at))}</p>${repo.error?`<div class="callout danger"><p>${e(repo.error)}</p></div>`:''}<div class="work-actions"><button class="button small" data-action="repository-refresh" data-repository="${e(repo.id)}" ${mutation(false)}>Check for updates</button><button class="button small" data-action="repository-toggle" data-repository="${e(repo.id)}" data-enabled="${!repo.enabled}" ${mutation(false)}>${repo.enabled?'Disable':'Enable'}</button><label class="input-label">Channel<select class="ah-repository-channel" data-repository="${e(repo.id)}" ${mutation(false)}><option value="stable" ${repo.channel==='stable'?'selected':''}>Stable</option><option value="prerelease" ${repo.channel==='prerelease'?'selected':''}>Include prereleases</option>${repo.kind==='github'?`<option value="development" ${repo.channel==='development'?'selected':''}>Development branch</option>`:''}</select></label><button class="button small ghost" data-action="repository-remove" data-repository="${e(repo.id)}" ${mutation(false)}>Remove repository</button></div></div></section>`).join('')||`<section class="panel">${empty('No repositories yet','The bundled examples work without a subscription. Add a GitHub repository or catalog when you have a source you trust.')}</section>`}</div><div class="source-box"><strong>Repository controls preserve your installed state.</strong><p>Disabling or removing a repository stops new installs and enables from that source. Existing add-ons are retained; you can disable or remove them separately. Cached releases and recovery data remain on disk.</p></div>`;
}

function updatePanel(){
  return `<section class="panel addon-updates" id="ah-available-updates"><div class="panel-header"><h2>${store.updates.length?store.updates.length+' available '+(store.updates.length===1?'update':'updates'):'Add-on updates'}</h2><button class="button small primary" data-action="batch-updates" ${mutation(!store.updates.some(item=>item.download_ready&&!isGameExtension(store.catalog.find(row=>row.id===item.id))))}>Review ready client updates</button><button class="button small" data-action="check-addon-updates" ${mutation(!store.repositories.some(repo=>repo.enabled))}>${icon('refresh')}Check for updates</button></div><div class="panel-body"><p class="info-paragraph">Updates are manual. Read the changelog, download the releases you choose, then review ready client updates together. Server &amp; client extensions are reviewed individually.</p>${ui.updatesError?`<p class="notice">Update information unavailable: ${e(ui.updatesError)}</p>`:''}${store.updates.length?store.updates.map(item=>`<article class="update-row"><div><strong>${e(item.name)}</strong><p>${e(item.installed_version)} → ${e(item.available_version)}${item.development?' · Development snapshot':''}</p><small>${item.download_ready?'Package selected · ready for installation review':item.check_error?'Last known update · source check needs attention':'Available from '+e(item.repository_name??'repository')}</small></div><button class="button small" data-action="update-details" data-id="${e(item.id)}">Read changelog</button></article>`).join(''):'<p class="subtext">No known updates from your last checks. Check enabled repositories to refresh availability.</p>'}</div></section>`;
}

function openUpdateDetails(id){
  const item=store.updates.find(row=>row.id===id);if(!item)return;
  $('#ah-update-content').innerHTML=`<div class="dialog-header"><div><p class="eyebrow">ADD-ON UPDATE · YOUR CHOICE</p><h2 id="ah-update-title">${e(item.name)}</h2><p>${e(item.installed_version)} → ${e(item.available_version)}${item.development?' · Development snapshot':''}</p></div><button class="icon-button" data-action="close-update" aria-label="Close update changelog">${icon('close')}</button></div><div class="dialog-body"><p>Reading this changelog does not download or install anything. You decide when to update.</p><dl class="definition-list"><dt>Installed version</dt><dd>${e(item.installed_version)}</dd><dt>Available version</dt><dd>${e(item.available_version)}</dd>${item.installed_commit?`<dt>Installed commit</dt><dd class="mono">${e(item.installed_commit)}</dd>`:''}${item.available_commit?`<dt>Available commit</dt><dd class="mono">${e(item.available_commit)}</dd>`:''}<dt>Source</dt><dd class="mono">${e(item.repository_url??'Selected local or bundled package')}</dd>${item.checked_at?`<dt>Last successful check</dt><dd>${e(formatTime(item.checked_at))}</dd>`:''}</dl>${item.check_error?`<div class="callout danger"><p>Last known update. Source check needs attention: ${e(item.check_error)}</p></div>`:''}<h3>Changelog</h3><p class="field-hint">${item.kind==='selected'?'Notes from the package you selected. Review its version and source before applying.':item.development?'Author-provided notes from the development manifest.':'Known release notes since your installed version, from the last repository check. This may not include the project’s full history.'}</p>${(item.changes??[]).map(change=>`<section class="update-changelog"><h4>${e(change.version)}${change.withdrawn?' · Withdrawn':''}</h4>${change.withdrawn?`<p>${e(change.reason)}</p>`:''}<pre>${e(change.release_notes||'No changelog provided for this release.')}</pre></section>`).join('')||'<p>No changelog provided for this release.</p>'}</div><div class="dialog-footer"><button class="button ghost" data-action="close-update">Not now</button>${item.download_ready?`<button class="button primary" data-action="plan" data-operation="update" data-id="${e(id)}" ${mutation(false)}>Review installation changes</button>`:`<button class="button primary" data-action="review-update-download" data-id="${e(id)}" ${mutation(!item.can_download)}>Review download</button>`}</div>`;
  $('#ah-update-dialog').showModal();
}

function installedPage() {
  const installed=asArray(store.state.installed);
  return heading('YOUR COLLECTION','Installed add-ons','Manage what is enabled. Every change gets a file plan before it is applied.',`<a href="#addons" class="button primary">${icon('plus')}Find add-ons</a>`)+banners()+updatePanel()+(installed.length ?
    `<section class="panel"><div class="panel-header"><h2>${installed.length} installed ${installed.length===1?'add-on':'add-ons'}</h2><span class="tagline-inline">${installed.filter(item=>item.enabled!==false).length} enabled</span></div><div class="table-scroll"><table class="data-table"><thead><tr><th>Add-on</th><th>Version</th><th>Compatibility</th><th>${installed.some(isGameExtension)?'Files &amp; activation':'Client files'}</th><th>Enabled</th><th><span class="sr-only">Actions</span></th></tr></thead><tbody>${installed.map(record=>{const id=record.id??record.addon_id;const item=store.catalog.find(entry=>entry.id===id)??record;const status=record.integrity?.status==='healthy'?{label:'Verified',tone:'success'}:addonStatus(record,installed);return `<tr><td><div class="row-title"><div class="metric-icon">${icon(addonIcon(item))}</div><div><strong>${e(item.name??id)}</strong>${store.updates.some(update=>update.id===id)?'<span class="pill copper">Update available</span>':''}<small>${e(id)}${isGameExtension(item)?' · Server &amp; client':''}</small></div></div></td><td class="mono">${e(record.version??item.version??'Unknown')}${record.distribution?.commit?`<div class="field-hint">${e(record.distribution.selection==='development'?'Development':'Release')} · ${e(record.distribution.commit.slice(0,12))}</div>`:''}</td><td>${compatibilityBadge(record)}</td><td><span class="pill ${status.tone}">${e(status.label)}</span>${record.integrity?.status==='missing'?reinstallButton(id):''}</td><td><button class="toggle-button" role="switch" aria-checked="${record.enabled!==false}" aria-label="Enable ${e(item.name??id)}" data-action="plan" data-id="${e(id)}" data-operation="${record.enabled===false?'enable':'disable'}" ${mutation(false)}><span class="toggle-track" aria-hidden="true"></span>${record.enabled===false?'Disabled':'Enabled'}</button></td><td><div class="row-actions"><button class="button small ghost" data-action="details" data-id="${e(id)}">Details</button><button class="icon-button" aria-label="Remove ${e(item.name??id)}" title="Review removal" data-action="plan" data-id="${e(id)}" data-operation="remove" ${mutation(false)}>${icon('remove')}</button></div></td></tr>`;}).join('')}</tbody></table></div></section>`:
    `<section class="panel">${empty('Your collection starts here','Install an example in a disposable sandbox to try the full review, enable, and removal workflow.','<a class="button primary" href="#addons">Explore add-ons '+icon('arrow')+'</a>')}</section>`)+`<div class="source-box"><strong>Removal respects ownership.</strong><p>The manager rebuilds the remaining add-on combination. Unexpected manual changes must be resolved before writing files.</p></div>`;
}

function historyMarkup(items) {
  return items.map(entry=>{
    const failed=['failed','error','interrupted'].includes(entry.status??entry.outcome);const title=entry.summary ?? entry.message ?? `${humanize(entry.action??entry.event??entry.type??'Workspace change')}${entry.addon_id?' · '+entry.addon_id:''}`;
    return `<div class="activity-item"><div class="activity-dot ${failed?'danger':''}">${icon(failed?'warning':entry.action==='recover'?'refresh':'check')}</div><div class="activity-content"><h3>${e(title)}</h3><p>${e(entry.error??entry.details?.message??entry.description??(entry.addon_id&&title!==entry.addon_id?entry.addon_id:humanize(entry.status??entry.outcome??'')))}</p></div><time class="activity-time">${e(formatTime(entry.timestamp??entry.time??entry.created_at??entry.date))}</time></div>`;
  }).join('');
}

function activity() {
  return heading('ONE WORLD, TWO WORKFLOWS','Activity','Recent server changes and transactions across this world’s add-on targets.')+`<section class="panel"><div class="panel-header"><h2>Recent activity</h2><a class="button small" href="#history">Server rollback history ↗</a></div>${(store.activity??[]).length?(store.activity??[]).map(row=>`<article class="activity-item"><span class="pill muted">${row.kind==='addon'?'Add-on':'Server'}</span><div class="activity-content"><h3>${e(row.title)}</h3><p>${e(row.detail)}</p></div><time>${e(formatTime(row.at))}</time></article>`).join(''):empty('No recorded changes','Server saves and add-on transactions will appear here.')}</section>`;
}

function settings() {
  const p=store.state.installation;const diagnostics=store.diagnostics;
  return heading('LOCAL & IN YOUR CONTROL','Workspace settings','Inspect the installation, select an owned test target, and review diagnostics.')+banners()+setup()+
    `<div class="settings-grid"><section class="panel"><div class="panel-header"><h2>Connected installation</h2><span class="pill ${p?.writable?'success':'muted'}">${targetLabel(p)}</span></div><div class="panel-body">${p?`<dl class="definition-list"><dt>Profile</dt><dd>${e(p.name??p.id)}</dd><dt>Client version</dt><dd>${e(p.client_version??'Unknown')}</dd><dt>Server version</dt><dd>${e(p.server_version??'Unknown')}</dd><dt>Write access</dt><dd>${p.writable?targetLabel(p):'Disabled'}</dd><dt>Path</dt><dd class="mono">${e(p.path??p.target_root??p.details?.path??'See diagnostics')}</dd><dt>Fingerprint</dt><dd class="mono">${e(p.fingerprint??'Unavailable')}</dd></dl>`:empty('No installation connected','Use the form above to inspect an existing game installation.','',true,'folder')}</div></section><section class="panel"><div class="panel-header"><h2>About this alpha</h2><span class="alpha">LOCAL</span></div><div class="panel-body"><dl class="definition-list"><dt>Manager</dt><dd>Metin2 Add-on Hub ${e(store.state.version??'alpha')}</dd><dt>Package format</dt><dd>Version 1 · Client Python</dd><dt>Catalog</dt><dd>Bundled examples and subscribed repositories</dd><dt>Client integration</dt><dd>Experimental, requires in-game verification</dd></dl><p class="info-paragraph mt-20 mb-0">This workspace exercises the framework and installation lifecycle. Sandbox success alone does not establish compatibility with a running game.</p></div></section></div><section class="panel mt-20"><div class="panel-header"><h2>Diagnostics</h2><button class="button small" data-action="support-report">Download support report</button><button class="button small ghost" data-action="diagnostics">${icon('refresh')}Refresh diagnostics</button></div><div class="panel-body"><p class="info-paragraph">The local view includes paths and fingerprints. The downloadable support report omits paths, tokens, settings, repository URLs and game content.</p>${diagnostics?`<pre class="diagnostics">${e(JSON.stringify(diagnostics,null,2))}</pre>`:`<p class="subtext">${ui.diagnosticsError?e(ui.diagnosticsError):'Loading diagnostic information…'}</p>`}</div></section>`;
}

function sourceMarkup(map) {
  return `<details class="source-box help-details"><summary>Sources & coverage</summary><p>${e(map?.coverage?.scope||'Installed spawn configuration.')}</p><p>Base intervals; no live presence or countdown. ${e(map?.coverage?.intervals||'')}</p><p class="mono">${e(sourceLabel(map?.source))}</p>${map?.original_name&&map.original_name!==map.name?`<p>Configured name: ${e(map.original_name)}</p>`:''}${map?.coverage?.omitted?.length?`<p>${map.coverage.omitted.length} unsupported or malformed rows omitted.</p>`:''}</details>`;
}
const atlasDrops=new Map();
const atlasTypes=[['all','All'],['monster','Mobs'],['boss','Bosses'],['metin','Metins'],['ore','Mining ores'],['npc','NPCs']];
function atlas() {
  const map=store.map,species=atlasSpecies(map,ui.atlasFilter,ui.atlasSearch),regions=species.flatMap(m=>m.zones);
  const label=m=>host.mobContent?host.mobContent(m.mob_id,{detail:m.type==='ore'?'Mining deposit':undefined,iconCategory:m.type==='ore'?'ore':undefined}):`<span><strong>${e(m.name)}</strong><small>#${e(m.mob_id)} · Lv. ${e(m.level??'?')}</small></span>`;
  return heading('KNOW THE WORLD','World atlas','Explore creatures, spawn zones and configured drops.')+banners()+
    `<div class="atlas-toolbar"><select id="ah-map-select" aria-label="Map">${store.maps.map(m=>`<option value="${e(m.id)}" ${String(m.id)===String(ui.mapId)?'selected':''}>${e(m.name)}</option>`).join('')}</select><input id="ah-atlas-search" type="search" aria-label="Search atlas creatures" placeholder="Creature name or ID…" value="${e(ui.atlasSearch)}"><span>${species.length} creatures · ${regions.length} zones</span></div>`+
    `<div class="atlas-filters" role="group" aria-label="Quick spawn filters">${atlasTypes.map(([id,name])=>`<button type="button" class="button small" data-atlas-filter="${id}" aria-pressed="${ui.atlasFilter===id}">${name}<span>${atlasSpecies(map,id,ui.atlasSearch).length}</span></button>`).join('')}</div>`+
    (ui.atlasError?`<div class="callout danger">${e(ui.atlasError)}<button data-action="reload-atlas" class="button">Retry</button></div>`:ui.atlasLoading?'<div class="loading">Loading map…</div>':map?
      `<div class="atlas-layout"><section class="panel atlas-map-panel"><div class="panel-header"><h2>${e(map.name)}</h2><button class="button small ghost" id="atlas-clear-focus">Show all zones</button></div>${mapGraphic(map,regions)}</section><section class="panel atlas-spawn-panel"><div class="panel-header"><h2>Creatures</h2><span>Hover to isolate · click to pin</span></div><div class="atlas-list">${species.map(m=>`<button type="button" class="spawn-row" data-atlas-creature="${e(m.mob_id)}" aria-pressed="${ui.atlasPinned===m.mob_id}">${label(m)}<span class="spawn-zone-count">${m.zones.length} ${m.zones.length===1?'zone':'zones'}</span></button>`).join('')||'<div class="empty">No creatures match these filters.</div>'}</div><section class="atlas-inspection" id="atlas-inspection" aria-label="Creature details" hidden></section></section></div>`:'<div class="empty">No configured maps available.</div>')+sourceMarkup(map);
}
function mapGraphic(map,regions) {
  const {x,y,width,height}=mapBounds(map,mapRegions(map));
  const safeImage=typeof map.image_url==='string'&&map.image_url.startsWith('/api/addons/map-image?')?map.image_url:null;
  const imageLabel=!safeImage?'Spawn diagram · no map image':map.image_source==='game-navigation'?'Navigation layout · configured zones':map.image_source==='client-atlas'?'Client atlas · configured zones':'Configured spawn zones';
  const radius=Math.max(width,height)/140;
  const grid=Array.from({length:9},(_,i)=>`<path d="M${x+width*(i+1)/10} ${y}v${height}M${x} ${y+height*(i+1)/10}h${width}" class="atlas-grid-line"/>`).join('');
  const marks=regions.filter(r=>Number.isFinite(r.x)&&Number.isFinite(r.y)).map(r=>`<g class="atlas-feature" data-atlas-mob="${e(r.mob_id)}" data-atlas-creature="${e(r.mob_id)}"><title>${e(r.name)} · ${r.x}, ${r.y} · ${e(respawnLabel(r))}</title>${r.width&&r.height?`<rect x="${r.x-r.width/2}" y="${r.y-r.height/2}" width="${r.width}" height="${r.height}" class="atlas-region" vector-effect="non-scaling-stroke"/>`:''}<circle cx="${r.x}" cy="${r.y}" r="${radius}" class="atlas-marker ${r.type==='metin'?'metin':''}" vector-effect="non-scaling-stroke"/></g>`).join('');
  return `<div class="atlas-canvas"><span class="atlas-tag">${imageLabel}${map.coverage?.bounds_verified===false?' · extent unverified':''}</span><svg viewBox="${x} ${y} ${width} ${height}" role="img" aria-label="${e(map.name)} configured spawn zones" preserveAspectRatio="xMidYMid meet">${safeImage?`<image href="${e(safeImage)}" x="${x}" y="${y}" width="${width}" height="${height}" preserveAspectRatio="none" opacity="1"/>`:''}${grid}${marks}</svg></div>`;
}
async function focusAtlas(id,pin=false){
  if(ui.page!=='atlas'||!host?.current())return;
  if(pin)ui.atlasPinned=ui.atlasPinned===id?'':id;
  const selected=pin?ui.atlasPinned:id||ui.atlasPinned;
  if(!pin&&selected===ui.atlasFocus&&$('#atlas-inspection')?.hidden===!selected)return;
  ui.atlasFocus=selected;const request=++ui.atlasHoverRequest;
  host.root.querySelectorAll('[data-atlas-mob]').forEach(node=>{node.style.display=selected&&node.dataset.atlasMob!==selected?'none':''});
  host.root.querySelectorAll('button[data-atlas-creature]').forEach(node=>{node.classList.toggle('selected',node.dataset.atlasCreature===selected);node.setAttribute('aria-pressed',String(node.dataset.atlasCreature===ui.atlasPinned))});
  const detail=$('#atlas-inspection');if(!detail)return;
  detail.hidden=!selected;
  if(!selected){detail.innerHTML='';return;}
  const mob=atlasSpecies(store.map).find(m=>m.mob_id===selected);if(!mob)return;
  detail.innerHTML=`<div class="atlas-creature-head"><div class="atlas-creature-identity">${host.mobContent?host.mobContent(selected,{detail:mob.type==='ore'?'Mining deposit':undefined,iconCategory:mob.type==='ore'?'ore':undefined}):`<strong>${e(mob.name)}</strong>`}</div><div class="atlas-creature-actions"><span class="pill">${ui.atlasPinned===selected?'Pinned':'Preview'} · ${mob.zones.length} zones</span>${mob.type!=='ore'?`<button class="button small" data-action="open-drops" data-id="${e(selected)}">View drops in Studio ↗</button>`:''}</div></div><div class="atlas-creature-drops" role="status">${mob.type==='ore'?'Mining deposit · rewards come from the game’s mining system.':'Loading configured drops…'}</div><details class="help-details"><summary>Spawn configuration</summary>${mob.zones.map(r=>`<p>X ${e(r.x)} · Y ${e(r.y)} · ${e(respawnLabel(r))}${r.random_group?' · possible random group':r.group_spawn?' · group spawn':''} <button class="subtle-link" data-action="open-map-source" data-path="${e(r.source)}">${e(String(r.source??'').split('/').pop())}:${e(r.line)}</button></p>`).join('')}</details>`;
  positionAtlasPreview(selected);
  if(mob.type==='ore'||!host.mobSummary)return;
  try{
    let cached=atlasDrops.get(selected);
    if(!cached||Date.now()-cached.at>30000){cached={at:Date.now(),promise:host.mobSummary(selected)};atlasDrops.set(selected,cached);}
    const data=await cached.promise;
    if(request!==ui.atlasHoverRequest||ui.atlasFocus!==selected||!host.current())return;
    const target=$('.atlas-creature-drops');if(!target)return;
    const preview=data.drops.slice(0,4);
    target.innerHTML=`<strong>${data.dropCount} configured items</strong><div class="atlas-drop-grid">${preview.map(item=>host.itemReference(item)).join('')||'<span>No configured drops in Studio’s sources.</span>'}</div><small>${e(data.scope)}${data.dropCount>preview.length?' Showing '+preview.length+'; open View drops for all.':''}</small>`;
    host.bindImages?.(detail);positionAtlasPreview(selected);
  }catch{if(request===ui.atlasHoverRequest&&$('.atlas-creature-drops'))$('.atlas-creature-drops').textContent='Drop details unavailable. Hover again to retry.';atlasDrops.delete(selected);}
}

function positionAtlasPreview(id){
  const panel=$('.atlas-spawn-panel'),detail=$('#atlas-inspection');
  const row=host?.root?.querySelector(`button[data-atlas-creature="${id}"]`);
  if(!panel?.getBoundingClientRect||!row?.getBoundingClientRect||!detail||detail.hidden)return;
  const box=panel.getBoundingClientRect(),anchor=row.getBoundingClientRect();
  const list=panel.querySelector('.atlas-list').getBoundingClientRect();
  const top=Math.max(list.top,12),bottom=Math.min(box.bottom-12,window.innerHeight-12);
  const below=bottom-anchor.bottom-6,above=anchor.top-top-6,placeBelow=below>=above;
  detail.style.maxHeight=Math.max(120,Math.min(340,placeBelow?below:above))+'px';
  const height=detail.getBoundingClientRect().height;
  const preferred=placeBelow?anchor.bottom+6:anchor.top-height-6;
  detail.style.top=Math.max(top,Math.min(preferred,bottom-height))-box.top+'px';
}

async function loadAtlas(force=false) {
  const request=(ui.atlasRequest??0)+1;ui.atlasRequest=request;
  ui.atlasPinned='';ui.atlasFocus='';atlasDrops.clear();ui.atlasLoading=true;ui.atlasError='';if(ui.page==='atlas')render();
  try {
    if(force||!store.maps.length){const response=unwrap(await api('maps'),'data');if(request!==ui.atlasRequest)return;store.maps=asArray(response.maps??response.items);store.mapsMeta=response;}
    if(!ui.mapId||!store.maps.some(map=>String(map.id)===String(ui.mapId)))ui.mapId=String(store.maps[0]?.id??'');
    if(ui.mapId){const response=await api(`map?map=${encodeURIComponent(ui.mapId)}`);if(request!==ui.atlasRequest)return;store.map=unwrap(response,'map');}else store.map=null;
  }catch(error){if(request===ui.atlasRequest)ui.atlasError=error.message;}finally{if(request===ui.atlasRequest){ui.atlasLoading=false;if(ui.page==='atlas')render();}}
}

async function loadDiagnostics() {
  try{store.diagnostics=unwrap(await api('diagnostics'),'diagnostics');ui.diagnosticsError='';}catch(error){ui.diagnosticsError=error.message;}
  if(ui.page==='settings')render();
}

function render() {
  if(!host?.current())return;
  const target=store.state.installation;
  const toolbar=`<div class="addon-toolbar"><span class="pill">${targetLabel(target)}</span>${store.updates.length?`<a href="#installed" class="button small copper">${store.updates.length} ${store.updates.length===1?'update':'updates'} available</a>`:''}<a href="#repositories" class="button small">Repositories</a><a href="#addonsettings" class="button small">Add-on settings</a><button class="button small" id="ah-refresh" data-action="refresh">Refresh</button></div>`;
  if(ui.error){host.root.innerHTML=`<div class="m2addons"><section class="error-page"><h1>Add-on tools unavailable</h1><p>${e(ui.error)}</p><button class="button" data-action="refresh">Try again</button></section></div>`;return;}
  if(!ui.loaded)return;
  host.root.innerHTML='<div class="m2addons">'+toolbar+'<div id="ah-network-job">'+networkJobMarkup()+'</div>'+({overview,discover,installed:installedPage,atlas,activity,settings,repositories}[ui.page]??discover)()+'</div>';
  host.bindImages?.(host.root);
  if(ui.page==='atlas'&&ui.atlasPinned)focusAtlas(ui.atlasPinned);
}

export async function mount(context) {
  host=context;ui.jobWatch++;
  ui.page=({addons:'discover',installed:'installed',atlas:'atlas',activity:'activity',addonsettings:'settings',repositories:'repositories'})[context.page]??'discover';
  ui.error='';
  try{
    await refresh({reconnect:true});
    if(!context.current())return;
    if(ui.page==='atlas')await loadAtlas(true);
    if(ui.page==='settings')await loadDiagnostics();
    watchIntegrity(context);
  }catch(error){ui.error=error.message;render();}
}

function distributionMarkup(item){
  const source=item.distribution;
  if(!source)return '';
  return `<dt>Package source</dt><dd class="mono">${e(source.kind==='local'?'Local file: '+source.filename:source.repository_url)}</dd>${source.kind==='github'?`<dt>Add-on folder</dt><dd class="mono">${e(source.package_path||'Repository root')}</dd><dt>Source reference</dt><dd>${e(source.selection==='development'?'Development · '+source.source_ref:source.source_ref)}</dd><dt>Commit</dt><dd class="mono">${e(source.commit)}</dd>`:''}<dt>Archive SHA-256</dt><dd class="mono">${e(source.sha256)}</dd>`;
}

function openDetails(id) {
  const item=store.catalog.find(addon=>addon.id===id)??store.state.installed.find(addon=>addon.id===id);if(!item)return;
  ui.detailsId=id;const record=installedRecord(item,store.state.installed);const status=addonStatus(item,store.state.installed);const error=itemError(item);
  const requires=asArray(item.requires);const conflicts=asArray(item.conflicts);
  $('#ah-details-content').innerHTML=`<div class="dialog-header"><div><p class="eyebrow">${e(humanize(item.category??'Add-on'))} · LOCAL ALPHA PACKAGE</p><h2 id="ah-details-title">${e(item.name??item.id)}</h2><p>v${e(item.version??'?')} · by ${e(typeof item.author==='object'?item.author.name:item.author??'Unknown author')}</p></div><button class="icon-button" data-action="close-details" aria-label="Close add-on details">${icon('close')}</button></div><div class="dialog-body">${error?`<div class="callout danger">${icon('warning')}<p>${e(error)}</p></div>`:''}${descriptionMarkup(item.description)}${isGameExtension(item)?extensionComponentsMarkup({...item,...record,components:record?.components??item.components}):''}<div class="detail-tags"><span class="pill ${status.tone}">${e(status.label)}</span><span class="pill muted">${isGameExtension(item)?'Server &amp; client':e(humanize(item.kind??'client-python'))}</span>${item.license?`<span class="pill muted">${e(item.license)}</span>`:''}</div><h3>Package information</h3><dl class="definition-list"><dt>Identifier</dt><dd class="mono">${e(item.id)}</dd>${distributionMarkup(item)}${record?.distribution?.commit&&record.distribution.commit!==item.distribution?.commit?`<dt>Installed commit</dt><dd class="mono">${e(record.distribution.commit)}</dd>`:''}<dt>${isGameExtension(item)?'Integration':'Entry point'}</dt><dd class="mono">${e(item.entry??'Not provided')}</dd><dt>Dependencies</dt><dd>${requires.length?requires.map(value=>e(typeof value==='string'?value:JSON.stringify(value))).join(', '):'None declared'}</dd><dt>Conflicts</dt><dd>${conflicts.length?conflicts.map(value=>e(typeof value==='string'?value:JSON.stringify(value))).join(', '):'None declared'}</dd><dt>Capabilities</dt><dd>${asArray(item.capabilities).map(value=>e(typeof value==='string'?humanize(value):JSON.stringify(value))).join(', ')||'None declared'}</dd></dl>${compatibilityDetails(item)}<div class="callout">${icon('info')}<p>${isGameExtension(item)?'This extension manages server activation and client-data fixes. Review both components before applying. Mounted combat remains a separate option.':'Add-ons run with the game client’s permissions. Choose code you trust.'}</p></div>${item.release_notes?`<h3>Release notes</h3><p class="detail-description">${e(typeof item.release_notes==='string'?item.release_notes:JSON.stringify(item.release_notes))}</p>`:''}<details class="json-details"><summary>View package manifest</summary><pre>${e(JSON.stringify(item,null,2))}</pre></details></div><div class="dialog-footer"><span>${store.state.installation?'Target: '+targetLabel(store.state.installation):'Connect an installation to review changes'}</span>${item.distribution?.kind==='local'?`<button class="button ghost" data-action="forget-package" data-id="${e(id)}" ${mutation(false)}>Remove from catalog</button>`:''}<button class="button ghost" data-action="close-details">Close</button>${record?`${record.integrity?.status==='missing'?reinstallButton(id):''}<button class="button danger" data-action="plan" data-id="${e(id)}" data-operation="remove" ${mutation(false)}>Review removal</button>${(item.update_available || (record.version && record.version !== item.version))?`<button class="button primary" data-action="plan" data-id="${e(id)}" data-operation="update" ${mutation(!!error)}>Review update ${icon('arrow')}</button>`:''}`:`<button class="button primary" data-action="plan" data-id="${e(id)}" data-operation="install" ${mutation(!!error||!store.state.installation)}>Review install ${icon('arrow')}</button>`}</div>`;
  const body=$('#ah-details-content .dialog-body');
  if(item.errors?.length||item.warnings?.length){const messages=document.createElement('div');messages.className=`callout ${item.errors?.length?'danger':''}`;messages.innerHTML=`${icon('info')}<ul class="warning-list">${[...planMessages(item.errors),...planMessages(item.warnings)].map(message=>`<li>${e(message)}</li>`).join('')}</ul>`;body.prepend(messages);}
  if(record){
    if((record.capabilities??item.capabilities??[]).includes('knowledge.read')){
      const section=document.createElement('section');
      section.innerHTML=referenceMarkup(store.state.reference)+`<button class="button small" data-action="plan" data-id="${e(id)}" data-operation="refresh-data" ${mutation(record.enabled===false)}>Review reference-data refresh</button><p class="field-hint">Refresh follows the same reviewed pack transaction. The in-game wiki works with Studio closed.</p>`;
      body.insertBefore(section,body.querySelector('.json-details'));
    }
    const fields=settingFields(item,record);
    if(fields.length){const form=document.createElement('form');form.id='addon-settings-form';form.dataset.id=id;form.className='addon-settings';form.innerHTML=`<h3>Add-on settings</h3>${fields.map(settingControl).join('')}<button class="button small primary" type="submit" ${mutation(false)}>Review settings change ${icon('arrow')}</button><p class="field-hint">Settings are applied through the same reviewed installation plan.</p>`;body.insertBefore(form,body.querySelector('.json-details'));}
  }
  if(!$('#ah-details-dialog').open)$('#ah-details-dialog').showModal();
}

function settingControl(field){
  let control;
  if(field.spec.enum)control=`<select name="${e(field.key)}">${field.spec.enum.map(value=>`<option value="${e(JSON.stringify(value))}" ${JSON.stringify(value)===JSON.stringify(field.value)?'selected':''}>${e(typeof value==='object'?JSON.stringify(value):value)}</option>`).join('')}</select>`;
  else if(field.type==='boolean')return `<label class="setting-checkbox"><input type="checkbox" name="${e(field.key)}" ${field.value?'checked':''}><span>${e(field.label)}<small>${e(field.description)}</small></span></label>`;
  else if(['array','object'].includes(field.type))control=`<textarea name="${e(field.key)}" rows="5" spellcheck="false">${e(JSON.stringify(field.value,null,2))}</textarea>`;
  else control=`<input name="${e(field.key)}" type="${['number','integer'].includes(field.type)?'number':'text'}" ${field.type==='integer'?'step="1"':field.type==='number'?'step="any"':''} value="${e(field.value)}">`;
  return `<label class="addon-setting-field">${e(field.label)}${control}<small>${e(field.description)}${['array','object'].includes(field.type)?' Edit as JSON.':''}</small></label>`;
}

function openDownloadReview(review){
  ui.downloadReview=review;
  const github=review.source_kind==='github';
  $('#ah-download-content').innerHTML=`<div class="dialog-header"><div><p class="eyebrow">DOWNLOAD REVIEW</p><h2 id="ah-download-title">${e(review.name)} ${e(review.version)}</h2></div><button class="icon-button" data-action="close-download" aria-label="Close download review">${icon('close')}</button></div><div class="dialog-body"><div class="callout"><p>${e(review.notice)}</p></div><dl class="definition-list"><dt>Repository</dt><dd class="mono">${e(review.repository_url)}</dd><dt>Publisher</dt><dd>${e(review.publisher)}</dd>${github?`<dt>Add-on folder</dt><dd class="mono">${e(review.package_path||'Repository root')}</dd>${review.collection?'<dt>Selection</dt><dd>Only this add-on is downloaded; other collection members stay unselected.</dd>':''}<dt>Source reference</dt><dd>${e(review.kind==='development'?'Development · '+review.source_ref:review.source_ref)}</dd><dt>Pinned commit</dt><dd class="mono">${e(review.commit)}</dd><dt>Manifest SHA-256</dt><dd class="mono">${e(review.manifest_digest)}</dd>`:''}<dt>Archive</dt><dd>${review.bytes!=null?e(review.bytes)+' bytes':'Source snapshot up to 66 MiB; only declared files are staged.'}</dd><dt>Package SHA-256</dt><dd class="mono">${review.sha256?e(review.sha256):'Computed after source validation and packaging.'}</dd><dt>Download URL</dt><dd class="mono">${e(review.url)}</dd></dl><h3>Release notes</h3><p class="detail-description">${e(review.release_notes)}</p>${github?`<details class="json-details"><summary>Repository README at this commit</summary><pre>${e(review.readme||'No README.md provided for this add-on.')}</pre></details>`:''}${review.source_changed?`<div class="callout danger"><p>This changes the repository for this add-on. Previous source: ${e(review.previous_source)}</p></div><label class="setting-checkbox"><input type="checkbox" id="ah-accept-source"><span>I accept this repository source change.</span></label>`:''}</div><div class="dialog-footer"><button class="button" data-action="close-download">Cancel</button><button class="button primary" id="ah-download-confirm" data-action="download-release" ${mutation(review.source_changed)}>Download and verify</button></div>`;
  $('#ah-download-dialog').showModal();
}

function openPlan(plan) {
  if(host.reviewApply){
    for(const kind of ['details','update','plan'])$('#ah-'+kind+'-dialog')?.close();
    host.reviewApply({addonPlanId:plan.id});
    return;
  }
  ui.plan=plan;const changes=changeRows(plan.changes);const warnings=planMessages(plan.warnings),conflicts=planMessages(plan.conflicts);const p=store.state.installation;
  const needsSharedReview=isGameExtension(plan)&&plan.server_required;
  const summary=typeof plan.summary==='string'?plan.summary:plan.summary?JSON.stringify(plan.summary):`${humanize(plan.action)} ${plan.addon_id}`;
  $('#ah-plan-content').innerHTML=`<div class="dialog-header"><div><p class="eyebrow">REVIEW BEFORE APPLYING</p><h2 id="ah-plan-title">${e(humanize(plan.action??'Installation'))} plan</h2><p>${e(plan.batch?plan.batch.length+' selected add-ons':['repair','reapply'].includes(plan.action)?(plan.installed??[]).length+' saved add-ons':plan.addon_id??'Managed installation change')}</p></div><button class="icon-button" data-action="close-plan" aria-label="Close change plan">${icon('close')}</button></div><div class="dialog-body"><div class="plan-summary">${e(summary)}</div>${batchPlanMarkup(plan)}${isGameExtension(plan)?extensionComponentsMarkup(plan):''}${needsSharedReview?'<p class="notice" role="status">Open Review &amp; apply in Studio to build and restart the required server activation changes.</p>':''}<div class="plan-target"><span>Target: <strong>${e(p?.name??p?.id??'Unknown installation')}</strong></span><span class="pill ${p?.writable?'success':'copper'}">${targetLabel(p)}</span></div>${conflicts.length?`<div class="callout danger">${icon('warning')}<div><strong>Resolve these conflicts first</strong><ul class="warning-list">${conflicts.map(message=>`<li>${e(message)}</li>`).join('')}</ul></div></div>`:''}${warnings.length?`<div class="callout">${icon('info')}<div><strong>Plan notes</strong><ul class="warning-list">${warnings.map(message=>`<li>${e(message)}</li>`).join('')}</ul></div></div>`:''}<h3>${changes.length} planned file ${changes.length===1?'change':'changes'}</h3>${changes.length?`<ul class="change-list">${changes.map(change=>`<li><span class="pill muted">${e(change.action)}</span><div><code>${e(change.path)}</code>${change.detail?`<small>${e(change.detail)}</small>`:''}</div></li>`).join('')}</ul>`:'<p>No file differences were reported by the manager.</p>'}<p class="raw-note">The manager rechecks the reviewed state before writing. A changed installation or another completed operation invalidates this plan.</p>${['batch','reapply','repair'].includes(plan.action)&&['installation','test-client'].includes(p?.kind)?'<label class="setting-checkbox"><input type="checkbox" id="ah-launch-client"><span>Open the game client once after all changes succeed.</span></label>':''}<details class="json-details"><summary>Inspect complete plan</summary><pre>${e(JSON.stringify(plan,null,2))}</pre></details></div><div class="dialog-footer"><span>${needsSharedReview?'Apply these changes from Studio’s combined review.':plan.can_apply?'Review complete? Apply this exact plan.':'This plan cannot be applied.'}</span><button class="button ghost" data-action="close-plan">Cancel</button><button class="button primary" data-action="apply" ${mutation(!plan.can_apply||needsSharedReview)}>${icon('check')}Apply ${e(humanize(plan.action??'change').toLowerCase())}</button></div>`;
  if(plan.reference){const section=document.createElement('div');section.innerHTML=referenceMarkup(plan.reference);$('#ah-plan-content .dialog-body').append(section);}
  $('#ah-details-dialog').close();$('#ah-update-dialog').close();if(!$('#ah-plan-dialog').open)$('#ah-plan-dialog').showModal();
}

async function runMutation(operation,successMessage) {
  if(ui.busy)return;setBusy(true);
  try{const result=await operation();await refresh({quiet:true});if(successMessage)toast(successMessage);return result;}
  catch(error){toast(error.message,true);try{await refresh({quiet:true});}catch{}throw error;}
  finally{setBusy(false);}
}

document.addEventListener('click',async event=>{
  const button=event.target.closest('.m2addons [data-action]');if(!button||button.disabled)return;
  const context=host;
  const action=button.dataset.action,id=button.dataset.id;
  try{
    if(action==='open-drops')await host.openDrops(id);
    else if(action==='open-map-source')await host.openMapSource(button.dataset.path);
    else if(action==='details')openDetails(id);
    else if(action==='update-details')openUpdateDetails(id);
    else if(action==='close-update')$('#ah-update-dialog').close();
    else if(action==='check-addon-updates')await startNetworkJob('repositories/check-updates',{});
    else if(action==='review-update-download'){
      const item=store.updates.find(row=>row.id===id);
      if(item)await startNetworkJob('releases/review',{repository_id:item.repository_id,addon_id:item.id,version:item.selection});
    }
    else if(action==='choose-package'){const input=$('#ah-package-file');input.value='';input.click();}
    else if(action==='close-download')$('#ah-download-dialog').close();
    else if(action==='review-download'){
      const card=button.closest('.remote-release-card');
      await startNetworkJob('releases/review',{repository_id:card.dataset.repository,addon_id:card.dataset.addon,version:card.querySelector('select').value});
    }
    else if(action==='download-release')await startNetworkJob('releases/download',{review_id:ui.downloadReview.id,accept_source_change:$('#ah-accept-source')?.checked===true});
    else if(action==='repository-refresh')await startNetworkJob('repositories/refresh',{repository_id:button.dataset.repository});
    else if(action==='cancel-network-job'){
      const result=await api('jobs/cancel',{job_id:button.dataset.job});
      if(host===context&&context.current()){store.state.network_job=result.job;const panel=$('#ah-network-job');if(panel)panel.innerHTML=networkJobMarkup();}
    }
    else if(action==='network-job-result'){
      const result=await api('job?id='+encodeURIComponent(button.dataset.job));
      if(host===context&&context.current()){
        if(result.job.result?.review)openDownloadReview(result.job.result.review);
        else toast('This review is no longer available. Review the release again.',true);
      }
    }
    else if(action==='repository-toggle')await runMutation(()=>api('repositories/configure',{repository_id:button.dataset.repository,enabled:button.dataset.enabled==='true'}),'Repository preference saved.');
    else if(action==='repository-remove')await runMutation(()=>api('repositories/remove',{repository_id:button.dataset.repository}),'Repository removed. Installed add-ons and cached data were retained.');
    else if(action==='forget-package'){const result=await runMutation(()=>api('packages/forget',{addon_id:id}),'Removed from the catalog. Installed add-ons were retained.');if(result)$('#ah-details-dialog').close();}
    else if(action==='close-details')$('#ah-details-dialog').close();
    else if(action==='close-plan')$('#ah-plan-dialog').close();
    else if(action==='clear-filters'){ui.query='';ui.category='all';render();$('#ah-catalog-search')?.focus();}
    else if(action==='refresh'){setBusy(true);try{await refresh({reconnect:true});if(ui.page==='atlas')await loadAtlas(true);if(ui.page==='settings')await loadDiagnostics();toast('Workspace refreshed.');}finally{setBusy(false);}}
    else if(action==='review-pending')openPlan(store.state.pending_plan);
    else if(action==='plan'||action==='reapply'||action==='repair'){
      if(ui.busy)return;setBusy(true);
      try{const result=await api('plan',{addon_id:['reapply','repair'].includes(action)?id||store.state.installed[0]?.id:id,action:['reapply','repair'].includes(action)?action:button.dataset.operation??'install'});if(host===context&&context.current()){const plan=unwrap(result,'plan');store.state.pending_plan=plan;openPlan(plan);}}finally{setBusy(false);}
    }
    else if(action==='batch-all')await reviewBatch(batchItems().map(item=>item.id));
    else if(action==='batch-selected')await reviewBatch(batchItems().filter(item=>batchSelection.has(item.id)).map(item=>item.id));
    else if(action==='batch-updates')await reviewBatch(store.updates.filter(item=>item.download_ready&&!isGameExtension(store.catalog.find(row=>row.id===item.id))).map(item=>item.id));
    else if(action==='apply'){
      if(!ui.plan?.can_apply||isGameExtension(ui.plan)&&ui.plan.server_required)return;
      const launchClient=$('#ah-launch-client')?.checked===true;
      const result=await runMutation(()=>api('apply',{plan_id:ui.plan.id,...(launchClient?{launch_client:true}:{})}),'');
      if(result){
        $('#ah-plan-dialog').close();ui.plan=null;batchSelection.clear();
        const launch=result.client_launch;
        if(launch?.status==='failed')toast('All add-on changes were applied. The client could not be opened: '+launch.message,true);
        else toast(launch?.status==='launched'?'All add-on changes were applied. The game client opened once.':launch?.status==='already_running'?'All add-on changes were applied. The game client is already open.':'All add-on changes were applied. Open the game client once to load them.');
      }
    }
    else if(action==='sandbox'){
      const path=$('#ah-installation-path')?.value.trim();const result=await runMutation(()=>api('sandbox',path?{source_path:path}:{}),'Disposable sandbox connected. Your game remains unchanged.');
      if(result){store.map=null;store.maps=[];store.diagnostics=null;}
    }
    else if(action==='test-client'){
      const result=await runMutation(()=>api('test-client',{}),'Playable test copy created. Review add-on installation, then launch the copied client from its displayed folder.');
      if(result){store.map=null;store.maps=[];store.diagnostics=null;}
    }
    else if(action==='recover')await runMutation(()=>api('recover',{}),'Recovery finished. Check the installation status and activity record.');
    else if(action==='diagnostics')await loadDiagnostics();
    else if(action==='support-report'){
      const result=await api('support-report');const blob=new Blob([JSON.stringify(result.report,null,2)+'\n'],{type:'application/json'});
      const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='metin2-addon-support.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
    else if(action==='reload-atlas')await loadAtlas(true);
  }catch(error){if(!['apply','sandbox','recover'].includes(action))toast(error.message,true);}
});

document.addEventListener('submit',async event=>{
  if(!event.target.closest('.m2addons'))return;
  if(event.target.id==='ah-repository-form'){
    event.preventDefault();try{await startNetworkJob('repositories/add',{url:$('#ah-repository-url').value.trim(),channel:$('#ah-repository-channel').value});}catch(error){toast(error.message,true);}return;
  }
  if(event.target.id==='addon-settings-form'){
    event.preventDefault();if(ui.busy)return;setBusy(true);
    try{const item=store.catalog.find(row=>row.id===event.target.dataset.id)??store.state.installed.find(row=>row.id===event.target.dataset.id)??{};const record=installedRecord(item,store.state.installed);const settings=Object.fromEntries(settingFields(item,record).map(field=>{const input=event.target.elements.namedItem(field.key);return [field.key,parseSettingValue(field.type==='boolean'&&!field.spec.enum?input.checked:input.value,field.spec,field.label)];}));const result=await api('plan',{addon_id:event.target.dataset.id,action:'configure',settings});const plan=unwrap(result,'plan');store.state.pending_plan=plan;openPlan(plan);}catch(error){toast(error.message,true);}finally{setBusy(false);}return;
  }
  if(event.target.id!=='ah-connect-form')return;event.preventDefault();const path=$('#ah-installation-path').value.trim();
  if(!path){$('#ah-installation-path').focus();toast('Select the game client to connect it.',true);return;}
  try{await runMutation(()=>api('connect',{path}),'Client connected. Review add-on changes before applying.');store.map=null;store.maps=[];store.diagnostics=null;}catch{}
});

document.addEventListener('input',event=>{
  if(!event.target.closest('.m2addons'))return;
  if(event.target.id==='ah-catalog-search'){ui.query=event.target.value;$('#ah-catalog-results').innerHTML=catalogResults();}
  if(event.target.id==='ah-catalog-search')renderRemoteResults();
});
document.addEventListener('change',async event=>{
  if(!event.target.closest('.m2addons'))return;
  if(event.target.id==='ah-package-file'){
    const context=host,file=event.target.files?.[0];if(!file||ui.busy)return;
    if(!file.size||file.size>66*1024*1024){toast('Choose a nonempty add-on ZIP no larger than 66 MiB.',true);return;}
    try{
      const result=await runMutation(()=>context.importPackage(file),'Package imported. Review its installation before applying.');
      if(result&&host===context&&context.current())openDetails(result.imported);
    }catch{}return;
  }
  if(event.target.id==='ah-category-filter'){ui.category=event.target.value;$('#ah-catalog-results').innerHTML=catalogResults();}
  if(event.target.id==='ah-category-filter')renderRemoteResults();
  if(event.target.classList.contains('ah-repository-channel')){try{await runMutation(()=>api('repositories/configure',{repository_id:event.target.dataset.repository,channel:event.target.value}),'Release channel saved.');}catch{}}
  if(event.target.classList.contains('ah-release-version')){const card=event.target.closest('.remote-release-card');const button=card.querySelector('[data-action="review-download"]');const blocked=card.dataset.blocked==='true'||card.dataset.offline==='true'&&event.target.selectedOptions[0]?.dataset.cached!=='true';button.dataset.blocked=String(blocked);button.disabled=blocked||ui.busy||jobActive(store.state.network_job);}
  if(event.target.dataset.batchId){if(event.target.checked)batchSelection.add(event.target.dataset.batchId);else batchSelection.delete(event.target.dataset.batchId);render();}
  if(event.target.id==='ah-accept-source'){const button=$('#ah-download-confirm');button.dataset.blocked=String(!event.target.checked);button.disabled=ui.busy||jobActive(store.state.network_job)||!event.target.checked;}
  if(event.target.id==='ah-map-select'){ui.mapId=event.target.value;store.map=null;await loadAtlas();}
});

function ensureDialogs(){
  if(document.querySelector('.m2addons-dialog'))return;
  for(const [kind,title] of [['details','ah-details-title'],['plan','ah-plan-title'],['download','ah-download-title'],['update','ah-update-title']]){
    const dialog=document.createElement('dialog');dialog.className='m2addons m2addons-dialog';dialog.id='ah-'+kind+'-dialog';dialog.setAttribute('aria-labelledby',title);
    const content=document.createElement('div');content.id='ah-'+kind+'-content';dialog.append(content);document.body.append(dialog);
    dialog.addEventListener('click',event=>{if(event.target===dialog){const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dialog.close();}});
  }
}
ensureDialogs();

export function unmount(){
  ui.jobWatch++;
  for(const dialog of document.querySelectorAll('.m2addons-dialog'))dialog.close();
}

function renderRemoteResults(){ const root=$("#ah-release-results"); if(root)root.innerHTML=releaseCards(); }

document.addEventListener('input',event=>{
  if(event.target.id!=='ah-atlas-search'||ui.page!=='atlas')return;
  ui.atlasSearch=event.target.value;ui.atlasPinned='';
  const start=event.target.selectionStart;render();
  const replacement=$('#ah-atlas-search');replacement?.focus();replacement?.setSelectionRange(start,start);
});
document.addEventListener('pointerover',event=>{const row=event.target.closest?.('[data-atlas-creature]');if(row&&!row.contains(event.relatedTarget))focusAtlas(row.dataset.atlasCreature)});
document.addEventListener('pointerout',event=>{const row=event.target.closest?.('[data-atlas-creature]'),preview=event.target.closest?.('#atlas-inspection');if((row&&!row.contains(event.relatedTarget)||preview&&!preview.contains(event.relatedTarget))&&!event.relatedTarget?.closest?.('#atlas-inspection'))focusAtlas('')});
document.addEventListener('focusin',event=>{const row=event.target.closest?.('button[data-atlas-creature]');if(row)focusAtlas(row.dataset.atlasCreature)});
document.addEventListener('focusout',event=>{const row=event.target.closest?.('button[data-atlas-creature]');if((row&&!row.contains(event.relatedTarget)||event.target.closest?.('#atlas-inspection'))&&!event.relatedTarget?.closest?.('#atlas-inspection'))focusAtlas('')});
document.addEventListener('click',event=>{
  const filter=event.target.closest?.('[data-atlas-filter]');
  if(filter&&atlasTypes.some(([id])=>id===filter.dataset.atlasFilter)){ui.atlasFilter=filter.dataset.atlasFilter;ui.atlasPinned='';ui.atlasFocus='';ui.atlasHoverRequest++;render();host.root.querySelector(`[data-atlas-filter="${ui.atlasFilter}"]`)?.focus();return;}
  const row=event.target.closest?.('[data-atlas-creature]');if(row)focusAtlas(row.dataset.atlasCreature,true);
  if(event.target.closest?.('#atlas-clear-focus')){ui.atlasPinned='';focusAtlas('');}
});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&ui.page==='atlas'){ui.atlasPinned='';focusAtlas('')}});

document.addEventListener('scroll',event=>{if(ui.page==='atlas'&&ui.atlasFocus&&!event.target.closest?.('#atlas-inspection'))positionAtlasPreview(ui.atlasFocus)},true);
window.addEventListener('resize',()=>{if(ui.page==='atlas'&&ui.atlasFocus)positionAtlasPreview(ui.atlasFocus)});
document.addEventListener('toggle',event=>{if(ui.page==='atlas'&&ui.atlasFocus&&event.target.closest?.('#atlas-inspection'))positionAtlasPreview(ui.atlasFocus)},true);
