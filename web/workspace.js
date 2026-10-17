'use strict';
const WUI={info:null,activeSet:null,cache:new Map(),timers:new Map(),pending:new Map(),restoring:false,report:null,updatePoll:null};
const wDate=at=>at?new Date(at*1000).toLocaleString('en-GB'):'Not recorded';
const wPrefix=()=>`metin2-studio:${S.data.root}:`;
function draftIdentity(){
  const scope=WUI.activeSet||'direct';
  if(S.page==='drops'&&S.group)return `${scope}:drops:${S.group.source}|${S.group.key}`;
  if(S.page==='quests'&&QuestUI.view==='builder')return QuestUI.activeDraft||`${scope}:quests:editor`;
  if(S.page==='quests'&&QuestUI.view==='source'&&S.file)return `${scope}:files:${S.file.id}`;
  if(S.page==='quests'&&QuestUI.view==='guided'&&NativeQuest.model)return `${scope}:native:${NativeQuest.model.id}`;
  if(S.page==='crafting'&&S.recipe)return `${scope}:crafting:${S.recipe.source}|${S.recipe.index}${S.recipe.system==='native'?'|'+S.recipe.window:''}`;
  if(S.page==='settings'&&S.settings)return `${scope}:settings`;
  if(S.page==='files'&&S.file)return `${scope}:files:${S.file.id}`;
  return null;
}
function workspaceDraft(){
  const id=draftIdentity();if(!id)return null;
  let payload,title,kind=S.page;
  if(S.page==='drops'){payload={group:S.group};title=S.group.name}
  if(S.page==='quests'&&QuestUI.view==='builder'){payload={quest:S.quest};title=S.quest.title}
  if(S.page==='quests'&&QuestUI.view==='source'){payload={file:{...S.file,text:$('#file-text')?.value??S.file.text}};title=S.file.id;kind='files'}
  if(S.page==='quests'&&QuestUI.view==='guided'){payload={quest:{native:true,model:NativeQuest.model,values:NativeQuest.values,title:NativeQuest.title}};title=NativeQuest.title;kind='quests'}
  if(S.page==='crafting'){payload={recipe:S.recipe};title=S.recipe.name}
  if(S.page==='settings'){payload={settings:S.settings};title='World settings'}
  if(S.page==='files'){payload={file:{...S.file,text:$('#file-text')?.value??S.file.text}};title=S.file.id.split('/').at(-1)}
  return {id,kind,title,payload:structuredClone({...payload,changeset:WUI.activeSet}),updated:Date.now()/1000};
}
function workspaceStash(){
  if(!S.dirty||WUI.restoring)return true;
  const draft=workspaceDraft();if(!draft)return true;
  WUI.cache.set(draft.id,draft);
  let local=true;try{localStorage.setItem(wPrefix()+'draft:'+draft.id,JSON.stringify(draft))}catch(error){local=false}
  clearTimeout(WUI.timers.get(draft.id));
  WUI.timers.set(draft.id,setTimeout(()=>saveWorkspaceDraft(draft),450));
  const label=$('#draft-status');if(label)label.textContent=local?'Draft preserved on this computer':'Saving draft to Studio…';
  if(!local&&!draft.remoteSaved){saveWorkspaceDraft(draft);toast('Studio is preserving this draft. Try switching again once it is saved.');return false}
  return true;
}
async function saveWorkspaceDraft(draft){
  clearTimeout(WUI.timers.get(draft.id));WUI.timers.delete(draft.id);
  const previous=WUI.pending.get(draft.id);
  const request=(async()=>{if(previous)await previous.catch(()=>{});await api('/api/drafts/save',draft);const cached=WUI.cache.get(draft.id);if(cached?.updated===draft.updated)cached.remoteSaved=true;const label=$('#draft-status');if(label)label.textContent='Draft saved in Studio';})();
  WUI.pending.set(draft.id,request);
  try{await request}catch(error){const label=$('#draft-status');if(label)label.textContent='Local draft retained · Studio copy could not be saved'}
  finally{if(WUI.pending.get(draft.id)===request)WUI.pending.delete(draft.id)}
}
async function workspaceFlush(){
  for(const id of [...WUI.timers.keys()]){clearTimeout(WUI.timers.get(id));WUI.timers.delete(id);const draft=WUI.cache.get(id);if(draft)await saveWorkspaceDraft(draft)}
  await Promise.allSettled([...WUI.pending.values()]);
}
async function workspaceDraftFor(id){
  let local=WUI.cache.get(id);
  if(!local){try{local=JSON.parse(localStorage.getItem(wPrefix()+'draft:'+id)||'null')}catch(error){}}
  let remote;try{remote=await api('/api/drafts?id='+encodeURIComponent(id))}catch(error){}
  const draft=!local||remote&&remote.updated>local.updated?remote:local;
  if(draft)WUI.cache.set(id,draft);
  return draft;
}
async function workspaceRestore(){
  const id=draftIdentity();if(!id||S.dirty||WUI.restoring)return;
  const draft=await workspaceDraftFor(id);if(!draft||draftIdentity()!==id||S.dirty)return;
  applyWorkspaceDraft(draft);
}
function applyWorkspaceDraft(draft){
  WUI.restoring=true;
  try{
    if(draft.kind==='drops'){S.group=draft.payload.group;S.selected=S.group.source+'|'+S.group.key;renderGroupList();renderDropDetail()}
    if(draft.kind==='quests'){const q=draft.payload.quest;if(q.native){NativeQuest.model=q.model;NativeQuest.values=q.values;NativeQuest.title=q.title;renderNativeQuest()}else{S.quest=q;QuestUI.activeDraft=draft.id;renderQuestBuilder()}}
    if(draft.kind==='crafting'){S.recipe=draft.payload.recipe;renderRecipeDetail();renderRecipeList()}
    if(draft.kind==='settings'){S.settings=draft.payload.settings;renderSettings()}
    if(draft.kind==='files'){S.file=draft.payload.file;if(S.page==='quests'){QuestUI.sourceTitle=S.file.id.split('/').pop();renderQuestSource()}else{renderFileDetail();renderFileList()}}
    dirty(true);const label=$('#draft-status');if(label)label.textContent='Restored draft · game files unchanged';
  }finally{WUI.restoring=false}
}
async function workspaceForget(id=draftIdentity()){
  if(!id)return;clearTimeout(WUI.timers.get(id));WUI.timers.delete(id);
  const pending=WUI.pending.get(id);if(pending)await pending.catch(()=>{});
  await api('/api/drafts/delete',{id});WUI.cache.delete(id);localStorage.removeItem(wPrefix()+'draft:'+id);
  if($('#draft-status'))$('#draft-status').textContent='';
}
async function workspaceRefresh(){
  WUI.info=await api('/api/workspace');
  if(WUI.activeSet&&!WUI.info.changesets.some(row=>row.id===WUI.activeSet&&row.status==='draft'))WUI.activeSet=null;
  const control=$('#workspace-set');
  if(control)control.innerHTML='<option value="">Save directly after review</option>'+WUI.info.changesets.filter(row=>row.status==='draft').map(row=>`<option value="${esc(row.id)}" ${row.id===WUI.activeSet?'selected':''}>${esc(row.name)} · ${row.files} files</option>`).join('');
  const label=$('#workspace-context');if(label)label.textContent=WUI.activeSet?'Changes stay staged until you review and save the whole set.':'Edits are preserved as drafts. Saving and applying remain separate.';
  refreshApplyControl();
  return WUI.info;
}
function refreshApplyControl(){
  const info=WUI.info,running=S.status?.job.status==='running';
  const files=info?.pending.length||0,packageUpdate=!!info?.preferences.nativeUpdatePending,count=files+Number(packageUpdate);
  const button=$('#apply-button');
  button.disabled=!info||(!count&&!running);
  button.textContent=running?'Applying changes…':count?`Apply changes (${count})`:'No pending changes (0)';
  button.title=count?`${files} saved ${files===1?'file':'files'}${packageUpdate?' and 1 game package update':''} awaiting Apply. Review before restarting.`:info?.deploymentKnown?'All saved changes match the last verified deployment. Drafts are excluded.':'No saved changes await Apply. Studio has not verified a deployment for this installation yet. Drafts are excluded.';
  if($('#apply-dialog').open){
    $('#apply-pending').innerHTML=`<p><strong>${count} pending ${count===1?'change':'changes'}</strong> · ${files} saved ${files===1?'file':'files'}${packageUpdate?' + 1 game package update':''}. ${info?.drafts.length||0} preserved drafts are excluded.</p>${packageUpdate?'<p>The game package update uses the native full-stack build.</p>':''}${!count?'<p>Nothing to apply. The server will not be restarted.</p>':''}${(info?.pending||[]).map(row=>`<div class="path">${esc(row.path)}</div>`).join('')}`;
    $('#run-apply').disabled=!count||!S.status?.docker.available||running;
    $('#run-validate').disabled=!S.status?.docker.available||running;
  }
}
async function initWorkspace(){
  try{WUI.activeSet=localStorage.getItem(wPrefix()+'active-set')||null}catch(error){}
  $('.topbar').insertAdjacentHTML('afterend',`<div class="workspace-ribbon"><div><label for="workspace-set">Working change set</label><select id="workspace-set"></select><button class="button small" id="workspace-board">Drafts &amp; changes</button></div><span id="workspace-context"></span><small id="draft-status" role="status"></small></div>`);
  await workspaceRefresh();
  $('#workspace-board').addEventListener('click',()=>navigate('changes'));
  $('#workspace-set').addEventListener('change',async e=>{
    if(!leaveOkay()){e.target.value=WUI.activeSet||'';return}await workspaceFlush();
    WUI.activeSet=e.target.value||null;localStorage.setItem(wPrefix()+'active-set',WUI.activeSet||'');dirty(false);
    S.data.groups=(await api('/api/bootstrap')).groups;await workspaceRefresh();await navigate(S.route||S.page,{reload:true});
  });
  window.addEventListener('beforeunload',()=>workspaceStash());
}
async function resumeWorkspaceDraft(id){
  const draft=await workspaceDraftFor(id);if(!draft)return toast('This draft is no longer available.',true);
  if(!leaveOkay())return;await workspaceFlush();
  dirty(false);
  WUI.activeSet=draft.payload.changeset||null;localStorage.setItem(wPrefix()+'active-set',WUI.activeSet||'');await workspaceRefresh();
  await navigate(draft.kind==='quests'||draft.kind==='files'&&draft.payload.file.id.endsWith('.quest')?'quests':draft.kind==='files'?'files/all':draft.kind==='settings'?'settings/all':draft.kind);applyWorkspaceDraft(draft);
}
async function renderChanges(){
  const info=await workspaceRefresh();
  $('#content').innerHTML=head('YOUR WORKSPACE','Drafts & changes','Preserve unfinished work, group related edits and review exactly what will be saved.')+
    `<div class="work-grid"><section class="panel"><div class="panel-header"><h2>New change set</h2></div><form id="changeset-form" class="work-form"><label for="changeset-name">Name</label><input id="changeset-name" maxlength="120" required placeholder="Protection scroll rebalance"><label for="changeset-note">Purpose and expected result</label><textarea id="changeset-note" maxlength="1500" rows="3" placeholder="Which targets, recipes and quests belong together?"></textarea><button class="button primary">Create change set</button><small>A change set holds reviewed edits without changing game files. Save the complete set when ready.</small></form></section>
    <section class="panel"><div class="panel-header"><h2>Saved changes awaiting apply</h2><span>${info.pending.length} tracked files</span></div><div class="work-body">${!info.deploymentKnown?'<p class="notice info">No successful Studio deployment has been recorded. The running configuration has not been verified.</p>':''}${info.pending.map(row=>`<p><code>${esc(row.path)}</code>${row.changedOutsideStudio?'<span class="pill">Changed outside Studio</span>':''}</p>`).join('')||'<p class="muted">No tracked file differences from the last recorded deployment.</p>'}<button class="button" id="changes-updates">Review update protection</button></div></section></div>
    <section class="panel work-section"><div class="panel-header"><h2>Change sets</h2><span>${info.changesets.length}</span></div><div class="work-list">${info.changesets.map(row=>`<article><div><strong>${esc(row.name)}</strong><p>${esc(row.note)}</p><small>${row.files} files · ${esc(row.status)} · ${wDate(row.updated)}</small></div><div class="work-actions">${row.status==='draft'?`<button class="button small" data-work-on="${row.id}">Work in this set</button><button class="button small" data-rebase-set="${row.id}">Review against current files</button><button class="button primary small" data-publish-set="${row.id}" ${row.files?'':'disabled'}>Review complete set</button>`:'<span class="pill">Saved to game files</span>'}</div></article>`).join('')||'<div class="empty">Create a named set to combine drops, recipes, quests and settings.</div>'}</div></section>
    <section class="panel work-section"><div class="panel-header"><h2>Preserved editor drafts</h2><span>${info.drafts.length}</span></div><div class="work-list">${info.drafts.map(row=>`<article><div><strong>${esc(row.title)}</strong><p>${esc(titles[row.kind]||row.kind)} · ${wDate(row.updated)}</p></div><div class="work-actions"><button class="button small" data-resume-draft="${esc(row.id)}">Resume</button><button class="button small" data-recover-draft="${esc(row.id)}">Recover to change set</button><button class="button ghost small" data-delete-draft="${esc(row.id)}">Discard draft</button></div></article>`).join('')||'<div class="empty">Drafts appear here as you edit. They do not affect the game.</div>'}</div></section>`;
  $('#changeset-form').addEventListener('submit',e=>{e.preventDefault();attempt(async()=>{const row=await api('/api/changesets/create',{name:$('#changeset-name').value,note:$('#changeset-note').value});WUI.activeSet=row.id;localStorage.setItem(wPrefix()+'active-set',row.id);await renderChanges();toast('Change set created. Choose an editor to add changes.')})});
  $('#changes-updates').addEventListener('click',()=>navigate('updates'));
  $$('[data-work-on]').forEach(button=>button.addEventListener('click',()=>attempt(async()=>{WUI.activeSet=button.dataset.workOn;localStorage.setItem(wPrefix()+'active-set',WUI.activeSet);S.data.groups=(await api('/api/bootstrap')).groups;await workspaceRefresh();toast('Working in the selected change set.')})));
  $$('[data-rebase-set]').forEach(button=>button.onclick=()=>attempt(async()=>{const report=await api('/api/changesets/review-update',{id:button.dataset.rebaseSet});toolDialog('Review staged work against current files','<div id="update-report"></div>');renderUpdateReport(report);$('#reconcile-custom').disabled=false;$('#reconcile-custom').textContent='Rebase staged changes';$('#reconcile-custom').replaceWith($('#reconcile-custom').cloneNode(true));$('#reconcile-custom').onclick=()=>attempt(async()=>{await api('/api/changesets/rebase',{id:report.id,decisions:updateChoices()});$('#tool-dialog').close();await renderChanges();toast('Staged work rebased. Game files are unchanged. Review the complete set before saving.')})}));
  $$('[data-recover-draft]').forEach(button=>button.onclick=()=>attempt(async()=>{await api('/api/drafts/to-set',{id:button.dataset.recoverDraft});await renderChanges();toast('Draft copied into a change set. Review it against current files before publishing.')}));
  $$('[data-publish-set]').forEach(button=>button.addEventListener('click',()=>preview('/api/changesets/preview',{id:button.dataset.publishSet})));
  $$('[data-resume-draft]').forEach(button=>button.addEventListener('click',()=>attempt(()=>resumeWorkspaceDraft(button.dataset.resumeDraft))));
  $$('[data-delete-draft]').forEach(button=>button.addEventListener('click',()=>attempt(async()=>{await workspaceForget(button.dataset.deleteDraft);await renderChanges()})));
}
function updateChoices(){
  const decisions={};$$('[data-custom-choice]').forEach(select=>{if(select.value)decisions[select.dataset.customChoice]=select.value});return decisions;
}
function renderUpdateReport(report){
  WUI.report=report;
  const pack=report.package;
  $('#update-report').innerHTML=`<div class="work-report-heading"><div><h2>${pack?'Package '+esc(pack.version):'Installed file changes'}</h2><p>${report.affectedFiles} affected files · ${report.conflicts} conflicting custom changes · ${report.trackedFiles} tracked files</p></div><button class="button small" id="update-export">Download report</button></div>${pack?`<p class="notice ${pack.verified?'info':''}">${pack.files} package files · ${pack.verified?'SHA-256 matched the supplied release checksum':'Preview only: import with the published SHA-256 to enable installation'} · ${esc(pack.kind)} package</p>`:''}
    <p class="work-help">${esc(report.scope)}</p>${report.files.map(file=>`<section class="work-conflict-file"><h3>${esc(file.path)}</h3>${file.choices.map(row=>`<article class="work-conflict ${row.conflict?'needs-choice':''}"><div class="work-conflict-title"><strong>${row.conflict?'Choose a value':'Custom value retained by default'}</strong><small>Original version ${esc(file.originalVersion)} · line ${row.line}</small></div><pre class="work-context">${esc(row.context)}</pre><div class="work-three">${[['Original',row.original],['Your custom value',row.custom],['Incoming update',row.incoming]].map(([label,value])=>`<div><span>${label}</span><pre>${value===null?'(not present)':esc(value)}</pre></div>`).join('')}</div><label class="work-choice">Decision<select data-custom-choice="${row.id}" aria-label="Decision for custom change on line ${row.line}">${row.conflict?'<option value="">Choose…</option>':''}<option value="keep">Keep my custom value</option><option value="update">Use update value</option></select></label></article>`).join('')}</section>`).join('')||'<div class="empty">No incoming changes affect tracked custom entries. Unrelated update changes need no individual approval.</div>'}
    <div class="work-actions work-report-actions">${pack?`<button id="install-reviewed-update" class="button primary" ${pack.verified?'':'disabled'}>Review package installation</button>`:`<button id="reconcile-custom" class="button primary" ${report.affectedFiles?'':'disabled'}>Review selected merge</button>`}</div>`;
  $('#update-export').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify({...report,decisions:updateChoices()},null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download=`metin2-custom-update-review-${Date.now()}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
  $('#reconcile-custom')?.addEventListener('click',()=>preview('/api/customisations/preview',{id:report.id,decisions:updateChoices()}));
  $('#install-reviewed-update')?.addEventListener('click',()=>{
    if($$('[data-custom-choice]').some(select=>!select.value))return toast('Choose Keep custom or Use update for each conflict.',true);
    const dialog=$('#update-install-dialog');$('#update-install-summary').textContent=`Install ${pack.version}: ${pack.files} package files, ${report.affectedFiles} files with custom decisions. The native updater creates its normal backups. Selected custom values are restored before any build. Apply to server is a separate action.`;
    $('#confirm-update-install').onclick=()=>attempt(async()=>{const result=await api('/api/updates/install',{id:report.id,decisions:updateChoices()});dialog.close();$('#update-operation').textContent=result.message;pollUpdateOperation()});dialog.showModal();
  });
}
async function pollUpdateOperation(){
  clearTimeout(WUI.updatePoll);
  try{const job=await api('/api/updates/status');if(S.page!=='updates')return;$('#update-operation').textContent=job.message||'No update operation running.';if(job.report)renderUpdateReport(job.report);if(job.status==='running')WUI.updatePoll=setTimeout(pollUpdateOperation,2000);if(job.requiresReload){$('#update-operation').insertAdjacentHTML('beforeend',' <button class="button small" id="reload-after-package">Reload Studio catalog</button>');$('#reload-after-package').onclick=()=>attempt(async()=>{await api('/api/catalog/reload',{});location.reload()})}}catch(error){if($('#update-operation'))$('#update-operation').textContent=error.message}
}
async function renderUpdates(){
  await workspaceRefresh();
  $('#content').innerHTML=head('KEEP YOUR CUSTOM WORK','Update protection','Review only updates that overlap your custom changes. Original, custom and incoming values stay separate.')+
    `<div class="notice info">Studio stores originals and custom changes outside the game installation. Use this page for a review before package installation. Updates launched elsewhere bypass that preview; Scan installed files can detect and recover tracked custom entries afterward.</div>
    <div class="work-grid"><section class="panel"><div class="panel-header"><h2>Review installed changes</h2></div><div class="work-body"><p>Track changes as you save through Studio. A scan leaves game files untouched.</p><button class="button primary" id="scan-customisations">Scan installed files</button><p class="work-help">${WUI.info.tracked.length} tracked files. Earlier edits made outside Studio need an original backup before they can be identified reliably.</p></div></section>
    <section class="panel"><div class="panel-header"><h2>Preview a game update</h2></div><div class="work-body"><div class="work-actions"><button class="button" id="check-official-update">Check official release</button><button class="button" id="download-official-update" disabled>Download &amp; preview</button></div><p id="official-offer" class="work-help">Uses this installation’s ordinary/protected server channel.</p><form id="update-upload" class="work-form"><label for="update-zip">Or import the server update ZIP</label><input id="update-zip" type="file" accept=".zip,application/zip" required><label for="update-sha">Published SHA-256</label><input id="update-sha" pattern="[a-fA-F0-9]{64}" placeholder="Required to install; optional for preview"><button class="button">Upload &amp; preview custom differences</button></form></div></section></div>
    <p id="update-operation" class="notice" role="status">No update operation running.</p><section class="panel work-update-report" id="update-report"><div class="empty">Scan installed files or preview a package to see affected custom changes.</div></section>`;
  $('#scan-customisations').onclick=()=>attempt(async()=>renderUpdateReport(await api('/api/customisations')));
  $('#check-official-update').onclick=()=>attempt(async()=>{const button=$('#check-official-update');button.disabled=true;$('#official-offer').textContent='Checking the official manifest…';try{const offer=await api('/api/updates/available');$('#official-offer').textContent=`Release ${offer.version} · ${offer.kind} · checksum available`;$('#download-official-update').disabled=false}finally{button.disabled=false}});
  $('#download-official-update').onclick=()=>attempt(async()=>{await api('/api/updates/download',{});pollUpdateOperation()});
  $('#update-upload').onsubmit=e=>{e.preventDefault();attempt(async()=>{const file=$('#update-zip').files[0];if(!file)return;const button=$('#update-upload button');button.disabled=true;$('#update-operation').textContent='Uploading and checking '+file.name+'…';try{const response=await fetch('/api/updates/package',{method:'POST',headers:{'Content-Type':'application/zip','X-Studio-Token':S.data.token,'X-Package-SHA256':$('#update-sha').value.trim()},body:file});const data=await response.json();if(!response.ok)throw new Error(data.error||'Package preview failed.');renderUpdateReport(data);$('#update-operation').textContent='Package staged. No installed game files changed.'}finally{button.disabled=false}})};
  await pollUpdateOperation();
}
function renderWorkspaceOverview(){
  const info=WUI.info||{drafts:[],pending:[],tracked:[],changesets:[],recent:[]},c=S.data.counts;
  $('#content').innerHTML=head('YOUR SERVER WORKSPACE','Your world, under control.','Pick up unfinished work, review custom changes and track what has been applied.','<button class="button" data-go="updates">Review update protection ↗</button>')+
    `<div class="stats">${[[info.drafts.length,'Preserved drafts','Unfinished editor work'],[info.changesets.filter(row=>row.status==='draft').length,'Open change sets','Related changes reviewed together'],[info.pending.length,'Files awaiting apply',info.deploymentKnown?'Since the last Studio deployment':'Deployment state not yet recorded'],[info.tracked.length,'Protected custom files','Originals retained outside the game']].map(([n,label,hint])=>`<div class="stat"><div class="stat-label">${label}</div><strong>${fmt(n)}</strong><small>${hint}</small></div>`).join('')}</div>
    <div class="work-grid work-section"><section class="panel"><div class="panel-header"><h2>Continue your work</h2><button class="subtle-link" data-go="changes">All drafts &amp; changes ↗</button></div><div class="work-list">${info.drafts.slice(0,4).map(row=>`<article><div><strong>${esc(row.title)}</strong><p>${esc(titles[row.kind])} · ${wDate(row.updated)}</p></div><button class="button small" data-home-draft="${esc(row.id)}">Resume</button></article>`).join('')||'<div class="empty">Choose an editor to begin. Drafts are preserved as you work.</div>'}</div></section>
    <section class="panel"><div class="panel-header"><h2>Recent activity</h2></div><div class="work-list">${info.recent.slice(0,5).map(row=>`<article><div><strong>${esc(row.title)}</strong><p>${esc(row.kind)} · ${wDate(row.at)}</p></div></article>`).join('')||'<div class="empty">Studio saves, staged changes and apply results will appear here.</div>'}</div></section></div>
    <div class="quick-grid work-section"><article class="feature-card"><div class="mini-label">LOOT &amp; REWARDS</div><h2>Shape the rewards.</h2><p>Compare targets and inspect shared pools before changing the loot.</p><button class="button primary" data-go="drops">Open drop editor ↗</button></article><article class="feature-card secondary"><div class="mini-label">STORIES &amp; PROGRESSION</div><h2>Build an adventure.</h2><p>Manage quests and crafting alongside the items they use.</p><div class="work-actions"><button class="button" data-go="quests">Browse quests ↗</button><button class="button" data-go="crafting">Crafting ↗</button></div></article></div>
    <details class="panel work-catalog"><summary>Installed catalog · ${fmt(c.items)} items · ${fmt(c.mobs)} targets · ${fmt(c.files)} files</summary><p>Version ${esc(S.data.version)}. Catalog and source definitions can differ from the running database. Docker availability alone does not verify game health.</p><div class="work-actions"><button class="button" data-go="settings">World settings</button><button class="button" data-go="files">Config library</button><button class="button" data-go="economy">Economy</button></div></details>`;
  bindNavigation();$$('[data-home-draft]').forEach(button=>button.onclick=()=>attempt(()=>resumeWorkspaceDraft(button.dataset.homeDraft)));
}

const baseUpdatesPage=renderUpdates;
renderUpdates=async function(){await baseUpdatesPage();const pending=(await workspaceRefresh()).preferences.nativeUpdatePending;if(pending&&!pending.ready){$('#update-operation').insertAdjacentHTML('afterend','<p class="notice">A native package was installed but custom restoration did not finish. Scan installed files, review the choices and save the selected merge. Then verify recovery before Apply.</p><button class="button" id="finish-update-recovery">Verify custom recovery</button>');$('#finish-update-recovery').onclick=()=>attempt(async()=>{await api('/api/updates/recovery',{});await renderUpdates();toast('Custom recovery verified. Apply the pending native build when ready.')})}};

const recoverableUpdatesPage=renderUpdates;
renderUpdates=async function(){await recoverableUpdatesPage();$('#update-operation').insertAdjacentHTML('afterend','<div class="editor-actions"><button class="button" id="adopt-custom-file">Track an existing edit from its original backup</button><small>Earlier manual edits need an original file to identify your custom differences. New Studio saves are tracked automatically.</small></div>');$('#adopt-custom-file').onclick=()=>attempt(async()=>{const paths=await api('/api/customisations/adopt-sources');toolDialog('Track existing configuration edits',`<p>Choose the current file and its unmodified original backup. Review the differences before registering them. Game files are unchanged.</p><label>Current configuration<select id="adopt-path" class="wide-input">${paths.map(path=>`<option>${esc(path)}</option>`).join('')}</select></label><label>Original backup file<input id="adopt-original" type="file"></label><button class="button primary" id="adopt-review">Review custom differences</button>`);$('#adopt-review').onclick=()=>attempt(async()=>{const file=$('#adopt-original').files[0];if(!file||file.size>2000000)throw new Error('Choose an original backup under 2 MB.');const bytes=new Uint8Array(await file.arrayBuffer());let raw='';for(const byte of bytes)raw+=String.fromCharCode(byte);const body={path:$('#adopt-path').value,original:btoa(raw)};$('#tool-dialog').close();await preview('/api/customisations/adopt',body)})})};
