'use strict';
const QuestUI={view:'library',rows:[],search:'',origin:'all',kind:'all',limit:40,request:0,activeDraft:null,sourceTitle:''};
const questBuilderBase=renderQuests;
const questKinds={hunt:'Hunt',collection:'Item turn-in',exchange:'Exchange',source:'Game quest · guided fields'};
const questRowKind=row=>row.template?(row.template.template||'hunt'):'source';
const questScope=()=>WUI.activeSet||'direct';

async function questTransition(){
  hideQuestHelp();
  if(!leaveOkay())return false;
  await workspaceFlush();
  dirty(false);hideItemHelp();++questRequest;
  return S.page==='quests';
}

async function renderQuestLibrary(){
  hideQuestHelp();QuestHelp.cache.clear();
  QuestUI.view='library';QuestUI.activeDraft=null;S.file=null;
  window.scrollTo({top:0,behavior:'instant'});
  const request=++QuestUI.request,navigation=S.navigation;
  $('#content').innerHTML=head('STORIES & ADVENTURES','Quests','Browse the game quests, update an existing adventure, or create something new.','<button class="button primary" id="new-quest">＋ New quest</button>')+
    `<div class="quest-menu-stats" id="quest-menu-stats"></div><div class="toolbar quest-menu-filters"><div class="searchbox"><span>⌕</span><input id="quest-search" aria-label="Search quests" placeholder="Search quest name, ID or source file…" value="${esc(QuestUI.search)}"></div><select id="quest-origin" aria-label="Quest origin">${[['all','All quests'],['game','Game quests'],['studio','Studio quests']].map(([id,label])=>`<option value="${id}" ${QuestUI.origin===id?'selected':''}>${label}</option>`).join('')}</select><select id="quest-kind" aria-label="Quest editor type">${[['all','All types'],['source','Game quests'],['hunt','Hunts'],['collection','Item turn-ins'],['exchange','Exchanges']].map(([id,label])=>`<option value="${id}" ${QuestUI.kind===id?'selected':''}>${label}</option>`).join('')}</select></div><div id="quest-drafts"></div><div class="panel" id="quest-catalog"><div class="loading">Reading quest sources…</div></div><p class="notice info">Hover a quest or focus its title to see what it does. Game quests open with guided fields for recognised values, with Advanced source available for their custom logic. Studio quests use the guided builder. Source copies with the same quest identity are grouped; the package override or an already edited source takes precedence. Review changes before saving, then Apply when ready.</p>`;
  $('#new-quest').onclick=()=>attempt(()=>openQuestBuilder());
  for(const [selector,key] of [['#quest-search','search'],['#quest-origin','origin'],['#quest-kind','kind']])$(selector).oninput=e=>{QuestUI[key]=e.target.value;QuestUI.limit=40;renderQuestRows()};
  const [rows,info]=await Promise.all([api('/api/quests'),api('/api/workspace')]);
  if(request!==QuestUI.request||S.page!=='quests'||QuestUI.view!=='library'||S.navigation!==navigation)return;
  QuestUI.rows=rows;WUI.info=info;
  $('#quest-menu-stats').innerHTML=[['Game quests',rows.filter(r=>r.origin==='game').length],['Studio quests',rows.filter(r=>r.origin==='studio').length],['Customized game quests',rows.filter(r=>r.compileRegistered).length]].map(([label,count])=>`<div><strong>${fmt(count)}</strong><span>${label}</span></div>`).join('');
  const drafts=info.drafts.filter(row=>row.kind==='quests'||row.kind==='files'&&row.title.endsWith('.quest'));
  if(drafts.length)$('#quest-drafts').innerHTML=`<section class="panel quest-menu-drafts"><div class="panel-header"><h2>Unfinished quests</h2><span>${drafts.length} saved drafts</span></div>${drafts.map(row=>`<article class="quest-menu-draft"><div><strong>${esc(row.title)}</strong><small>${esc(row.kind==='quests'?'Guided builder':'Quest source')} · ${wDate(row.updated)}</small></div><button class="button small" data-resume-quest="${esc(row.id)}">Resume draft</button></article>`).join('')}</section>`;
  $$('[data-resume-quest]').forEach(button=>button.onclick=()=>attempt(()=>resumeWorkspaceDraft(button.dataset.resumeQuest)));
  renderQuestRows();
}

