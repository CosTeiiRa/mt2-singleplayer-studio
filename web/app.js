'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = n => Number(n).toLocaleString('en-GB');
const S = {page:'overview', data:null, group:null, dropKind:'metin', dropSearch:'', selected:null, dirty:false, settings:null, files:null, file:null, fileSearch:'', fileCategory:'all', plan:null, picker:null, quest:{id:'studio_stone_hunter',title:'The Stone Hunter',intro:'Metin stones threaten the village. Will you help us?',npc:'9001',target:'8001',reward:'71084',kills:10,level:5,quantity:1,yang:10000,exp:5000}};
const titles = {overview:'Overview',economy:'Economy',drops:'Drop editor',quests:'Quests',crafting:'Crafting recipes',settings:'World settings',files:'Config files',history:'Change history',changes:'Drafts & changes',updates:'Update protection',addons:'Discover add-ons',installed:'Installed add-ons',atlas:'World atlas',addonsettings:'Add-on settings',activity:'Activity',repositories:'Repositories'};
let addonModule;
async function loadAddonTools(page,current){
  addonModule=await import('/addons.mjs');
  if(!current())return;
  await addonModule.mount({page,root:$('#content'),api,toast,current,openDrops:openAtlasDrops,openMapSource:openAtlasSource,
    importPackage:file=>api('/api/addons/packages/import',file,{'Content-Type':'application/zip','X-Addon-Filename':encodeURIComponent(file.name)})});
}
async function openAtlasDrops(id){
  if(!/^\d+$/.test(String(id))||!leaveOkay())return;
  const fresh=await api('/api/bootstrap');S.data.groups=fresh.groups;
  const group=fresh.groups.find(row=>row.id===String(id)&&row.source.startsWith('mob'));
  S.dropKind=group?.category??(S.mobMap[id]?.category==='metin'?'metin':'boss');
  S.dropSearch=group?'':String(id);S.openDropTarget=group;
  await navigate('drops');
}
async function openAtlasSource(path){
  if(!leaveOkay())return;
  await navigate('files/maps');
  if(S.page!=='files')return;
  S.file=await api('/api/file?id='+encodeURIComponent(path));
  renderFileDetail();renderFileList();
}
async function renderAddonOverview(){
  const navigation=S.navigation,root=$('#content');
  const section=document.createElement('section');section.className='panel work-catalog';section.id='addon-overview';
  section.innerHTML='<h2>Client add-ons &amp; world atlas</h2><p>Reading this world’s add-on target…</p>';root.append(section);
  try{
    const [stateResult,updatesResult]=await Promise.allSettled([api('/api/addons/state'),api('/api/addons/updates')]);
    if(stateResult.status==='rejected')throw stateResult.reason;
    const {state}=stateResult.value;
    const updateCount=updatesResult.status==='fulfilled'?(updatesResult.value.updates??[]).length:0;
    if(S.page!=='overview'||S.navigation!==navigation)return;
    const profile=state.installation;
    section.innerHTML=`<h2>Client add-ons &amp; world atlas</h2><p>${state.installed.length} installed in the selected ${profile?.kind==='sandbox'?'pack sandbox':profile?.kind==='test-client'?'playable test copy':profile?'game client':'world'}. Server changes and add-on installs have separate reviews. Updates are manual.</p><div class="work-actions">${updateCount?`<button class="button primary" data-go="installed">${updateCount} add-on ${updateCount===1?'update':'updates'} available · Read changelog</button>`:''}<button class="button" data-go="addons">Discover add-ons ↗</button><button class="button" data-go="atlas">World atlas ↗</button><button class="button" data-go="addonsettings">${profile?.kind==='sandbox'?'Manage sandbox':'Manage client'} ↗</button></div>`;
    $$('[data-go]',section).forEach(button=>button.addEventListener('click',()=>navigate(button.dataset.go)));
  }catch(error){if(S.page==='overview'&&S.navigation===navigation){section.innerHTML='<h2>Client add-ons &amp; world atlas</h2><p></p>';section.querySelector('p').textContent=error.message;}}
}
async function api(path, body, uploadHeaders){
  const headers=body===undefined?{}:{...(uploadHeaders??{'Content-Type':'application/json'}),'X-Studio-Token':S.data.token};
  if(typeof WUI!=='undefined'&&WUI.activeSet)headers['X-Studio-Changeset']=WUI.activeSet;
  const response = await fetch(path, body === undefined ? {headers} : {method:'POST',headers,body:uploadHeaders?body:JSON.stringify(body)});
  const data = await response.json();
  if(!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}
let toastTimer;
function toast(message, error=false){const node=$('#toast');node.textContent=message;node.classList.toggle('error',error);node.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.hidden=true,error?11000:6500)}
async function attempt(fn){try{return await fn()}catch(error){toast(error.message,true)}}
function head(eyebrow,title,description,action=''){return `<div class="page-head"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${description}</p></div>${action}</div>`}
function iconPlaceholder(id){return `<span class="item-icon item-placeholder" aria-hidden="true" title="${esc(/^\d+$/.test(String(id))?'No local icon available for item #'+id:'No item icon available')}">◇</span>`}
function icon(id){return /^\d{1,10}$/.test(String(id)) ? `<img class="item-icon" src="/icons/${encodeURIComponent(id)}" alt="" loading="lazy" data-icon-id="${esc(id)}">` : iconPlaceholder(id)}
function bindImages(root=document){$$('img.item-icon',root).forEach(img=>{
  if(img.dataset.iconBound)return;img.dataset.iconBound='1';
  const fallback=()=>{const el=document.createElement('span');el.className='item-icon item-placeholder';el.setAttribute('aria-hidden','true');el.title='No local icon available for item #'+(img.dataset.iconId||'unknown');el.textContent='◇';img.replaceWith(el)};
  img.addEventListener('error',fallback,{once:true});
  if(img.complete&&img.naturalWidth===0)fallback();
})}
function pool(id){return String(id).startsWith('s')?S.data.groups.find(g=>g.source.startsWith('chest')&&g.id===String(id).slice(1)):null}
function name(kind,id){const p=kind==='item'?pool(id):null;return p?p.name+' · shared pool':(kind==='item'?S.itemMap[id]:S.mobMap[id])?.name || `#${id}`}
function itemHelpAttrs(id){return `data-help-item="${esc(id)}"`}
function bindItemUsageLinks(root){
  $$('.item-button[data-help-item],#quest-reward',root).forEach(anchor=>{
    const id=anchor.dataset.helpItem;if(!id||id.startsWith('s'))return;
    let button=anchor.nextElementSibling;
    if(!button?.matches('[data-inspect-item]')){button=document.createElement('button');button.className='subtle-link usage-link';anchor.after(button)}
    button.dataset.inspectItem=id;button.textContent='Where used ↗';button.setAttribute('aria-label',`Where is ${name('item',id)} used?`);
  });
}
let usageRequest=0;
function browseItems(){
  hideItemHelp();
  if($('#item-usage').open)$('#item-usage').close();
  pick('item',e=>!e.id.startsWith('s'),e=>showItemUsage(e.id),{inspectOnly:true});
}
async function showItemUsage(id){
  hideItemHelp();S.usageId=id;
  const request=++usageRequest,dialog=$('#item-usage');
  $('#usage-title').textContent='Where this item is used';
  $('#usage-body').innerHTML='<div class="loading">Scanning saved drops, recipes and item references…</div>';
  $('#usage-refresh').disabled=true;
  if(!dialog.open)dialog.showModal();
  try{
    const data=await api('/api/item-usage?id='+encodeURIComponent(id));
    if(request!==usageRequest||!dialog.open)return;
    S.usageData=data;renderItemUsage(data);
  }catch(error){
    if(request===usageRequest&&dialog.open){$('#usage-body').innerHTML='<div class="empty"><strong>Could not read item references</strong><p id="usage-error"></p></div>';$('#usage-error').textContent=error.message}
  }finally{if(request===usageRequest)$('#usage-refresh').disabled=false}
}
function renderItemUsage(data){
  const labels={drops:['Drops in','Monster, boss and Metin groups, including shared pools.'],chests:['Found in chests','Saved chest reward groups.'],pools:['Reward pools & other tables','Shared or unclassified reward tables. These are not all physical chests or confirmed obtainable sources.'],crafted:['Can be crafted by','Recipes that produce this exact item ID.'],ingredients:['Used to craft','Ingredients and recipe/progress requirements.'],shops:['Sold by NPCs','Database seed shop inventories; current shops may differ.'],refining:['Used in equipment upgrades','Database seed refinement relationships.'],files:['Other file references','Literal ID matches; these do not confirm an item effect or an active quest.']};
  const total=Object.values(data.counts).reduce((a,b)=>a+b,0),actions=[];
  $('#usage-title').textContent=data.item.name;
  $('#usage-body').innerHTML=`<div class="usage-item">${icon(data.item.id)}<div><strong>${esc(data.item.name)}</strong><small>#${esc(data.item.id)} · ${esc(data.item.catalogLabel||'Item ID lookup')}</small></div><span class="pill gold">${fmt(total)} references</span></div>
    <div class="usage-stats">${[['drops','Drop groups'],['chests','Chests'],['crafted','Crafting sources'],['ingredients','Crafting uses']].map(([key,label])=>`<button data-usage-jump="${key}" ${data.counts[key]?'':'disabled'}><strong>${fmt(data.counts[key])}</strong><small>${label} ↗</small></button>`).join('')}</div>
    ${S.dirty?'<p class="notice">Your unsaved draft is excluded. You can inspect references now; your draft is preserved when opening another editor.</p>':''}
    <div class="usage-sections">${Object.entries(labels).filter(([key])=>data.sections[key].length).map(([key,[title,hint]])=>`<details class="usage-section" data-usage-kind="${key}" ${(['crafted','ingredients'].includes(key)||(['drops','chests'].includes(key)&&data.sections[key].length<=4))?'open':''}><summary>${title}<span>${fmt(data.sections[key].length)}</span></summary><p class="usage-section-hint">${hint}</p><div class="usage-rows">${data.sections[key].map((row,i)=>`<article class="usage-row" ${i>=4?'hidden':''} data-usage-section="${key}"><div class="usage-row-head"><strong>${esc(row.name)}</strong>${row.seed?'<span class="pill">DATABASE SEED</span>':''}</div><p>${esc(row.summary)}</p>${row.details.length?`<ul>${row.details.map(detail=>`<li>${esc(detail)}</li>`).join('')}</ul>`:''}<div class="usage-row-foot"><code>${esc(row.file)}${row.line?':'+row.line:''}</code>${row.actions.map(action=>{const index=actions.push(action)-1;return `<button class="button small ghost" data-usage-action="${index}" >${esc(action.label)} ↗</button>`}).join('')}</div></article>`).join('')}</div>${data.sections[key].length>4?`<button class="button small usage-show-more" data-usage-more="${key}">Show all ${fmt(data.sections[key].length)} references</button>`:''}</details>`).join('')||'<div class="empty"><strong>No references found in the scanned sources.</strong><p>This does not prove the item is unused in the running game. Check the coverage below.</p></div>'}</div>
    <details class="usage-coverage"><summary>Coverage & limits · ${fmt(data.coverage.files)} saved files</summary><ul>${data.coverage.notes.map(note=>`<li>${esc(note)}</li>`).join('')}${data.coverage.warnings.map(note=>`<li>${esc(note)}</li>`).join('')}</ul></details>`;
  $$('[data-usage-action]',$('#usage-body')).forEach(button=>button.addEventListener('click',()=>openUsageSource(actions[Number(button.dataset.usageAction)])));
  $$('[data-usage-more]',$('#usage-body')).forEach(button=>button.addEventListener('click',()=>{$$(`[data-usage-section="${button.dataset.usageMore}"]`,$('#usage-body')).forEach(row=>row.hidden=false);button.hidden=true}));
  $$('[data-usage-jump]',$('#usage-body')).forEach(button=>button.addEventListener('click',()=>{const section=$(`[data-usage-kind="${button.dataset.usageJump}"]`,$('#usage-body'));section.open=true;section.scrollIntoView({block:'start'})}));
  bindImages($('#usage-body'));
}
async function openUsageSource(action){
  if(!leaveOkay())return;
  hideItemHelp();$('#item-usage').close();$('#picker').close();
  await attempt(async()=>{
    if(action.kind==='drop'){
      const groups=(await api('/api/bootstrap')).groups;S.data.groups=groups;
      const group=groups.find(g=>g.source===action.source&&g.key===action.key);
      if(!group)throw new Error('This group changed or was removed. Refresh the item references.');
      S.dropKind=group.source.startsWith('chest')?'chest':group.category;S.dropSearch='';S.openDropTarget=group;
      await navigate('drops');
    }else if(action.kind==='recipe'){
      await navigate('crafting');
      const recipe=S.recipes.find(r=>r.source===action.source&&r.index===action.index);
      if(!recipe||recipe.hash!==action.hash)throw new Error('This recipe file changed. Refresh the item references before opening it.');
      S.recipe=structuredClone(recipe);renderRecipeDetail();renderRecipeList();
    }else if(action.kind==='file'){
      await navigate('files/all');S.file=await api('/api/file?id='+encodeURIComponent(action.file));renderFileDetail();renderFileList();
      const input=$('#file-text'),line=Math.max(1,Number(action.line)||1),start=S.file.text.split('\n').slice(0,line-1).reduce((n,text)=>n+text.length+1,0);
      input.focus();input.setSelectionRange(start,S.file.text.indexOf('\n',start)===-1?S.file.text.length:S.file.text.indexOf('\n',start));input.scrollTop=(line-1)*parseFloat(getComputedStyle(input).lineHeight);
    }
  });
}
let helpAnchor=null,helpHideTimer,helpUsageTimer,helpRequest=0;
function hideItemHelp(){
  clearTimeout(helpHideTimer);
  clearTimeout(helpUsageTimer);helpRequest++;
  const tooltip=$('#item-tooltip');
  if(tooltip.matches(':popover-open'))tooltip.hidePopover();
  tooltip.hidden=true;
  if(helpAnchor){
    const ids=(helpAnchor.getAttribute('aria-describedby')||'').split(/\s+/).filter(id=>id&&id!=='item-tooltip');
    if(ids.length)helpAnchor.setAttribute('aria-describedby',ids.join(' '));else helpAnchor.removeAttribute('aria-describedby');
  }
  helpAnchor=null;
}
function positionItemHelp(){
  if(!helpAnchor?.isConnected)return hideItemHelp();
  const tooltip=$('#item-tooltip'),rect=helpAnchor.getBoundingClientRect(),gap=10,edge=12;
  const viewportWidth=document.documentElement.clientWidth,viewportHeight=window.innerHeight;
  tooltip.style.maxHeight=Math.min(510,viewportHeight-edge*2)+'px';
  let box=tooltip.getBoundingClientRect();
  let left=rect.right+gap,top=rect.top;
  if(left+box.width>viewportWidth-edge)left=rect.left-box.width-gap;
  if(left<edge){
    left=rect.left;
    const below=viewportHeight-edge-rect.bottom-gap,above=rect.top-edge-gap,placeBelow=below>=box.height||below>=above;
    tooltip.style.maxHeight=Math.max(80,Math.min(510,placeBelow?below:above))+'px';
    box=tooltip.getBoundingClientRect();top=placeBelow?rect.bottom+gap:rect.top-box.height-gap;
  }
  tooltip.style.left=Math.max(edge,Math.min(left,viewportWidth-box.width-edge))+'px';
  tooltip.style.top=Math.max(edge,Math.min(top,viewportHeight-box.height-edge))+'px';
}
function showItemHelp(anchor){
  if(typeof hideQuestHelp==='function')hideQuestHelp();
  clearTimeout(helpHideTimer);
  if(helpAnchor===anchor&&!$('#item-tooltip').hidden)return positionItemHelp();
  hideItemHelp();helpAnchor=anchor;
  const id=anchor.dataset.helpItem,p=pool(id),item=S.itemMap?.[id]||{id,name:p?p.name+' · shared pool':`Unknown item #${id}`,catalogLabel:p?'Shared reward pool':'Unknown item',description:p?{text:'A shared reward table, not a physical item. Targets that reference this pool draw rewards from its configured contents. Editing the pool affects every target that uses it.',source:'definition',facts:[]}:null};
  const detail=StudioCatalog.help(item),tooltip=$('#item-tooltip');
  const owner=anchor.closest('dialog')||document.body;
  if(tooltip.parentElement!==owner)owner.append(tooltip);
  tooltip.innerHTML=`<div class="item-help-head">${icon(id)}<div><strong>${esc(item.name)}</strong><small>#${esc(id)} · ${esc(StudioCatalog.label(item))}</small></div></div><div id="item-help-usage" class="item-help-usage" role="status">Checking drop sources…</div><p class="item-help-text">${esc(detail.text)}</p>${detail.facts.length?`<dl class="item-help-facts">${detail.facts.map(([key,value])=>`<div><dt>${esc(key)}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl>`:''}${detail.note?`<p class="item-help-note">${esc(detail.note)}</p>`:''}<div class="item-help-source">${esc(detail.source)}</div>`;
  const ids=(anchor.getAttribute('aria-describedby')||'').split(/\s+/).filter(Boolean);ids.push('item-tooltip');anchor.setAttribute('aria-describedby',[...new Set(ids)].join(' '));
  tooltip.hidden=false;tooltip.showPopover();positionItemHelp();bindImages(tooltip);
  const request=helpRequest;
  helpUsageTimer=setTimeout(()=>loadHoverUsage(id,anchor,request),140);
}
async function loadHoverUsage(id,anchor,request){
  try{
    const data=await api('/api/item-drop-summary?id='+encodeURIComponent(id));
    if(request!==helpRequest||helpAnchor!==anchor)return;
    const count=data.counts.metins,others=[['bosses','boss','bosses'],['monsters','monster','monsters'],['chests','chest','chests'],['pools','reward table','reward tables'],['other','other target','other targets']].filter(([key])=>data.counts[key]).map(([key,one,many])=>`${fmt(data.counts[key])} ${data.counts[key]===1?one:many}`);
    const current=S.page==='drops'&&S.group?.category==='metin'&&data.metins.some(metin=>metin.id===S.group.id);
    $('#item-help-usage').innerHTML=`<strong>Configured in ${fmt(count)} ${count===1?'Metin':'Metins'}</strong>${data.metins.length?`<ul>${data.metins.slice(0,4).map(metin=>`<li>${esc(metin.name)} <span>· Lv. ${esc(metin.level??'?')} · #${esc(metin.id)}</span></li>`).join('')}</ul>${count>4?`<div class="item-help-more">+ ${fmt(count-4)} more · see Where used ↗</div>`:''}`:''}${others.length?`<div class="item-help-other">Also in ${esc(others.join(' · '))}</div>`:''}${current?'<div class="item-help-current">Includes this Metin.</div>':''}<small>Saved references, including shared pools. Unsaved edits excluded.${data.zeroParameter?' Some references have zero parameters.':''}</small>`;
  }catch(error){
    if(request!==helpRequest||helpAnchor!==anchor)return;
    $('#item-help-usage').textContent='Drop usage unavailable. Try hovering again or open Where used ↗.';
  }
  positionItemHelp();
}
function scheduleHideItemHelp(){
  clearTimeout(helpHideTimer);helpHideTimer=setTimeout(()=>{
    const tooltip=$('#item-tooltip');
    if(!tooltip.matches(':hover')&&!helpAnchor?.matches(':hover')&&document.activeElement!==helpAnchor)hideItemHelp();
  },130);
}
function dirty(value=true){S.dirty=value;$('#discard-draft').hidden=!value;const el=$('#dirty-label');if(el){el.textContent=value?'Draft · game files unchanged':'Saved file · no changes';el.classList.toggle('unsaved',value)}if(value&&typeof workspaceStash==='function')workspaceStash()}
function leaveOkay(){return !S.dirty||workspaceStash()}
async function navigate(route,{reload=false}={}){
  const {page,section,route:canonical}=StudioNavigation.parse(route);
  if(!S.data || !titles[page] || !leaveOkay()) return;
  const navigation=(S.navigation||0)+1;S.navigation=navigation;
  addonModule?.unmount();
  await workspaceFlush();
  if(S.navigation!==navigation)return;
  const current=()=>S.navigation===navigation;
  hideItemHelp();
  if(typeof hideQuestHelp==='function')hideQuestHelp();
  const keepSettings=!reload&&page==='settings'&&S.page==='settings'&&S.settings&&S.settingsScope===(WUI.activeSet||'direct');
  if(S.page!==page||S.section!==section){S.settingSearch='';S.fileSearch='';S.fileCategory='all';S.mapFolder='all'}
  S.page=page;S.section=section;S.route=canonical;S.group=null;S.file=null;
  if(!keepSettings)dirty(false);
  $$('#content').forEach(n=>n.innerHTML='<div class="loading">Reading installed files…</div>');
  syncSidebar();
  if(location.hash.slice(1)!==canonical)location.hash=canonical;
  await attempt(async()=>{
    if(page==='overview'){await workspaceRefresh();if(current())renderOverview()}
    if(page==='economy') await loadEconomy();
    if(page==='drops') await renderDrops();
    if(page==='quests') await renderQuests();
    if(page==='crafting'){const data=await api('/api/crafting');if(!current())return;S.recipes=data.recipes;S.craftingAccess=data.access;S.recipe=null;S.recipeSearch='';renderCrafting()}
    if(page==='settings'){if(!keepSettings){const settings=await api('/api/settings');if(!current())return;S.settings=settings;S.settingsScope=WUI.activeSet||'direct'}renderSettings()}
    if(page==='files'){const files=await api('/api/files');if(!current())return;S.files=files;renderFiles()}
    if(page==='history'){const history=await api('/api/history');if(current())renderHistory(history)}
    if(page==='changes') await renderChanges();
    if(page==='updates') await renderUpdates();
    if(['addons','installed','atlas','addonsettings','activity','repositories'].includes(page))await loadAddonTools(page,current);
  });
}
function renderOverview(){
  if(typeof renderWorkspaceOverview==='function')return renderWorkspaceOverview();
  const c=S.data.counts;
  $('#content').innerHTML=head('YOUR WORLD, YOUR RULES','Welcome to your world.','A little less file editing. A lot more adventure.', '<span class="head-note"><span class="world-dot"></span>Connected to your installation</span>')+
    `<div class="stats">${[[c.items,'Searchable items','Weapons, materials & rewards','◇'],[c.mobs,'Monsters & NPCs','Metins, bosses & villagers','♧'],[c.settings,'World settings','From your installed configuration','☷'],[c.files,'Config files','Quests, maps, tables & more','▤']].map(([n,t,s,i])=>`<div class="stat"><div class="stat-label">${t}<span>${i}</span></div><strong>${fmt(n)}</strong><small>${s}</small></div>`).join('')}</div>
    <div class="section-label"><h3>Make it your own</h3><span class="muted small-text">Start with what you want to change</span></div>
    <div class="quick-grid"><article class="feature-card"><div class="feature-symbol">◇</div><div class="mini-label">LOOT & REWARDS</div><h2>Better drops. Your way.</h2><p>Pick a Metin, find an item by name, and tune its rewards. No memorizing item IDs.</p><button class="button primary" data-go="drops">Open drop editor <span>↗</span></button></article><article class="feature-card secondary"><div class="feature-symbol">▤</div><div class="mini-label">STORIES & ADVENTURES</div><h2>A new reason to explore.</h2><p>Give an NPC a mission, choose a hunt, and make the reward worth the journey.</p><button class="button" data-go="quests">Create a quest <span>↗</span></button></article></div>
    <div class="overview-lower"><div class="panel"><div class="panel-header"><h3>Your editing toolkit</h3><span>Built around this installation</span></div>${[['☷','World & progression','Difficulty, waits, extra drops and bot population','Forms','settings'],['▧','Game configuration','Crafting, shops, fishing, spawns, skills and maps','File catalog','files'],['↶','Every change has a way back','Review diffs, save backups, restore earlier files','History','history']].map(([i,t,d,p,page])=>`<button class="capability file-entry" data-go="${page}"><span class="glyph">${i}</span><span><strong>${t}</strong><small>${d}</small></span><span class="pill">${p}</span></button>`).join('')}</div><div class="panel"><div class="panel-header"><h3>From idea to in game</h3><span>THREE SIMPLE STEPS</span></div><div class="steps">${[['Make your changes','Search the real item catalog and edit the files your server uses.'],['Review & save','Check exactly what changes. Studio backs up the originals.'],['Apply to server','Build the updated game files, compile quests, and restart.']].map(([t,d],i)=>`<div class="step"><span>${i+1}</span><div><strong>${t}</strong><p>${d}</p></div></div>`).join('')}</div></div></div>
    <p class="notice info">Your server files stay on this computer. Catalog names come from the installed package; database changes made elsewhere may differ. Database-only item stats, shop prices and refine tables are available in the package’s existing admin panel.</p>`;
  bindNavigation();
}
function bindNavigation(){$$('[data-go]',$('#content')).forEach(n=>n.addEventListener('click',()=>navigate(n.dataset.go)))}
function renderDrops(){
  $('#content').innerHTML=head('LOOT & REWARDS','Drop editor','Choose the target. Choose the loot. Shape the adventure.','<button class="button" id="new-group">＋ New drop group</button>')+
    `<div class="toolbar"><div class="tabs" id="drop-tabs">${[['metin','Metin stones'],['boss','Bosses'],['monster','Monsters'],['chest','Chests']].map(([k,v])=>`<button data-kind="${k}" class="${S.dropKind===k?'selected':''}">${v}</button>`).join('')}</div><div class="searchbox"><span>⌕</span><input id="drop-search" value="${esc(S.dropSearch)}" placeholder="Search targets by name or ID…" aria-label="Search drop targets"><kbd>⌕</kbd></div></div><div class="editor-layout"><div class="panel"><div class="list-head" id="group-count"></div><div id="group-list" class="entity-list"></div></div><div class="panel" id="drop-detail"><div class="empty"><div class="empty-symbol">◇</div>Select a target to explore its rewards.</div></div></div><p class="small-text muted">Names and IDs come from your installed package. Probability rules match the package’s drop parser. Some loot also comes from quests, common tables, and world settings.</p>`;
  $('#drop-search').addEventListener('input',e=>{S.dropSearch=e.target.value;renderGroupList()});
  $$('#drop-tabs button').forEach(n=>n.addEventListener('click',()=>{if(!leaveOkay())return;dirty(false);S.dropKind=n.dataset.kind;S.selected=null;S.group=null;renderDrops()}));
  $('#new-group').addEventListener('click',()=>{if(leaveOkay())newGroup()});
  renderGroupList();
  const first=S.openDropTarget||filteredGroups()[0];S.openDropTarget=null;
  if(first)return loadGroup(first);
}
function filteredGroups(){return S.data.groups.filter(g=>(S.dropKind==='chest'?g.source.startsWith('chest'):g.source.startsWith('mob')&&g.category===S.dropKind)&&`${g.name} ${g.id} ${g.key}`.toLowerCase().includes(S.dropSearch.toLowerCase())).sort((a,b)=>Number(a.level||0)-Number(b.level||0)||Number(a.id)-Number(b.id))}
function renderGroupList(){
  const groups=filteredGroups();$('#group-count').textContent=`${fmt(groups.length)} DROP GROUPS`;
  $('#group-list').innerHTML=groups.length?groups.map((g,i)=>`<button class="entity ${S.selected===g.source+'|'+g.key?'selected':''}" data-index="${i}"><span class="entity-glyph">${S.dropKind==='chest'?'▣':'◇'}</span><span><strong>${esc(g.name)}</strong><small>${g.level?`Lv. ${g.level} · `:''}#${esc(g.id)} · ${esc(g.type)}${g.source==='mob-m3'?' · add-on':''}</small></span><span class="pill">${g.count}</span></button>`).join(''):'<div class="no-results">No matching drop groups.<br>Create a group for another target.</div>';
  $$('.entity',$('#group-list')).forEach(n=>n.addEventListener('click',()=>{if(leaveOkay())loadGroup(groups[Number(n.dataset.index)])}));
}
async function loadGroup(g){await workspaceFlush();await attempt(async()=>{S.group=await api(`/api/group?source=${encodeURIComponent(g.source)}&key=${encodeURIComponent(g.key)}`);S.selected=g.source+'|'+g.key;dirty(false);renderGroupList();renderDropDetail();await workspaceRestore()})}
function isWeighted(){return S.group.type==='kill'||(S.group.source.startsWith('chest')&&!['pct'].includes(S.group.type.toLowerCase()))}
function renderDropDetail(){
  const g=S.group,weighted=isWeighted(),chest=g.source.startsWith('chest');
  $('#drop-detail').innerHTML=`<div class="drop-head"><div class="drop-symbol">${chest?'▣':'◇'}</div><div><h2>${esc(g.name)}</h2><small>${g.level?`Level ${g.level} · `:''}${chest?'Chest':'Monster'} #${esc(g.id)} · ${esc(g.type)}</small></div><span class="pill gold">${g.new?'NEW GROUP':'INSTALLED FILE'}</span></div><div class="drop-description">${weighted?'Weighted rewards: a larger weight makes a reward more likely within this group.':'Each line has a configured base parameter; values above 100 can be valid. Multiple items can drop.'} ${g.type==='kill'?'The kill-drop denominator controls how often this group rolls.':''} Global rates and level differences may affect the final result.</div>${g.type==='kill'||g.type==='limit'?`<div class="group-fields"><label for="group-extra">${g.type==='kill'?'Kill-drop denominator':'Level limit'}</label><input id="group-extra" type="number" min="1" value="${esc(g.fields[g.type==='kill'?'kill_drop':'level_limit'])}"></div>`:''}${g.blocks>1?`<p class="notice">This target spans ${g.blocks} blocks. Saving consolidates this group while keeping its rewards.</p>`:''}${g.skipped?'<p class="notice">This group has numbered lines the engine skips. Saving rewrites consecutive indices; review the full diff carefully.</p>':''}<div class="table-wrap"><table><thead><tr><th>#</th><th>REWARD ITEM</th><th>COUNT</th><th>${weighted?'WEIGHT':'BASE PARAMETER'}</th><th>${weighted?'SHARE':'BASE'}</th><th></th></tr></thead><tbody id="drop-rows"></tbody></table></div><div class="drop-bottom"><button class="button ghost small" id="add-item">＋ Add reward</button><span class="muted small-text" id="entry-count"></span></div><div class="drop-save"><span id="dirty-label">Saved file · no changes</span><button class="button primary" id="review-drop">Review changes <span>→</span></button></div><div class="panel-body"><div class="path">${esc(g.file)}</div></div>`;
  renderDropRows();
  $('#add-item').addEventListener('click',()=>pick('item',null,item=>{g.entries.push({item:item.id,name:item.name,count:'1',prob:weighted?'1':'1',rare:''});dirty();renderDropRows()}));
  $('#group-extra')?.addEventListener('input',e=>{g.fields[g.type==='kill'?'kill_drop':'level_limit']=e.target.value;dirty()});
  $('#review-drop').addEventListener('click',()=>preview('/api/preview/drop',g));
  dirty(g.new||S.dirty);
}
function renderDropRows(){
  const g=S.group;
  $('#drop-rows').innerHTML=g.entries.map((e,i)=>`<tr><td>${String(i+1).padStart(2,'0')}</td><td><button class="item-button" ${itemHelpAttrs(e.item)} data-item="${i}" title="Choose a different reward">${icon(e.item)}<span><strong>${esc(name('item',e.item))}</strong><small>#${esc(e.item)}${e.rare?` · rare ${esc(e.rare)}`:''}</small></span></button>${pool(e.item)?`<button class="subtle-link pool-link" data-pool="${esc(e.item)}">Edit pool contents ↗</button>`:''}</td><td><input type="number" min="1" max="200" step="1" value="${esc(e.count)}" data-field="count" data-row="${i}" aria-label="Count for reward ${i+1}"></td><td><input type="number" min="0" step="${isWeighted()?'1':'0.01'}" value="${esc(e.prob)}" data-field="prob" data-row="${i}" aria-label="${isWeighted()?'Weight':'Base parameter'} for reward ${i+1}"></td><td><span class="chance" data-chance="${i}"></span></td><td><button class="icon-button remove-row" data-remove="${i}" aria-label="Remove reward ${i+1}">×</button></td></tr>`).join('');
  $$('[data-item]',$('#drop-rows')).forEach(n=>n.addEventListener('click',()=>pick('item',null,item=>{const e=g.entries[Number(n.dataset.item)];e.item=item.id;e.name=item.name;dirty();renderDropRows()})));
  $$('[data-field]',$('#drop-rows')).forEach(n=>n.addEventListener('input',()=>{g.entries[Number(n.dataset.row)][n.dataset.field]=n.value;dirty();updateChances()}));
  $$('[data-remove]',$('#drop-rows')).forEach(n=>n.addEventListener('click',()=>{g.entries.splice(Number(n.dataset.remove),1);dirty();renderDropRows()}));
  $$('[data-pool]').forEach(n=>n.addEventListener('click',()=>{if(leaveOkay()){dirty(false);loadGroup(pool(n.dataset.pool))}}));
  $('#entry-count').textContent=`${g.entries.length} rewards in this group`;
  updateChances();bindImages($('#drop-rows'));bindItemUsageLinks($('#drop-rows'));
}
function updateChances(){const total=S.group.entries.reduce((n,e)=>n+(Number(e.prob)||0),0);$$('[data-chance]').forEach(n=>{const p=Number(S.group.entries[Number(n.dataset.chance)].prob)||0;n.textContent=`${(isWeighted()?total?p/total*100:0:p).toLocaleString('en-GB',{maximumFractionDigits:2})}%`})}
function newGroup(){
  dirty(false);
  $('#drop-detail').innerHTML=`<div class="panel-header"><h2>A new drop group</h2><span>BASE PERCENTAGE DROPS</span></div><div class="new-form"><p>Choose a target that does not already have this drop group.</p><div class="form-grid"><div class="field full"><label>Target type</label><select id="new-kind"><option value="mob">Monster, Metin or boss</option><option value="chest">Chest (weighted rewards)</option></select></div><div class="field full"><label>Target</label><button class="button" id="new-target">Search the installed catalog…</button></div></div><p class="notice info">Existing targets can have several drop group types. A new monster group uses independent percentages; a new chest uses relative weights.</p></div>`;
  $('#new-target').addEventListener('click',()=>{const chest=$('#new-kind').value==='chest';pick(chest?'item':'mob',chest?e=>!e.id.startsWith('s'):m=>m.category!=='npc',async entity=>{await attempt(async()=>{const source=chest?'chest-base':'mob-base';const info=await api('/api/drop-source?source='+source);const key=chest?entity.id:entity.id+' drop';if(S.data.groups.some(g=>g.key===key&&g.source.startsWith(chest?'chest':'mob')))throw new Error('This target already has that group. Open it in the list.');S.group={source,key,id:entity.id,name:entity.name,level:entity.level,type:chest?'weighted':'drop',fields:chest?{vnum:entity.id,type:''}:{mob:entity.id,type:'drop'},entries:[],file:info.file,hash:info.hash,new:true};S.selected=null;dirty();renderDropDetail()})})});
}
function pick(kind,filter,callback,options={}){
  S.catalogFilters ||= {};
  const filters=S.catalogFilters[kind] ||= {category:'all',function:'all',sort:'id'};
  const pools=kind==='item'&&S.page==='drops'?[...new Map(S.data.groups.filter(g=>g.source.startsWith('chest')).map(g=>['s'+g.id,{id:'s'+g.id,name:g.name+' · shared pool',category:'reward pool',keywords:g.key,catalogGroups:['pools'],catalogKind:'reward-pool',catalogLabel:'Shared reward pool'}])).values()]:[];
  const items=(kind==='item'?[...S.data.items,...pools]:S.data.mobs).filter(e=>!filter||filter(e));
  if(!items.some(e=>StudioCatalog.groupKeys(e,kind).includes(filters.category)))filters.category='all';
  const available=StudioCatalog.query(items,{kind,category:filters.category});
  if(!available.functions.some(e=>e.id===filters.function))filters.function='all';
  S.picker={kind,callback,items,filters,limit:100,inspectOnly:!!options.inspectOnly};
  $('#picker-title').textContent=options.inspectOnly?'Explore an item':kind==='item'?'Choose an item':'Choose a monster or NPC';
  $('.picker-hint').textContent=options.inspectOnly?'Select an item to see drops, crafting and other references. Read only.':kind==='item'?'Browse by category or function. Names and IDs are optional.':'Browse by type or search a name or ID.';
  $('#picker-search').value='';$('#picker-sort').value=filters.sort;
  $('#picker-function-field').hidden=kind!=='item';
  $('#picker').showModal();renderPicker();setTimeout(()=>$('#picker-search').focus(),40);
}
function renderPicker(){
  hideItemHelp();
  const {kind,items,filters,limit}=S.picker;
  const {results,counts,functions}=StudioCatalog.query(items,{kind,...filters,search:$('#picker-search').value});
  const categories=kind==='item'?StudioCatalog.groups:StudioCatalog.mobGroups;
  $('#picker-category').innerHTML=categories.filter(([key])=>key==='all'||key===filters.category||items.some(e=>StudioCatalog.groupKeys(e,kind).includes(key))).map(([key,label])=>`<option value="${key}" ${key===filters.category?'selected':''}>${esc(label)} (${fmt(counts[key]||0)})</option>`).join('');
  $('#picker-function').innerHTML='<option value="all">All functions / types</option>'+functions.map(e=>`<option value="${esc(e.id)}" ${e.id===filters.function?'selected':''}>${esc(e.name)} (${fmt(e.count)})</option>`).join('');
  $('#picker-function').disabled=functions.length<2&&filters.function==='all';
  const quick=kind==='item'?['all','bonus','scrolls','potions']:['all','metin','boss','monster','npc'];
  $('#picker-quick').innerHTML=quick.filter(key=>key==='all'||items.some(e=>StudioCatalog.groupKeys(e,kind).includes(key))).map(key=>`<button class="filter-chip" data-category="${key}" aria-pressed="${filters.category===key}">${key==='all'?'All':esc(categories.find(([id])=>id===key)[1])}<span>${fmt(counts[key]||0)}</span></button>`).join('');
  $$('[data-category]',$('#picker-quick')).forEach(n=>n.addEventListener('click',()=>setPickerCategory(n.dataset.category)));
  const visible=results.slice(0,limit);
  $('#picker-results').innerHTML=visible.length?visible.map((e,i)=>`<button class="pick-result" data-pick="${i}">${kind==='item'?icon(e.id):'<span class="entity-glyph" aria-hidden="true">◇</span>'}<span class="pick-name"><strong>${esc(e.name)}</strong><small>#${esc(e.id)}${(e.requiredLevel??e.level)?` · ${kind==='item'?'Requires level':'Level'} ${e.requiredLevel??e.level}`:''}</small></span><span class="pill">${esc(StudioCatalog.label(e,kind))}</span></button>`).join(''):'<div class="empty"><strong>No matching results</strong><p>Try a broader category, another function, or fewer search words.</p><button class="button small" id="picker-empty-reset">Clear filters</button></div>';
  $('#picker-count').textContent=`${fmt(results.length)} ${results.length===1?'match':'matches'}`;
  $('#picker-shown').textContent=results.length?`Showing ${fmt(visible.length)} of ${fmt(results.length)} · ${S.picker.inspectOnly?'Select an item to inspect it':'Select a result to use it; ↗ shows its references'}`:'No results to display';
  $('#picker-more').hidden=visible.length>=results.length;
  $('#picker-more').textContent=`Show ${Math.min(100,results.length-visible.length)} more`;
  $('#picker-reset').hidden=filters.category==='all'&&filters.function==='all'&&!$('#picker-search').value;
  $$('[data-pick]',$('#picker-results')).forEach(n=>{
    if(kind==='item'){
      const item=visible[Number(n.dataset.pick)];n.dataset.helpItem=item.id;
      if(!item.id.startsWith('s')&&!S.picker.inspectOnly){
        const row=document.createElement('div');row.className='pick-row';n.before(row);row.append(n);
        const inspect=document.createElement('button');inspect.className='pick-inspect';inspect.dataset.inspectItem=item.id;inspect.textContent='↗';inspect.setAttribute('aria-label',`Where is ${item.name} used?`);inspect.title='Where this item is used';row.append(inspect);
      }
    }
    n.addEventListener('click',()=>{hideItemHelp();$('#picker').close();S.picker.callback(visible[Number(n.dataset.pick)])});
  });
  $('#picker-empty-reset')?.addEventListener('click',resetPicker);
  const typedId=$('#picker-search').value.trim();
  if(kind==='item'&&/^[1-9][0-9]{0,9}$/.test(typedId)&&Number(typedId)<=4294967295&&!S.itemMap[typedId]){
    const lookup=document.createElement('button');lookup.className='button small picker-id-lookup';lookup.dataset.inspectItem=typedId;lookup.textContent=`Inspect item ID #${typedId} directly`;$('#picker-results').append(lookup);
  }
  bindImages($('#picker-results'));
}
function setPickerCategory(category){S.picker.filters.category=category;S.picker.filters.function='all';S.picker.limit=100;renderPicker();$('#picker-results').scrollTop=0}
function resetPicker(){S.picker.filters.category='all';S.picker.filters.function='all';$('#picker-search').value='';S.picker.limit=100;renderPicker();$('#picker-results').scrollTop=0;$('#picker-search').focus()}
function questField(key,label,type='text'){return `<div class="field"><label for="quest-${key}">${label}</label><input id="quest-${key}" data-quest="${key}" type="${type}" value="${esc(S.quest[key])}" ${type==='number'?'min="0" step="1"':''}></div>`}
function renderQuests(){
  const q=S.quest;
  $('#content').innerHTML=head('STORIES & ADVENTURES','Quest builder','Turn an idea into a hunt, an NPC conversation, and a reward.','<span class="head-note">One completion per character</span>')+
  `<div class="quest-layout"><div class="panel"><div class="quest-section"><h3><span class="quest-number">01</span>The story</h3><div class="form-grid">${questField('title','Quest title')}${questField('id','Unique quest ID')}<div class="field full"><label for="quest-intro">NPC introduction</label><textarea id="quest-intro" data-quest="intro">${esc(q.intro)}</textarea><small>Use plain English text. The unique ID starts with studio_.</small></div></div></div><div class="quest-section"><h3><span class="quest-number">02</span>The adventure</h3><div class="form-grid"><div class="field"><label>Quest giver</label><button class="button" id="quest-npc">${esc(name('mob',q.npc))} · #${q.npc}</button></div><div class="field"><label>Hunt target</label><button class="button" id="quest-target">${esc(name('mob',q.target))} · #${q.target}</button></div>${questField('kills','Number to defeat','number')}${questField('level','Minimum player level','number')}</div></div><div class="quest-section"><h3><span class="quest-number">03</span>The reward</h3><div class="form-grid"><div class="field full"><label>Reward item</label><button class="button" id="quest-reward" ${itemHelpAttrs(q.reward)}>${esc(name('item',q.reward))} · #${q.reward}</button></div></div><div class="number-grid">${questField('quantity','Item count','number')}${questField('yang','Yang','number')}${questField('exp','Experience','number')}</div></div><div class="drop-save"><span id="dirty-label">Ready to customize</span><button class="button primary" id="review-quest">Review quest <span>→</span></button></div></div><div class="panel"><div class="panel-header"><h3>Quest source</h3><button class="button ghost small" id="download-quest">↓ Download .quest</button></div><pre class="code quest-code" id="quest-source">Generating source…</pre><div class="panel-body"><p class="notice info">Saving adds this quest and a compiler hook to your game build. Apply to server runs the installed qc compiler. Source preview alone does not confirm compilation.</p><p class="small-text muted">Players accept at the chosen NPC, defeat the target, and return for a reward. The quest keeps progress between logins and completes once.</p></div></div></div>`;
  let timer;
  $$('[data-quest]').forEach(n=>n.addEventListener('input',()=>{S.quest[n.dataset.quest]=n.value;dirty();clearTimeout(timer);timer=setTimeout(updateQuestCode,400)}));
  [['npc',m=>m.category==='npc'],['target',m=>['monster','metin','boss'].includes(m.category)],['reward',null]].forEach(([key,filter])=>{$('#quest-'+key).addEventListener('click',()=>pick(key==='reward'?'item':'mob',filter,e=>{S.quest[key]=e.id;if(key==='reward')$('#quest-reward').dataset.helpItem=e.id;$('#quest-'+key).textContent=`${e.name} · #${e.id}`;bindItemUsageLinks($('#content'));dirty();updateQuestCode()}))});
  $('#review-quest').addEventListener('click',()=>preview('/api/preview/quest',S.quest));
  $('#download-quest').addEventListener('click',()=>attempt(async()=>{const {code}=await api('/api/quest-code',S.quest);const u=URL.createObjectURL(new Blob([code],{type:'text/plain'}));const a=document.createElement('a');a.href=u;a.download=S.quest.id+'.quest';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}));
  updateQuestCode();bindItemUsageLinks($('#content'));workspaceRestore();
}
let questRequest=0;
async function updateQuestCode(){const id=++questRequest;try{const {code}=await api('/api/quest-code',S.quest);if(id===questRequest&&$('#quest-source'))$('#quest-source').textContent=code}catch(e){if(id===questRequest&&$('#quest-source'))$('#quest-source').textContent=e.message}}
function renderSettings(){
  const menu=S.section==='menu',section=StudioNavigation.settings.find(r=>r.id===S.section),count=S.settings.settings.filter(r=>r.draft!==undefined&&r.draft!==r.value).length;
  $('#content').innerHTML=head('GAME CONFIGURATION','World settings',menu?'Choose the part of your world you want to tune.':section?.description||'All gameplay settings exposed by your installed server.','<div class="settings-actions"><small id="setting-dirty">'+(count?count+' unsaved '+(count===1?'setting':'settings'):'No changes')+'</small><button class="button primary" id="review-settings">Review changes →</button></div>')+
    (menu?configTopicMenu('settings'):configSubmenu('settings')+`<div class="config-section-heading"><h2>${esc(section?.label||'All settings')}</h2><span>Changes are retained when switching topics.</span></div><div class="toolbar"><div class="searchbox"><span>⌕</span><input id="setting-search" value="${esc(S.settingSearch||'')}" placeholder="Find a setting in this topic…" aria-label="Search world settings"></div></div>${['progression','all'].includes(S.section)?'<p class="notice info">EXP, drop and Yang base rates only seed a fresh world. Change current-world rates in the package’s Rates panel. Custom waits and exchange chances require difficulty = custom.</p>':''}<div class="settings-grid" id="setting-grid" data-section="${S.section}"></div>`);
  if(!menu){renderSettingGrid(S.settingSearch||'');$('#setting-search').addEventListener('input',e=>{S.settingSearch=e.target.value;renderSettingGrid(e.target.value)})}
  $('#review-settings').addEventListener('click',()=>{const values={};S.settings.settings.forEach(s=>{if(s.draft!==undefined&&s.draft!==s.value)values[s.key]=s.draft});preview('/api/preview/settings',{hash:S.settings.hash,values})});
  bindConfigNavigation('settings');workspaceRestore();
}
function renderCrafting(){
  $('#content').innerHTML=head('INGREDIENTS & POSSIBILITIES','Crafting recipes','Make something worth collecting the materials for.','<button class="button" id="new-recipe">＋ New recipe</button>')+`<div class="toolbar"><div class="searchbox"><span>⌕</span><input id="recipe-search" placeholder="Find a reward, ingredient, NPC or item ID…" aria-label="Search crafting recipes"></div></div><div class="editor-layout"><div class="panel"><div class="list-head" id="recipe-count"></div><div class="entity-list" id="recipe-list"></div></div><div class="panel" id="recipe-detail"><div class="empty"><div class="empty-symbol">⚒</div>Choose a recipe to edit its ingredients and rewards.</div></div></div><p class="notice info">These are cube recipes from the base table and Seon-Pyeong additions. Some NPC crafting windows have separate Lua definitions in Config files. Refining equipment uses database tables in the existing admin panel.</p>`;
  $('#recipe-search').addEventListener('input',e=>{S.recipeSearch=e.target.value;renderRecipeList()});
  $('#new-recipe').disabled=!S.craftingAccess.npcs.length;$('#new-recipe').addEventListener('click',()=>{if(!leaveOkay())return;const npc=S.craftingAccess.npcs[0],table=S.craftingAccess.tables[npc.source];S.recipe={source:npc.source,index:-1,new:true,name:'New recipe',hash:table.hash,file:table.file,sourceHashes:Object.fromEntries(Object.entries(S.craftingAccess.tables).map(([key,value])=>[key,value.hash])),fields:{npc:npc.id,percent:'100',gold:'0'},materials:[],rewards:[]};dirty();renderRecipeDetail()});
  renderRecipeList();
}
function renderRecipeList(){
  const term=S.recipeSearch.toLowerCase();const list=S.recipes.filter(r=>`${r.name} ${r.npcName} ${r.fields.npc} ${[...r.materials,...r.rewards].map(e=>`${name('item',e.item)} ${e.item}`).join(' ')}`.toLowerCase().includes(term));
  $('#recipe-count').textContent=`${list.length} RECIPES`;
  $('#recipe-list').innerHTML=list.map((r,i)=>`<button class="entity ${S.recipe?.source===r.source&&S.recipe?.index===r.index?'selected':''}" data-recipe="${i}">${icon(r.rewards[0]?.item)}<span><strong>${esc(r.name)}</strong><small>${esc(r.npcName)} · ${r.fields.percent}%${r.npcSupported?'':' · Cube access unconfirmed'}</small></span></button>`).join('')||'<div class="empty">No matching recipes.</div>';
  $$('[data-recipe]').forEach(n=>n.addEventListener('click',()=>{if(!leaveOkay())return;S.recipe=structuredClone(list[Number(n.dataset.recipe)]);dirty(false);renderRecipeDetail();renderRecipeList()}));bindImages($('#recipe-list'));
}
function renderRecipeDetail(){
  const r=S.recipe;
  $('#recipe-detail').innerHTML=`<div class="panel-header"><h2>${esc(r.name)}</h2><span class="pill gold">${r.new?'NEW RECIPE':r.source==='base'?'BASE TABLE':'SEON-PYEONG'}</span></div><div class="panel-body"><div class="form-grid"><div class="field full"><label>Compatible Cube NPC</label><button class="button" id="recipe-npc">${esc(name('mob',r.fields.npc))} · #${esc(r.fields.npc)}</button></div><div class="field"><label for="recipe-percent">Success chance %</label><input id="recipe-percent" type="number" min="1" max="100" value="${esc(r.fields.percent)}"></div><div class="field"><label for="recipe-gold">Yang cost</label><input id="recipe-gold" type="number" min="0" max="100000000" value="${esc(r.fields.gold||'0')}"></div></div></div><div class="panel-header"><h3>Ingredients</h3><button class="button small ghost" data-add-recipe="materials">＋ Add ingredient</button></div><div id="recipe-materials"></div><div class="panel-header"><h3>Rewards</h3><button class="button small ghost" data-add-recipe="rewards">＋ Add reward</button></div><div id="recipe-rewards"></div><div class="drop-save"><span id="dirty-label">Saved file · no changes</span><button class="button ghost danger" id="remove-recipe" ${r.new?'disabled':''}>Remove recipe</button><button class="button primary" id="review-recipe">Review changes →</button></div><div class="panel-body path">${esc(r.file)}</div>`;
  ['percent','gold'].forEach(k=>$('#recipe-'+k).addEventListener('input',e=>{r.fields[k]=e.target.value;dirty()}));
  $('#recipe-npc').addEventListener('click',()=>pick('mob',m=>S.craftingAccess.npcs.some(n=>n.id===m.id),e=>{r.fields.npc=e.id;r.npcSupported=true;$('#recipe-npc-warning')?.remove();$('#recipe-npc').textContent=`${e.name} · #${e.id}`;dirty()}));
  $$('[data-add-recipe]').forEach(n=>n.addEventListener('click',()=>pick('item',e=>e.id!=='1',e=>{r[n.dataset.addRecipe].push({item:e.id,count:'1'});dirty();renderRecipeRows(n.dataset.addRecipe)})));
  $('#review-recipe').addEventListener('click',()=>preview('/api/preview/recipe',r));
  $('#remove-recipe').onclick=()=>{if(S.dirty)return toast('Save or discard the current draft before removing this saved recipe.',true);preview('/api/preview/recipe-delete',{source:r.source,index:r.index,hash:r.hash})};
  if(!S.craftingAccess.npcs.some(n=>n.id===r.fields.npc))$('#recipe-detail .panel-header').insertAdjacentHTML('afterend','<p class="notice recipe-access-warning" id="recipe-npc-warning">No Cube-opening dialogue was identified for this NPC. Choose a compatible NPC to make this recipe accessible, or remove the test recipe.</p>');
  renderRecipeRows('materials');renderRecipeRows('rewards');dirty(r.new||S.dirty);workspaceRestore();
}
function renderRecipeRows(kind){
  const rows=S.recipe[kind],el=$('#recipe-'+kind);
  el.innerHTML=rows.length?`<table><thead><tr><th>#</th><th>ITEM</th><th>COUNT</th><th></th></tr></thead><tbody>${rows.map((e,i)=>`<tr><td>${i+1}</td><td><button class="item-button" ${itemHelpAttrs(e.item)} data-recipe-item="${i}">${icon(e.item)}<span><strong>${esc(name('item',e.item))}</strong><small>#${esc(e.item)}</small></span></button></td><td><input type="number" min="1" max="200" data-recipe-qty="${i}" value="${esc(e.count)}" aria-label="${kind} count ${i+1}"></td><td><button class="icon-button" data-recipe-remove="${i}" aria-label="Remove ${kind} ${i+1}">×</button></td></tr>`).join('')}</tbody></table>`:'<div class="empty">Choose an item from the catalog to add it here.</div>';
  $$('[data-recipe-item]',el).forEach(n=>n.addEventListener('click',()=>pick('item',e=>e.id!=='1',e=>{rows[Number(n.dataset.recipeItem)].item=e.id;dirty();renderRecipeRows(kind)})));
  $$('[data-recipe-qty]',el).forEach(n=>n.addEventListener('input',()=>{rows[Number(n.dataset.recipeQty)].count=n.value;dirty()}));
  $$('[data-recipe-remove]',el).forEach(n=>n.addEventListener('click',()=>{rows.splice(Number(n.dataset.recipeRemove),1);dirty();renderRecipeRows(kind)}));bindImages(el);bindItemUsageLinks(el);
}
function renderSettingGrid(term){
  const list=StudioNavigation.matchingSettings(S.settings.settings,S.section==='menu'?'all':S.section||'all',term);
  const groups=[...new Set(list.map(s=>s.group))];
  $('#setting-grid').innerHTML=groups.map(group=>`<section class="panel"><div class="panel-header"><h3>${esc(group)}</h3><span>${list.filter(s=>s.group===group).length} settings</span></div>${list.filter(s=>s.group===group).map(s=>{const value=s.draft??s.value;const options=s.options ? [...new Set([s.value,...s.options])] : null;return `<div class="setting"><label for="setting-${s.key}">${esc(s.label)}${s.fresh?'<span class="pill">NEW WORLD ONLY</span>':''}</label><code>${s.key}</code>${options?`<select id="setting-${s.key}" data-setting="${s.key}" ${s.fresh?'disabled':''}>${options.map(o=>`<option value="${esc(o)}" ${o===value?'selected':''}>${esc(o)}</option>`).join('')}</select>`:`<input id="setting-${s.key}" data-setting="${s.key}" value="${esc(value)}" ${s.fresh?'disabled':''} autocomplete="off">`}<details><summary>Package notes · default ${esc(s.default)}</summary>${esc(s.description||'Read at startup. Use the launcher or Apply to server to load changes.')}</details></div>`}).join('')}</section>`).join('')||'<div class="empty">No settings match your search.</div>';
  $$('[data-setting]').forEach(n=>n.addEventListener('input',()=>{const s=S.settings.settings.find(s=>s.key===n.dataset.setting);s.draft=n.value;const count=S.settings.settings.filter(s=>s.draft!==undefined&&s.draft!==s.value).length;dirty(count>0);$('#setting-dirty').textContent=count?`${count} unsaved ${count===1?'setting':'settings'}`:'No changes'}));
}
function renderFiles(){
  const menu=S.section==='menu',section=StudioNavigation.files.find(r=>r.id===S.section),topic=S.files.filter(f=>S.section==='all'||StudioNavigation.fileTopic(f)===S.section);
  const categories=[...new Set(topic.map(f=>f.category))].sort();if(!categories.includes(S.fileCategory))S.fileCategory='all';
  const folders=[...new Set(topic.map(StudioNavigation.mapFolder))].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
  $('#content').innerHTML=head('GAME CONFIGURATION','Config files',menu?'Choose a topic to find the files you need.':section?.description||'Browse every editable configuration file.','<span class="head-note">Advanced editors · review before saving</span>')+
    (menu?configTopicMenu('files'):configSubmenu('files')+`<div class="config-section-heading"><h2>${esc(section?.label||'All files')}</h2><span>${topic.length} files in this topic</span></div><div class="toolbar config-file-toolbar"><div class="searchbox"><span>⌕</span><input id="file-search" value="${esc(S.fileSearch)}" placeholder="Search names, folders or file paths…" aria-label="Search configuration files"></div><select id="file-category" aria-label="Configuration category" ${categories.length<2?'hidden':''}><option value="all">All source categories</option>${categories.map(c=>`<option ${c===S.fileCategory?'selected':''}>${esc(c)}</option>`).join('')}</select>${S.section==='maps'?`<select id="file-map-folder" aria-label="Map folder"><option value="all">All maps and shared tables</option>${folders.map(folder=>`<option value="${esc(folder)}" ${S.mapFolder===folder?'selected':''}>${esc(folder==='shared'?'Shared spawn tables':folder)} (${topic.filter(f=>StudioNavigation.mapFolder(f)===folder).length})</option>`).join('')}</select>`:''}</div>${S.section==='quests'?'<p class="notice info">For guided objectives and rewards, use Quests in the sidebar. These files expose the original scripts and shared helpers.</p>':''}<div class="file-layout"><div class="panel"><div class="list-head" id="file-count"></div><div id="file-list" class="file-list"></div></div><div class="panel" id="file-detail"><div class="empty"><div class="empty-symbol">▧</div>Choose a file to inspect or edit.<p>Unfinished edits are preserved as drafts when you switch topics.</p><p>Database-only changes use the existing game admin panel.</p></div></div></div>`);
  if(!menu){
    $('#file-search').addEventListener('input',e=>{S.fileSearch=e.target.value;renderFileList()});
    $('#file-category').addEventListener('change',e=>{S.fileCategory=e.target.value;renderFileList()});
    $('#file-map-folder')?.addEventListener('change',e=>{S.mapFolder=e.target.value;renderFileList()});
    renderFileList();
  }
  bindConfigNavigation('files');
}
function renderFileList(){
  if(!$('#file-list'))return;
  const files=StudioNavigation.matchingFiles(S.files,S.section||'all',S.fileSearch,S.fileCategory,S.mapFolder||'all');
  $('#file-count').textContent=`${fmt(files.length)} FILES`;
  $('#file-list').innerHTML=files.map((f,i)=>`<button class="file-entry ${S.file?.id===f.id?'selected':''}" data-file="${i}"><strong>${esc(f.name)}</strong><small>${esc(f.category)} · ${(f.size/1024).toFixed(1)} KB</small><small>${esc(f.id.split('/').slice(-3).join('/'))}</small></button>`).join('')||'<div class="empty">No matching files in this topic.</div>';
  $$('[data-file]').forEach(n=>n.addEventListener('click',()=>{if(leaveOkay())attempt(async()=>{const navigation=S.navigation,request=(S.fileRequest||0)+1;S.fileRequest=request;const file=await api('/api/file?id='+encodeURIComponent(files[Number(n.dataset.file)].id));if(S.page!=='files'||S.navigation!==navigation||S.fileRequest!==request)return;S.file=file;dirty(false);renderFileDetail();renderFileList()})}));
}
function renderFileDetail(){
  const f=S.file;
  $('#file-detail').innerHTML=`<div class="panel-header"><h3>${esc(f.id.split('/').pop())}</h3><span>${f.encoding==='utf-8'?'UTF-8':'Legacy bytes (Latin-1 view)'}</span></div><div class="panel-body"><div class="path">${esc(f.id)}</div><p class="notice">${esc(f.hint)}${f.encoding!=='utf-8'?' This file has legacy encoded names. Keep those bytes unchanged; add plain ASCII text.':''}</p></div><textarea class="file-text" id="file-text" spellcheck="false" aria-label="Configuration file contents"></textarea><div class="drop-save"><span id="dirty-label">Saved file · no changes</span><button class="button primary" id="review-file">Review changes →</button></div>`;
  $('#file-text').value=f.text;$('#file-text').addEventListener('input',()=>dirty());
  $('#review-file').addEventListener('click',()=>preview('/api/preview/file',{...f,text:$('#file-text').value}));
  workspaceRestore();
}
function renderHistory(history){
  const labels={gameplay:'Gameplay changes',reconciliation:'Update reconciliations',all:'All changes'};
  const types={all:'All types',quests:'Quests',crafting:'Crafting',drops:'Drops',settings:'World settings',maps:'Maps & spawns',shops:'Shops',fishing:'Fishing',alchemy:'Alchemy',items:'Items',skills:'Skills',events:'Events',files:'Other server files'};
  const selected=labels[S.historyCategory]?S.historyCategory:'gameplay';
  const type=types[S.historyType]?S.historyType:'all';
  const category=row=>row.category==='reconciliation'?'reconciliation':'gameplay';
  const areas=row=>row.areas?.length?row.areas:['files'];
  const inCategory=history.filter(row=>selected==='all'||category(row)===selected);
  const inType=history.filter(row=>type==='all'||areas(row).includes(type));
  const counts={gameplay:inType.filter(row=>category(row)==='gameplay').length,reconciliation:inType.filter(row=>category(row)==='reconciliation').length,all:inType.length};
  const rows=inCategory.filter(row=>type==='all'||areas(row).includes(type));
  const description=selected==='reconciliation'?'Merges and conflict resolutions after game updates.':selected==='gameplay'?'Recipe, drop, quest, EXP and other gameplay edits.':'Gameplay edits and update reconciliations in one timeline.';
  $('#content').innerHTML=head('A WAY BACK','Change history','Gameplay edits and game-update reconciliations have separate views.')+
  `<div class="work-actions history-tabs" role="tablist" aria-label="History category">${Object.entries(labels).map(([key,label])=>`<button class="button ${selected===key?'primary':''}" type="button" role="tab" aria-selected="${selected===key}" data-history-category="${key}">${label} (${counts[key]})</button>`).join('')}</div><p class="subtext">${description}</p>`+
  `<div class="history-filter"><label for="history-type">Change type</label><select id="history-type">${Object.entries(types).map(([key,label])=>`<option value="${key}" ${key===type?'selected':''}>${esc(label)} (${key==='all'?inCategory.length:inCategory.filter(row=>areas(row).includes(key)).length})</option>`).join('')}</select><span class="muted">A save can include several types. Rollback restores the entire save.</span></div>`+
  `<div class="notice info"><strong>How rollback works</strong><p>1. Choose Review rollback. 2. Inspect the before/after diff and click Revert saved changes. 3. Use Apply to server to load the reverted files.</p><p>This restores the listed files to their contents before that save. Newer edits in the same files must be reverted first, including edits in the other category. Use All changes and All types to find related records. Character progress and items are retained.</p></div><div class="panel"><div class="panel-header"><h3>${labels[selected]}${type==='all'?'':` · ${esc(types[type])}`}</h3><span>${rows.length} of ${inCategory.length} recorded</span></div>${rows.length?rows.map(h=>`<div class="history-entry"><span>↶</span><div><h3>${esc(h.title)}</h3><p>${h.files.length} ${h.files.length===1?'file':'files'} · ${new Date(h.time).toLocaleString()} · ${esc(h.status)} · ${labels[category(h)]}</p><p class="history-types">${esc(areas(h).map(area=>types[area]||types.files).join(' · '))}</p><small>${esc(h.files.map(f=>f.path.replaceAll('\\','/').split('/').pop()).join(', '))}</small><p class="history-restore-note">${esc(h.restoreReason)}</p></div><button class="button small" data-restore="${esc(h.id)}" ${h.canRestore?'':'disabled'}>Review rollback</button></div>`).join(''):`<div class="empty">${type!=='all'?'No saved changes match this type in this category. Choose All types or All changes to widen the view.':selected==='reconciliation'?'No update reconciliations recorded yet.':selected==='gameplay'?'No gameplay changes recorded yet.':'No saved changes yet. Backups appear here after saving an edit.'}</div>`}</div>`;
  $('#history-type').addEventListener('change',event=>{S.historyType=event.target.value;renderHistory(history)});
  $$('[data-history-category]').forEach(button=>button.addEventListener('click',()=>{S.historyCategory=button.dataset.historyCategory;renderHistory(history)}));
  $$('[data-restore]').forEach(button=>button.addEventListener('click',()=>preview('/api/preview/restore',{id:button.dataset.restore})));
}
async function preview(path,body){await attempt(async()=>{
  const plan=await api(path,body);S.plan=plan;
  $('#commit-button').textContent=plan.changeset?'Stage in change set':plan.confirmLabel||'Save changes';
  $('#review-title').textContent=plan.title;
  $('#review-body').innerHTML=`<p class="notice info">${esc(plan.hint)}</p>${plan.summary?.length?`<div class="table-wrap"><table><thead><tr><th>Configuration</th><th>Before</th><th>After</th></tr></thead><tbody>${plan.summary.map(row=>`<tr><th>${esc(row.field)}</th><td>${esc(row.before)}</td><td>${esc(row.after)}</td></tr>`).join('')}</tbody></table></div>`:''}${plan.files.map(f=>`<div class="diff-file"><strong>${esc(f.path)}</strong><pre class="code">${f.diff.split('\n').map(l=>`<span class="${l.startsWith('+')?'diff-added':l.startsWith('-')?'diff-removed':''}">${esc(l)}</span>`).join('\n')}</pre></div>`).join('')}`;
  if(plan.keptGameFiles?.length)$('#review-body').insertAdjacentHTML('afterbegin',`<div class="notice info"><strong>Newer game files will be kept</strong>${plan.keptGameFiles.map(path=>`<p class="path">${esc(path)}</p>`).join('')}</div>`);
  $('#review').showModal();
})}
async function commit(){const button=$('#commit-button');button.disabled=true;try{
  const result=await api('/api/commit',{id:S.plan.id});$('#review').close();await workspaceForget();dirty(false);if(result.publishedSet===WUI.activeSet){WUI.activeSet=null;localStorage.removeItem(wPrefix()+'active-set')}await workspaceRefresh();S.data.groups=(await api('/api/bootstrap')).groups;toast(result.staged||result.recovered?result.hint:'Saved with a backup. Use Apply to server to load the changes.');
  if(S.page==='drops'){S.dropSearch='';renderDrops()}
  else if(S.page==='quests'){QuestUI.search='';QuestUI.origin='all';QuestUI.kind='all';QuestUI.limit=40;await renderQuestLibrary()}
  else navigate(S.route||S.page,{reload:true});
}catch(e){toast(e.message,true)}finally{button.disabled=false}}
function openApplyDialog(){
  ApplyUI.jobId=null;ApplyUI.error='';ApplyUI.loading=true;ApplyUI.connectionFailed=false;
  $('#apply-previous').open=false;
  $('#apply-interrupted-ack').checked=false;
  $('#apply-dialog').showModal();
  refreshApplyControl();
  updateStatus();
}
async function runServerOperation(validateOnly){
  if(ApplyUI.starting||S.status?.job.status==='running')return;
  ApplyUI.starting=validateOnly?'validation':'apply';ApplyUI.error='';ApplyUI.jobId=null;
  refreshApplyControl();
  try{
    const interrupted=WUI.info?.interruptedDeployment;
    const body=!validateOnly&&interrupted&&$('#apply-interrupted-ack').checked?{acknowledgeInterrupted:interrupted.id}:{};
    const job=await api(validateOnly?'/api/validate':'/api/apply',body);
    ApplyUI.jobId=job.id;
    S.status={...S.status,job};
  }catch(error){ApplyUI.error=error.message;toast(error.message,true);}
  finally{ApplyUI.starting='';await updateStatus();}
}
let applyTimer;
async function updateStatus(){
  try{
    const data=await api('/api/status');S.status=data;
    const badge=$('#docker-badge');
    badge.textContent=data.job.status==='running'?(data.job.kind==='validation'?'Validating build…':'Applying changes…'):data.health?.gameHealthy?'Game healthy':data.docker.available?'Game health unverified':'Docker stopped';
    badge.classList.toggle('good',!!data.health?.gameHealthy);badge.classList.toggle('neutral',!data.docker.available);
    await workspaceRefresh();
    ApplyUI.loading=false;ApplyUI.connectionFailed=false;
    refreshApplyControl();
    if(data.job.status==='running'&&!applyTimer)applyTimer=setInterval(updateStatus,4000);
    if(data.job.status!=='running'&&applyTimer){clearInterval(applyTimer);applyTimer=null}
  }catch(error){
    $('#docker-badge').textContent='Studio disconnected';
    ApplyUI.loading=false;ApplyUI.connectionFailed=true;
    refreshApplyControl();
  }
}

document.addEventListener('DOMContentLoaded',async()=>{
  document.addEventListener('click',e=>{const button=e.target.closest('[data-inspect-item]');if(button){e.preventDefault();e.stopPropagation();showItemUsage(button.dataset.inspectItem)}});
  $('#explore-items').addEventListener('click',browseItems);
  $('#usage-browse').addEventListener('click',()=>{$('#item-usage').close();if($('#picker').open)$('#picker-search').focus();else browseItems()});
  $('#usage-refresh').addEventListener('click',()=>showItemUsage(S.usageId));
  $('#item-usage').addEventListener('close',()=>{usageRequest++;$('#usage-refresh').disabled=false});
  document.addEventListener('pointerover',e=>{const anchor=e.target.closest('[data-help-item]');if(anchor)showItemHelp(anchor)});
  document.addEventListener('pointerout',e=>{const anchor=e.target.closest('[data-help-item]');if(anchor&&!anchor.contains(e.relatedTarget))scheduleHideItemHelp()});
  document.addEventListener('focusin',e=>{const anchor=e.target.closest('[data-help-item]');if(anchor)showItemHelp(anchor);else hideItemHelp()});
  document.addEventListener('focusout',e=>{if(e.target.closest('[data-help-item]'))scheduleHideItemHelp()});
  $('#item-tooltip').addEventListener('pointerenter',()=>clearTimeout(helpHideTimer));
  $('#item-tooltip').addEventListener('pointerleave',scheduleHideItemHelp);
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#item-tooltip').hidden){e.preventDefault();e.stopImmediatePropagation();hideItemHelp()}},true);
  window.addEventListener('resize',hideItemHelp);
  document.addEventListener('scroll',e=>{
    if($('#item-tooltip').contains(e.target)||!helpAnchor)return;
    const rect=helpAnchor.getBoundingClientRect();
    if(document.activeElement===helpAnchor&&rect.bottom>0&&rect.top<window.innerHeight)positionItemHelp();else hideItemHelp();
  },true);
  $$('dialog').forEach(dialog=>dialog.addEventListener('close',hideItemHelp));
  $$('nav [data-page]').forEach(n=>n.addEventListener('click',()=>navigate(n.dataset.page)));
  $$('.brand').forEach(n=>n.addEventListener('click',e=>{e.preventDefault();navigate('overview')}));
  $$('[data-close]').forEach(n=>n.addEventListener('click',()=>$('#'+n.dataset.close).close()));
  $('#picker-search').addEventListener('input',()=>{S.picker.limit=100;renderPicker();$('#picker-results').scrollTop=0});
  $('#picker-category').addEventListener('change',e=>setPickerCategory(e.target.value));
  $('#picker-function').addEventListener('change',e=>{S.picker.filters.function=e.target.value;S.picker.limit=100;renderPicker();$('#picker-results').scrollTop=0});
  $('#picker-sort').addEventListener('change',e=>{S.picker.filters.sort=e.target.value;S.picker.limit=100;renderPicker();$('#picker-results').scrollTop=0});
  $('#picker-reset').addEventListener('click',resetPicker);
  $('#picker-more').addEventListener('click',()=>{const firstNew=S.picker.limit;S.picker.limit+=100;renderPicker();$(`[data-pick="${firstNew}"]`)?.focus()});
  $('#picker-search').addEventListener('keydown',e=>{if(e.key==='ArrowDown'){$('.pick-result')?.focus();e.preventDefault()}if(e.key==='Enter'){$('.pick-result')?.click();e.preventDefault()}});
  $('#picker-results').addEventListener('keydown',e=>{const list=$$('.pick-result'),i=list.indexOf(document.activeElement);if(e.key==='ArrowDown'){list[Math.min(i+1,list.length-1)]?.focus();e.preventDefault()}if(e.key==='ArrowUp'){if(i===0)$('#picker-search').focus();else list[i-1]?.focus();e.preventDefault()}});
  $('#commit-button').addEventListener('click',commit);
  $('#discard-draft').addEventListener('click',()=>attempt(async()=>{await workspaceForget();dirty(false);navigate(S.route||S.page,{reload:true})}));
  $('#connection-info').addEventListener('click',()=>toast('Connected server folder:\n'+S.data.root));
  $('#apply-button').addEventListener('click',openApplyDialog);
  $('#run-validate').addEventListener('click',()=>runServerOperation(true));
  $('#run-apply').addEventListener('click',()=>runServerOperation(false));
  $('#apply-interrupted-ack').addEventListener('change',refreshApplyControl);
  try{S.data=await api('/api/bootstrap');S.itemMap=Object.fromEntries(S.data.items.map(e=>[e.id,e]));S.mobMap=Object.fromEntries(S.data.mobs.map(e=>[e.id,e]));await initWorkspace();initSidebarNavigation();if(WUI.activeSet)S.data.groups=(await api('/api/bootstrap')).groups;$('#version').textContent='Game '+S.data.version+' · Connected';$('#studio-version').textContent='METIN2 STUDIO '+(S.data.studioVersion||'');await navigate(location.hash.slice(1)||'overview');updateStatus();setInterval(()=>{if(!applyTimer)updateStatus()},30000)}catch(e){$('#content').innerHTML='<div class="empty">Studio could not read the installation.<p></p></div>';$('#content .empty p').textContent=e.message}
});