function renderQuestRows(){
  hideQuestHelp();
  if(!$('#quest-catalog'))return;
  const query=QuestUI.search.trim().toLowerCase(),rows=QuestUI.rows.filter(row=>(QuestUI.origin==='all'||row.origin===QuestUI.origin)&&(QuestUI.kind==='all'||questRowKind(row)===QuestUI.kind)&&(!query||`${row.title} ${row.questName} ${row.id}`.toLowerCase().includes(query)));
  $('#quest-catalog').innerHTML=`<div class="panel-header"><h2>Quest library</h2><span>${rows.length} quests found</span></div><div class="quest-menu-list">${rows.slice(0,QuestUI.limit).map(row=>`<article class="quest-menu-row" data-help-quest="${esc(row.id)}"><div class="quest-menu-symbol" aria-hidden="true">${row.origin==='studio'?'✦':'▤'}</div><div class="quest-menu-description"><div class="quest-menu-title"><h3><button class="quest-help-title" type="button" aria-label="About ${esc(row.title)}">${esc(row.title)} <span aria-hidden="true">ⓘ</span></button></h3><span class="pill ${row.origin==='studio'?'gold':''}">${row.origin==='studio'?'STUDIO':'GAME'}</span>${row.staged?'<span class="pill">STAGED</span>':''}${row.compileRegistered?'<span class="pill">CUSTOMIZED</span>':''}</div><p>${esc(row.questName)} · ${esc(questKinds[questRowKind(row)])}${row.template?` · Level ${esc(row.template.level)}+ · ${Number(row.template.cooldown)?'Repeatable':'One time'}`:''}${row.otherSources?.length?` · ${row.otherSources.length+1} source copies`:''}</p><small>${esc(row.id)}</small></div><div class="work-actions"><button class="button small" data-edit-quest="${esc(row.id)}">Edit quest</button>${row.template?`<button class="button ghost small" data-clone-quest="${esc(row.id)}">Clone</button>`:''}${row.origin==='studio'?`<button class="button ghost small danger" data-remove-quest="${esc(row.id)}">Remove</button>`:''}</div></article>`).join('')||'<div class="empty">No quests match these filters.<p>Clear your search or create a new quest.</p></div>'}</div>${rows.length>QuestUI.limit?'<div class="quest-menu-more"><button class="button" id="quest-more">Show 40 more quests</button></div>':''}`;
  $('#quest-more')?.addEventListener('click',()=>{QuestUI.limit+=40;renderQuestRows()});
  $$('[data-edit-quest]').forEach(button=>button.onclick=()=>attempt(async()=>{const row=QuestUI.rows.find(row=>row.id===button.dataset.editQuest);if(row.template)await openQuestBuilder(row);else await openQuestSource(row)}));
  $$('[data-remove-quest]').forEach(button=>button.onclick=()=>removeStudioQuest(QuestUI.rows.find(row=>row.id===button.dataset.removeQuest)));
  $$('[data-clone-quest]').forEach(button=>button.onclick=()=>attempt(()=>openQuestBuilder(QuestUI.rows.find(row=>row.id===button.dataset.cloneQuest),true)));
}

function removeStudioQuest(row){
  if(S.dirty)return toast('Save or discard the current draft before removing this saved quest.',true);
  preview('/api/preview/quest-delete',{id:row.id,hash:row.hash});
}

async function openQuestBuilder(row=null,clone=false){
  if(!await questTransition())return;
  QuestUI.view='builder';S.file=null;
  S.quest=row?.template?structuredClone(row.template):{title:'A new adventure',intro:'The village needs your help.',npc:'9001',target:'8001',reward:'71084',kills:10,level:5,quantity:1,yang:10000,exp:5000,template:'hunt',cooldown:0,requiredItem:'30001',requiredCount:1};
  if(row&&!clone){S.quest.hash=row.hash;QuestUI.activeDraft=`${questScope()}:quests:${row.id}`}
  else{delete S.quest.hash;S.quest.id='studio_quest_'+Date.now().toString(36);if(clone)S.quest.title='Copy of '+S.quest.title;QuestUI.activeDraft=`${questScope()}:quests:new:${S.quest.id}`}
  renderQuestBuilder();
  if(clone)dirty();
}

function renderQuestBuilder(){
  QuestUI.view='builder';const q=S.quest;
  window.scrollTo({top:0,behavior:'instant'});
  q.template||='hunt';q.cooldown??=0;q.requiredItem||='30001';q.requiredCount||=1;
  questBuilderBase();
  $('.page-head h1').textContent=q.hash?'Edit quest':'New quest';
  $('.page-head p').textContent='Choose the requirements, conversation and rewards, then review the changes.';
  $('.page-head .head-note').innerHTML='<button class="button" id="back-to-quests">← Back to quests</button>';
  $('#back-to-quests').onclick=()=>attempt(backToQuests);
  if(q.hash){$('#back-to-quests').insertAdjacentHTML('beforebegin','<button class="button ghost danger" id="remove-current-quest">Remove quest</button>');$('#remove-current-quest').onclick=()=>removeStudioQuest({id:'linux-port/docker/game/custom-quests/'+q.id+'.quest',hash:q.hash})}
  $('.quest-layout').insertAdjacentHTML('beforebegin',`<div class="editor-filters"><label>Template<select id="quest-template">${[['hunt','Hunt'],['collection','Collection / item turn-in'],['exchange','Material exchange']].map(([id,title])=>`<option value="${id}" ${q.template===id?'selected':''}>${title}</option>`).join('')}</select></label><label>Repeat cooldown (seconds; 0 = one time)<input id="quest-cooldown" type="number" min="0" max="2592000" value="${esc(q.cooldown)}"></label><button class="button" id="quest-return-npc">Return to: ${esc(name('mob',q.returnNpc||q.npc))}</button><button class="button" id="quest-player-preview">Player dialogue preview</button></div><div id="quest-requirements"></div><p id="quest-inline-error" role="status"></p>`);
  $('#quest-template').onchange=e=>{q.template=e.target.value;dirty();renderQuestBuilder()};
  $('#quest-cooldown').oninput=e=>{q.cooldown=e.target.value;dirty();updateQuestCode()};
  $('#quest-return-npc').onclick=()=>pick('mob',mob=>mob.category==='npc',entry=>{q.returnNpc=entry.id;$('#quest-return-npc').textContent='Return to: '+entry.name;dirty();updateQuestCode()});
  if(q.template!=='hunt'){
    $('#quest-requirements').innerHTML=`<div class="editor-filters"><button class="button" id="quest-required-item">Turn in: ${esc(name('item',q.requiredItem))}</button><label>Quantity<input id="quest-required-count" type="number" min="1" max="200" value="${esc(q.requiredCount)}"></label><small>Consumes existing inventory items. Add drops separately if needed.</small></div>`;
    $('#quest-target').closest('.field').hidden=true;$('#quest-kills').closest('.field').hidden=true;
    $('#quest-required-item').onclick=()=>pick('item',item=>item.id!=='1',entry=>{q.requiredItem=entry.id;$('#quest-required-item').textContent='Turn in: '+entry.name;dirty();updateQuestCode()});
    $('#quest-required-count').oninput=e=>{q.requiredCount=e.target.value;dirty();updateQuestCode()};
  }
  $('#quest-player-preview').onclick=()=>toolDialog('Player dialogue preview',`<h3>${esc(q.title)}</h3><div class="steps"><div class="step"><span>1</span><div><strong>Available · ${esc(name('mob',q.npc))}</strong><p>A quest letter and an NPC marker guide eligible players to the giver.</p><p>${esc(q.intro)}</p><p>${q.template==='hunt'?`Defeat ${esc(q.kills)} × ${esc(name('mob',q.target))}.`:`Bring ${esc(q.requiredCount)} × ${esc(name('item',q.requiredItem))}.`}</p><p><span class="pill">Accept</span> <span class="pill">Later</span></p></div></div><div class="step"><span>2</span><div><strong>${q.template==='hunt'?'Objective and progress':'Required items'}</strong><p>${q.template==='hunt'?`The letter names ${esc(name('mob',q.target))} and shows the number defeated out of ${esc(q.kills)}. Kills count after accepting.`:`The letter names ${esc(name('item',q.requiredItem))} and shows the inventory count out of ${esc(q.requiredCount)}.`}</p></div></div><div class="step"><span>3</span><div><strong>Return · ${esc(name('mob',q.returnNpc||q.npc))}</strong><p>The return letter names this NPC and marks it for the hand-in. Reward: ${esc(q.quantity)} × ${esc(name('item',q.reward))}, ${fmt(q.yang)} Yang and ${fmt(q.exp)} EXP.</p></div></div></div><p class="notice info">NPC markers appear when the NPC is on your current map. ${Number(q.cooldown)?'Available again after '+fmt(q.cooldown)+' seconds.':'One completion per character; completed characters do not get a new marker.'}</p>`);
  $('.quest-layout .panel-body .small-text')?.remove();
  $('.quest-layout .panel-body').insertAdjacentHTML('beforeend','<p class="small-text muted">Editing a saved quest preserves its character flags. Clone it to start fresh progress. Changing template type requires a new ID.</p>');
}

async function openQuestAdvanced(row){
  if(!await questTransition())return;
  const request=++QuestUI.request;
  const file=await api('/api/file?id='+encodeURIComponent(row.id));
  if(S.page!=='quests'||request!==QuestUI.request)return;
  QuestUI.view='source';QuestUI.sourceTitle=row.title||row.questName||row.id.split('/').pop();S.file=file;
  renderQuestSource();
}

function renderQuestSource(){
  QuestUI.view='source';
  window.scrollTo({top:0,behavior:'instant'});
  $('#content').innerHTML=head('EXISTING QUEST','Edit '+QuestUI.sourceTitle,'Update the original script while retaining its quest identity.','<button class="button" id="back-to-quests">← Back to quests</button>')+`<p class="notice info">Saving registers this source for compilation after the package quests. Keep existing state names if characters have already started this quest. Review all changes, then Apply when ready. New adventures use the guided builder.</p><div class="panel" id="file-detail"></div>`;
  $('#back-to-quests').onclick=()=>attempt(backToQuests);
  renderFileDetail();$('#file-text').setAttribute('aria-label','Quest source');
  $('#back-to-quests').insertAdjacentHTML('beforebegin','<button class="button" id="quest-guided">Guided fields</button>');
  $('#quest-guided').onclick=()=>attempt(()=>openQuestSource({id:S.file.id,title:QuestUI.sourceTitle}));
}

async function backToQuests(){if(await questTransition())await renderQuestLibrary()}

const questSourceCodeUpdate=updateQuestCode;
updateQuestCode=async function(){await questSourceCodeUpdate();const error=$('#quest-inline-error');if(error){const code=$('#quest-source')?.textContent||'';error.textContent=code.startsWith('--')?'':code}};
renderQuests=renderQuestLibrary;

const NativeQuest={model:null,values:{},title:'',section:'all',search:''};
async function openQuestSource(row){
  if(!await questTransition())return;
  const request=++QuestUI.request;
  QuestUI.view='guided';NativeQuest.model=null;NativeQuest.values={};NativeQuest.title=row.title||row.questName||row.id.split('/').pop();NativeQuest.section='all';NativeQuest.search='';S.file=null;
  $('#content').innerHTML=head('EXISTING QUEST','Edit '+NativeQuest.title,'Reading guided quest fields…')+'<div class="loading">Reading objectives, rewards and dependencies…</div>';
  try{
    const model=await api('/api/quest-fields?id='+encodeURIComponent(row.id));
    if(S.page!=='quests'||request!==QuestUI.request)return;
    NativeQuest.model=model;
    if(model.questName==='hunting')NativeQuest.section=model.fields[0]?.group||'all';
    renderNativeQuest();workspaceRestore();
  }catch(error){
    if(S.page!=='quests'||request!==QuestUI.request)return;
    $('#content').innerHTML=head('EXISTING QUEST','Edit '+NativeQuest.title,'This version needs the advanced editor.','<button class="button" id="back-to-quests">← Back to quests</button>')+`<div class="notice">${esc(error.message)}</div><button class="button" id="native-advanced">Advanced source</button>`;
    $('#back-to-quests').onclick=()=>attempt(backToQuests);$('#native-advanced').onclick=()=>attempt(()=>openQuestAdvanced(row));
  }
}
function renderNativeQuest(){
  QuestUI.view='guided';S.file=null;
  const m=NativeQuest.model,groups=[...new Set(m.fields.map(f=>f.group))];
  if(NativeQuest.section!=='all'&&!groups.includes(NativeQuest.section))NativeQuest.section='all';
  $('#content').innerHTML=head('EXISTING QUEST','Edit '+NativeQuest.title,'Choose items and adjust objectives or rewards while retaining this quest’s existing flow.','<button class="button" id="back-to-quests">← Back to quests</button>')+
    `<div class="editor-actions native-quest-actions"><button class="button primary" id="native-review" ${m.fields.length?'':'disabled'}>Review field changes</button><button class="button" id="native-advanced">Advanced source</button><span id="native-edited" role="status"></span></div><div class="notice info">These fields edit the existing sources. Characters keep their quest progress; previously granted rewards stay as they are. Shared fields are labelled below.</div><div class="editor-filters"><label>Quest section<select id="native-section"><option value="all">All sections · ${m.fields.length} fields</option>${groups.map(g=>`<option value="${esc(g)}" ${NativeQuest.section===g?'selected':''}>${esc(g)}</option>`).join('')}</select></label><label>Find a field<input type="search" id="native-search" value="${esc(NativeQuest.search)}" placeholder="Item, quantity, EXP, kills…"></label></div><div id="native-fields"></div><details class="panel native-quest-notes"><summary>Coverage & source files</summary>${m.notes.map(n=>`<p>${esc(n)}</p>`).join('')}<p>${m.sources.map(s=>`<code>${esc(s)}</code>`).join('<br>')}</p><button class="button small" id="native-settings">Open World settings</button></details>`;
  $('#back-to-quests').onclick=()=>attempt(backToQuests);
  $('#native-advanced').onclick=()=>attempt(()=>openQuestAdvanced({id:m.id,title:NativeQuest.title}));
  $('#native-review').onclick=()=>preview('/api/preview/quest-fields',{id:m.id,hashes:m.hashes,values:NativeQuest.values});
  $('#native-settings').onclick=()=>navigate('settings/progression');
  $('#native-section').onchange=e=>{NativeQuest.section=e.target.value;renderNativeFields()};
  $('#native-search').oninput=e=>{NativeQuest.search=e.target.value;renderNativeFields()};
  renderNativeFields();
}
function nativeValue(f){return NativeQuest.values[f.key]??f.value}
function nativeName(f,value){return {primary_armor:'Armour for the player’s class',primary_helmet:'Helmet for the player’s class'}[value]||(f.kind==='number'?value:name(f.kind==='mob'?'mob':'item',value))}
function nativeSet(f,value){if(String(value)===f.value)delete NativeQuest.values[f.key];else NativeQuest.values[f.key]=String(value);dirty(Object.keys(NativeQuest.values).length>0);nativeEdited()}
function nativeEdited(){$('#native-edited').textContent=Object.keys(NativeQuest.values).length+' fields changed'}
function renderNativeFields(){
  const query=NativeQuest.search.toLowerCase(),fields=NativeQuest.model.fields.filter(f=>(NativeQuest.section==='all'||NativeQuest.section===f.group)&&`${f.label} ${f.group} ${f.detail} ${nativeName(f,nativeValue(f))}`.toLowerCase().includes(query)),groups=[...new Set(fields.map(f=>f.group))];
  const priority=g=>g==='Research requirements'?0:g==='Items'?1:g.startsWith('Completion rewards')?2:g==='Shared cooldown'?3:g==='Targets'?5:4;
  groups.sort((a,b)=>priority(a)-priority(b));
  $('#native-fields').innerHTML=groups.map(group=>`<section class="panel native-quest-panel"><div class="panel-header"><h2>${esc(group)}</h2></div><div class="native-quest-grid">${fields.filter(f=>f.group===group).map(f=>{const i=NativeQuest.model.fields.indexOf(f),v=nativeValue(f);return `<div class="field native-quest-field"><label for="native-field-${i}">${esc(f.label)}</label>${f.kind==='number'?`<input id="native-field-${i}" data-native-number="${i}" type="number" step="${f.key.includes(':setting:')?'any':'1'}" min="${f.min}" max="${f.max}" value="${esc(v)}" ${f.disabled?'disabled':''}>`:`<button class="button native-picker ${f.kind==='item'&&/^\d+$/.test(v)?'item-button item-reference':''}" id="native-field-${i}" data-native-pick="${i}" ${f.kind==='item'&&/^\d+$/.test(v)?itemHelpAttrs(v):''}>${f.kind==='item'&&/^\d+$/.test(v)?itemContent(v):`${esc(nativeName(f,v))} <span>#${esc(v)} ▾</span>`}</button>${f.choices?`<select data-native-symbol="${i}" aria-label="Class reward option for ${esc(f.label)}"><option value="">Choose a specific item above</option>${f.choices.map(c=>`<option value="${c}" ${v===c?'selected':''}>${esc(nativeName(f,c))}</option>`).join('')}</select>`:''}`}<small>${esc(f.detail)}</small>${NativeQuest.values[f.key]!==undefined?`<span class="native-field-change">Was: ${esc(nativeName(f,f.value))} · <button type="button" class="subtle-link" data-native-reset="${i}">Reset</button></span>`:''}</div>`}).join('')}</div></section>`).join('')||'<div class="empty">No guided fields match. Check Coverage & source files for unsupported values.</div>';bindImages($('#native-fields'));bindItemUsageLinks($('#native-fields'));
  $$('[data-native-number]').forEach(input=>input.oninput=()=>nativeSet(NativeQuest.model.fields[Number(input.dataset.nativeNumber)],input.value));
  $$('[data-native-pick]').forEach(button=>button.onclick=()=>{const f=NativeQuest.model.fields[Number(button.dataset.nativePick)];pick(f.kind==='mob'?'mob':'item',entry=>f.kind==='mob'?entry.category!=='npc':entry.id!=='1',entry=>{nativeSet(f,entry.id);renderNativeFields()})});
  $$('[data-native-symbol]').forEach(select=>select.onchange=()=>{if(select.value){nativeSet(NativeQuest.model.fields[Number(select.dataset.nativeSymbol)],select.value);renderNativeFields()}});
  $$('[data-native-reset]').forEach(button=>button.onclick=()=>{const f=NativeQuest.model.fields[Number(button.dataset.nativeReset)];nativeSet(f,f.value);renderNativeFields()});
  nativeEdited();
}

const QuestHelp={anchor:null,row:null,dismissed:null,request:0,timer:null,cache:new Map()};
function hideQuestHelp(){
  clearTimeout(QuestHelp.timer);QuestHelp.request++;
  const tip=$('#quest-tooltip');
  if(tip?.matches(':popover-open'))tip.hidePopover();
  if(tip)tip.hidden=true;
  if(QuestHelp.anchor){
    const ids=(QuestHelp.anchor.getAttribute('aria-describedby')||'').split(/\s+/).filter(id=>id&&id!=='quest-tooltip');
    if(ids.length)QuestHelp.anchor.setAttribute('aria-describedby',ids.join(' '));else QuestHelp.anchor.removeAttribute('aria-describedby');
  }
  QuestHelp.anchor=null;QuestHelp.row=null;
}
function positionQuestHelp(){
  const anchor=QuestHelp.anchor,tip=$('#quest-tooltip');
  if(!anchor?.isConnected||S.page!=='quests'||QuestUI.view!=='library')return hideQuestHelp();
  const rect=anchor.getBoundingClientRect(),edge=12,gap=10,w=document.documentElement.clientWidth,h=window.innerHeight;
  tip.style.maxHeight=Math.max(80,Math.min(510,h-edge*2))+'px';
  let box=tip.getBoundingClientRect(),left=rect.right+gap,top=rect.top;
  if(left+box.width>w-edge)left=rect.left-box.width-gap;
  if(left<edge){
    left=rect.left;
    const below=h-edge-rect.bottom-gap,above=rect.top-edge-gap,down=below>=box.height||below>=above;
    tip.style.maxHeight=Math.max(80,Math.min(510,down?below:above))+'px';
    box=tip.getBoundingClientRect();top=down?rect.bottom+gap:rect.top-box.height-gap;
  }
  tip.style.left=Math.max(edge,Math.min(left,w-box.width-edge))+'px';
  tip.style.top=Math.max(edge,Math.min(top,h-box.height-edge))+'px';
}
function questHelpContent(data){
  return `<div class="quest-help-heading"><span class="pill">QUEST DETAILS</span><strong>${esc(data.title)}</strong></div><p class="item-help-text">${esc(data.summary)}</p>${data.facts.length?`<dl class="quest-help-facts">${data.facts.map(([label,value])=>`<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl>`:''}${data.notes.map(note=>`<p class="quest-help-note">${esc(note)}</p>`).join('')}<div class="item-help-source">${esc(data.source)}</div>`;
}
async function showQuestHelp(row,force=false){
  if(S.page!=='quests'||QuestUI.view!=='library')return;
  if(QuestHelp.dismissed===row&&!force)return;
  QuestHelp.dismissed=null;
  clearTimeout(QuestHelp.timer);
  const anchor=$('.quest-help-title',row),tip=$('#quest-tooltip');if(!anchor)return;
  if(QuestHelp.anchor===anchor&&!tip.hidden)return positionQuestHelp();
  hideQuestHelp();hideItemHelp();QuestHelp.anchor=anchor;QuestHelp.row=row;
  const request=++QuestHelp.request,id=row.dataset.helpQuest,key=questScope()+':'+id;
  const title=$('h3',row).textContent.replace(/\s*ⓘ\s*$/,'');
  tip.innerHTML=`<div class="quest-help-heading"><strong>${esc(title)}</strong></div><p class="item-help-text" role="status">Reading quest details…</p>`;
  const ids=(anchor.getAttribute('aria-describedby')||'').split(/\s+/).filter(Boolean);ids.push('quest-tooltip');anchor.setAttribute('aria-describedby',[...new Set(ids)].join(' '));
  tip.hidden=false;tip.showPopover();positionQuestHelp();
  try{
    let cached=QuestHelp.cache.get(key);
    if(!cached||Date.now()-cached.at>30000){cached={at:Date.now(),promise:api('/api/quest-help?id='+encodeURIComponent(id))};QuestHelp.cache.set(key,cached)}
    const data=await cached.promise;
    if(request!==QuestHelp.request||QuestHelp.anchor!==anchor||!anchor.isConnected)return;
    tip.innerHTML=questHelpContent(data);positionQuestHelp();
  }catch(error){
    QuestHelp.cache.delete(key);
    if(request!==QuestHelp.request||QuestHelp.anchor!==anchor)return;
    tip.innerHTML=`<div class="quest-help-heading"><strong>${esc(title)}</strong></div><p class="item-help-text">Quest details could not be loaded. Move away and hover again to retry.</p>`;positionQuestHelp();
  }
}
function scheduleHideQuestHelp(){
  clearTimeout(QuestHelp.timer);
  QuestHelp.timer=setTimeout(()=>{
    const tip=$('#quest-tooltip');
    if(!tip?.matches(':hover')&&!QuestHelp.row?.matches(':hover')&&!QuestHelp.row?.contains(document.activeElement))hideQuestHelp();
  },160);
}
document.addEventListener('pointerover',e=>{const row=e.target.closest?.('[data-help-quest]');if(row)showQuestHelp(row)});
document.addEventListener('pointerout',e=>{const row=e.target.closest?.('[data-help-quest]');if(row&&!row.contains(e.relatedTarget)){if(QuestHelp.dismissed===row&&!$('#quest-tooltip')?.contains(e.relatedTarget))QuestHelp.dismissed=null;scheduleHideQuestHelp()}});
document.addEventListener('focusin',e=>{const row=e.target.closest?.('[data-help-quest]');if(row)showQuestHelp(row,true);else if(!$('#quest-tooltip')?.contains(e.target))hideQuestHelp()});
document.addEventListener('focusout',e=>{if(e.target.closest?.('[data-help-quest]'))scheduleHideQuestHelp()});
document.addEventListener('click',e=>{const title=e.target.closest?.('.quest-help-title');if(title)showQuestHelp(title.closest('[data-help-quest]'),true)});
document.addEventListener('pointerdown',e=>{if(!e.target.closest?.('[data-help-quest],#quest-tooltip'))hideQuestHelp()});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#quest-tooltip')?.hidden){e.preventDefault();e.stopImmediatePropagation();QuestHelp.dismissed=QuestHelp.row;hideQuestHelp()}},true);
document.addEventListener('scroll',e=>{if(QuestHelp.anchor&&!$('#quest-tooltip')?.contains(e.target))hideQuestHelp()},true);
window.addEventListener('resize',hideQuestHelp);
$('#quest-tooltip').addEventListener('pointerenter',()=>clearTimeout(QuestHelp.timer));
$('#quest-tooltip').addEventListener('pointerleave',scheduleHideQuestHelp);
