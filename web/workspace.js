'use strict';
const WUI={info:null,activeSet:null,cache:new Map(),timers:new Map(),pending:new Map(),restoring:false,report:null,updatePoll:null};
const ApplyUI={jobId:null,starting:'',loading:false,connectionFailed:false,error:''};
const OperationUI={dismissed:null,scope:null,timer:null,signature:''};
function operationJob(){
  const job=S.status?.job;
  if(job?.id&&job.status!=='idle')return job;
  const saved=WUI.info?.lastDeployment;
  return saved?{...saved.payload,id:saved.id,status:saved.status,started:saved.started,finished:saved.finished}:{};
}
function operationMarkup(view,job,compact=false){
  const labels={complete:'Complete',running:'In progress',pending:'Waiting',blocked:'Not reached',failed:'Failed',warning:'Needs verification'};
  return `<div class="operation-summary"><div class="operation-copy"><div class="eyebrow">${esc(view.kind)}${job.started?' · '+esc(wDate(job.started)):''}</div><div role="${view.attention?'alert':'status'}" aria-live="${view.attention?'assertive':'polite'}"><strong class="operation-title">${esc(view.title)}</strong><p>${esc(view.message)}</p></div></div><span class="operation-elapsed" data-operation-elapsed data-status="${esc(job.status||'running')}" data-started="${Number(job.started)||0}" data-finished="${Number(job.finished)||0}" aria-label="Elapsed time">${esc(view.elapsed)}</span></div>${!compact&&view.steps.length?`<ol class="operation-steps" aria-label="Operation stages">${view.steps.map(step=>`<li data-state="${step.status}" ${step.status==='running'?'aria-current="step"':''}><span class="operation-step-mark" aria-hidden="true"></span><span>${esc(step.label)}<small>${labels[step.status]}</small></span></li>`).join('')}</ol>`:''}${view.active&&view.total?`<p class="operation-count">${view.stale?'Last observed: ':''}${view.complete} of ${view.total} stages complete · duration depends on the current build</p>`:''}${!compact&&view.lastLine?`<p class="operation-latest">${esc(view.lastLine)}</p>`:''}`;
}
function updateOperationElapsed(){
  $$('[data-operation-elapsed]').forEach(node=>{node.textContent=StudioOperations.elapsed({status:node.dataset.status,started:Number(node.dataset.started)||undefined,finished:Number(node.dataset.finished)||undefined})});
}
function renderOperationStatus(){
  const node=$('#operation-status');if(!node||typeof StudioOperations==='undefined')return;
  const scope='metin2-studio:'+S.data.root+':operation-dismissed';
  if(OperationUI.scope!==scope){OperationUI.scope=scope;try{OperationUI.dismissed=sessionStorage.getItem(scope)}catch(error){OperationUI.dismissed=null}}
  const job=ApplyUI.starting?{kind:ApplyUI.starting,started:ApplyUI.startedAt}:operationJob();
  const pending=(WUI.info?.pending.length||0)+Number(!!WUI.info?.preferences.nativeUpdatePending);
  const view=StudioOperations.view(job,{starting:ApplyUI.starting,pending,connectionFailed:ApplyUI.connectionFailed});
  node.hidden=(!job.id&&!ApplyUI.starting)||(!view.active&&OperationUI.dismissed===job.id);
  if(!node.hidden){
    const signature=JSON.stringify([job.id,job.status,job.progress?.current,view.title,view.message,view.tone,view.complete]);
    if(OperationUI.signature!==signature){
      OperationUI.signature=signature;node.className='operation-status operation-'+view.tone;
      node.innerHTML='<div class="operation-main">'+operationMarkup(view,job,true)+'</div>'+`<div class="operation-actions"><button class="button small" id="operation-open">${view.active?'View progress':'View result'}</button>${ApplyUI.connectionFailed?'<button class="button small" id="operation-reconnect">Reconnect</button>':''}${!view.active?'<button class="icon-button" id="operation-dismiss" aria-label="Dismiss operation result">×</button>':''}</div>`;
      $('#operation-open').onclick=()=>openApplyDialog({jobId:job.id});
      if($('#operation-reconnect'))$('#operation-reconnect').onclick=updateStatus;
      if($('#operation-dismiss'))$('#operation-dismiss').onclick=()=>{OperationUI.dismissed=job.id;try{sessionStorage.setItem(scope,job.id)}catch(error){}node.hidden=true;OperationUI.signature=''};
    }
  }
  if(view.active&&!OperationUI.timer)OperationUI.timer=setInterval(updateOperationElapsed,1000);
  if(!view.active&&OperationUI.timer){clearInterval(OperationUI.timer);OperationUI.timer=null}
  updateOperationElapsed();
}
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
  const info=WUI.info,running=S.status?.job.status==='running'||!!ApplyUI.starting;
  const files=info?.pending.length||0,packageUpdate=!!info?.preferences.nativeUpdatePending,count=files+Number(packageUpdate);
  const button=$('#apply-button');
  const recovering=!!info?.saveRecovery?.length;
  const lastJob=operationJob();
  button.disabled=!info||(!count&&!running&&!lastJob.id);
  button.textContent=running?(ApplyUI.starting==='validation'||!ApplyUI.starting&&S.status?.job.kind==='validation'?'Validating build…':'Applying server changes…'):count?`Apply to server (${count})`:'No server changes (0)';
  if(recovering){button.disabled=false;button.textContent='Save recovery required';}
  else if(running&&ApplyUI.connectionFailed)button.textContent='Check operation status';
  else if(!count&&!running&&lastJob.id)button.textContent='View last operation';
  const warning=$('#studio-recovery');
  if(warning){
    const interrupted=!!info?.interruptedDeployment||S.status?.job.status==='interrupted';
    warning.hidden=!recovering&&!interrupted;
    warning.innerHTML=recovering?'<strong>Interrupted save recovery required.</strong> Open <button class="button small" id="open-save-recovery">Drafts &amp; changes</button> to review recovery. Further saves and Apply are paused.':interrupted?'<strong>Deployment interrupted.</strong> Inspect the game launcher and any running build commands before retrying Apply. Saved changes remain pending; Studio did not restart the game automatically.':'';
    const link=$('#open-save-recovery');if(link)link.onclick=()=>navigate('changes');
  }
  button.title=count?`${files} saved ${files===1?'file':'files'}${packageUpdate?' and 1 game package update':''} awaiting Apply. Review before restarting.`:info?.deploymentKnown?'All saved changes match the last verified deployment. Drafts are excluded.':'No saved changes await Apply. Studio has not verified a deployment for this installation yet. Drafts are excluded.';
  if($('#apply-dialog').open){
    $('#apply-pending').innerHTML=`<p><strong>${count} pending ${count===1?'change':'changes'}</strong> · ${files} saved ${files===1?'file':'files'}${packageUpdate?' + 1 game package update':''}. ${info?.drafts.length||0} preserved drafts are excluded.</p>${packageUpdate?'<p>The game package update uses the native full-stack build.</p>':''}${!count?'<p>Nothing to apply. The server will not be restarted.</p>':''}${(info?.pending||[]).map(row=>`<div class="path">${esc(row.path)}</div>`).join('')}`;
    renderApplyDialog();
  }
  renderOperationStatus();
}

function applyOperationTitle(job){
  const kind=job.kind==='validation'||job.status==='validated'?'Validation':'Apply';
  const result={running:'in progress',validated:'passed (validation only)',succeeded:'completed',unverified:'needs verification',failed:'failed',interrupted:'interrupted'}[job.status]??job.status;
  return `${kind} · ${result}`;
}

function applyOperationMessage(job){
  if(job.status==='interrupted')return 'Studio closed before this operation finished. Inspect the game launcher and any running build commands before retrying. Deployment is unverified and saved changes remain pending; no automatic restart or retry was performed.';
  if(job.kind==='validation'||job.status==='validated')return job.status==='validated'?'Build and compilation passed. Validation did not apply changes or restart the game.':job.status==='running'?'Checking the build without applying changes or restarting the game.':'Validation did not deploy changes. Inspect its log.';
  if(job.status==='succeeded')return 'This Apply completed and was verified. Check the current pending changes above for any newer saves.';
  if(job.status==='unverified')return 'Commands completed, but deployment verification is incomplete. Changes stay pending.';
  if(job.status==='failed')return 'The operation failed. Saved changes and backups are retained.';
  return 'Build, migration and restart are in progress. Pending changes clear only after verified completion.';
}

function renderApplyDialog(){
  if(!$('#apply-dialog').open)return;
  const latest=operationJob();
  const info=WUI.info,job=latest.id&&latest.id===ApplyUI.jobId?latest:S.status?.job??{},running=job.status==='running';
  const count=(info?.pending.length??0)+Number(!!info?.preferences.nativeUpdatePending);
  const validation=ApplyUI.starting==='validation'||!ApplyUI.starting&&job.kind==='validation';
  const interrupted=info?.interruptedDeployment;
  const acknowledgement=$('#apply-interrupted-ack');
  if(ApplyUI.interruptedId!==interrupted?.id){acknowledgement.checked=false;ApplyUI.interruptedId=interrupted?.id;}
  $('#apply-interrupted-check').hidden=!interrupted;
  if(running)ApplyUI.jobId=job.id;
  let title=count?`${count} ${count===1?'change is':'changes are'} still not applied`:'No saved changes awaiting Apply';
  let text=count?'Use Build & restart to load these saved changes. Validate build only checks compilation and leaves them pending.':'There are no saved changes waiting to be applied. Validation is optional and does not deploy anything.';
  if(ApplyUI.loading){title='Checking saved changes…';text='Refreshing the pending list and server status.';}
  else if(ApplyUI.starting){title=validation?'Starting validation only…':'Starting Apply…';text=validation?'This will check the build. Saved changes will remain pending.':'Waiting for the server operation to start.';}
  else if(running){title=validation?'Validation in progress — changes are not being applied':'Applying saved changes…';text=applyOperationMessage(job);}
  else if(info?.saveRecovery?.length){title='Interrupted save recovery required';text='Open Drafts & changes and Review recovery. Saving, validation and Apply are paused until the incomplete save is resolved.';}
  else if(job.status==='interrupted'){title='Previous deployment was interrupted';text=applyOperationMessage(job);}
  else if(ApplyUI.connectionFailed)text='Server status could not be refreshed. Reopen this dialog to check before starting an operation.';
  else if(!S.status?.docker.available)text+=' Start Docker Desktop before running either operation.';
  if(interrupted&&job.status!=='interrupted'&&!running)text+=' A previous interrupted deployment still needs a verified Apply. Inspect its game/build state before acknowledging a retry below.';
  $('#apply-current-title').textContent=title;
  $('#apply-current').className='notice apply-current '+(count?'apply-current-pending':'apply-current-clean');
  $('#apply-explanation').textContent=text;
  $('#apply-error').hidden=!ApplyUI.error;
  $('#apply-error').textContent=ApplyUI.error;
  const current=!ApplyUI.loading&&!ApplyUI.starting&&(running||job.id&&job.id===ApplyUI.jobId);
  $('#apply-operation').hidden=!current;
  $('#apply-operation-title').textContent=current?applyOperationTitle(job):'';
  $('#apply-operation-result').textContent=current?applyOperationMessage(job):'';
  if(typeof StudioOperations!=='undefined'){
    const progress=$('#apply-progress'),visible=current||!!ApplyUI.starting;
    progress.hidden=!visible;$('#apply-operation').hidden=!visible;
    if(visible){
      const shown=ApplyUI.starting?{started:ApplyUI.startedAt}:job;
      const view=StudioOperations.view(shown,{starting:ApplyUI.starting,pending:count,connectionFailed:ApplyUI.connectionFailed});
      const signature=JSON.stringify([shown.id,shown.status,shown.progress,view.title,view.message,view.lastLine]);
      progress.className='operation-card operation-'+view.tone;
      if(ApplyUI.progressSignature!==signature){progress.innerHTML=operationMarkup(view,shown);ApplyUI.progressSignature=signature}
    }
  }
  const log=$('#apply-log'),follow=log.scrollHeight-log.scrollTop-log.clientHeight<40;
  $('#apply-log').hidden=!current||!job.lines?.length;
  $('#apply-log').textContent=current?(job.lines??[]).join('\n'):'';
  $('#apply-log-count').textContent=current?`(${job.lines?.length||0} lines)`:'';
  if(follow&&running)log.scrollTop=log.scrollHeight;
  if(current&&['failed','unverified','interrupted'].includes(job.status)&&ApplyUI.openedLog!==job.id){$('#apply-log-details').open=true;ApplyUI.openedLog=job.id}
  const deployed=info?.lastDeployment;
  const historical=!current&&job.status&&job.status!=='idle'&&!running?job:deployed&&deployed.id!==job.id?{...deployed.payload,id:deployed.id,status:deployed.status,started:deployed.started,finished:deployed.finished}:null;
  $('#apply-previous').hidden=ApplyUI.loading||!historical;
  $('#apply-previous-title').textContent=historical?`Previous ${applyOperationTitle(historical).toLowerCase()} · ${wDate(historical.finished??historical.started)}`:'';
  $('#apply-previous-note').textContent=historical?'This is an earlier operation. Its result does not mean newer saved changes have been applied. '+applyOperationMessage(historical):'';
  $('#apply-previous-log').textContent=historical?(historical.lines??[]).join('\n'):'';
  const blocked=ApplyUI.loading||ApplyUI.connectionFailed||!!ApplyUI.starting||running||!info||!S.status?.docker.available||!!info?.saveRecovery?.length;
  $('#run-apply').disabled=blocked||!count||!!interrupted&&!acknowledgement.checked;
  $('#run-validate').disabled=blocked;
}
async function initWorkspace(){
  try{WUI.activeSet=localStorage.getItem(wPrefix()+'active-set')||null}catch(error){}
  $('.topbar').insertAdjacentHTML('afterend',`<div class="workspace-ribbon"><div><label for="workspace-set">Working change set</label><select id="workspace-set"></select><button class="button small" id="workspace-board">Drafts &amp; changes</button></div><span id="workspace-context"></span><small id="draft-status" role="status"></small></div>`);
  $('.workspace-ribbon').insertAdjacentHTML('afterend','<div id="studio-recovery" class="notice studio-recovery" role="alert" hidden></div>');
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
    `${info.saveRecovery?.length?`<section class="panel work-section"><div class="panel-header"><h2>Interrupted save recovery</h2></div><div class="work-body"><p>Review recovery before saving or applying. Restore interrupted writes while keeping files changed since then. The original before/after backups are retained.</p>${info.saveRecovery.map(row=>`<article><h3>${esc(row.title)}</h3>${row.paths.map(path=>`<p class="path">${esc(path)}</p>`).join('')}${row.error?`<p class="notice">${esc(row.error)}</p>`:''}<button class="button" data-review-save-recovery="${esc(row.id)}" ${row.canRecover?'':'disabled'}>Review recovery</button></article>`).join('')}</div></section>`:''}`+
    `<div class="work-grid"><section class="panel"><div class="panel-header"><h2>New change set</h2></div><form id="changeset-form" class="work-form"><label for="changeset-name">Name</label><input id="changeset-name" maxlength="120" required placeholder="Protection scroll rebalance"><label for="changeset-note">Purpose and expected result</label><textarea id="changeset-note" maxlength="1500" rows="3" placeholder="Which targets, recipes and quests belong together?"></textarea><button class="button primary">Create change set</button><small>A change set holds reviewed edits without changing game files. Save the complete set when ready.</small></form></section>
    <section class="panel"><div class="panel-header"><h2>Saved changes awaiting apply</h2><span>${info.pending.length} tracked files</span></div><div class="work-body">${!info.deploymentKnown?'<p class="notice info">No successful Studio deployment has been recorded. The running configuration has not been verified.</p>':''}${info.pending.map(row=>`<p><code>${esc(row.path)}</code>${row.changedOutsideStudio?'<span class="pill">Changed outside Studio</span>':''}</p>`).join('')||'<p class="muted">No tracked file differences from the last recorded deployment.</p>'}<button class="button" id="changes-updates">Review update protection</button></div></section></div>
    <section class="panel work-section"><div class="panel-header"><h2>Change sets</h2><span>${info.changesets.length}</span></div><div class="work-list">${info.changesets.map(row=>`<article><div><strong>${esc(row.name)}</strong><p>${esc(row.note)}</p><small>${row.files} files · ${esc(row.status)} · ${wDate(row.updated)}</small></div><div class="work-actions">${row.status==='draft'?`<button class="button small" data-work-on="${row.id}">Work in this set</button><button class="button small" data-rebase-set="${row.id}">Review against current files</button><button class="button primary small" data-publish-set="${row.id}" ${row.files?'':'disabled'}>Review complete set</button>`:'<span class="pill">Saved to game files</span>'}</div></article>`).join('')||'<div class="empty">Create a named set to combine drops, recipes, quests and settings.</div>'}</div></section>
    <section class="panel work-section"><div class="panel-header"><h2>Preserved editor drafts</h2><span>${info.drafts.length}</span></div><div class="work-list">${info.drafts.map(row=>`<article><div><strong>${esc(row.title)}</strong><p>${esc(titles[row.kind]||row.kind)} · ${wDate(row.updated)}</p></div><div class="work-actions"><button class="button small" data-resume-draft="${esc(row.id)}">Resume</button><button class="button small" data-recover-draft="${esc(row.id)}">Recover to change set</button><button class="button ghost small" data-delete-draft="${esc(row.id)}">Discard draft</button></div></article>`).join('')||'<div class="empty">Drafts appear here as you edit. They do not affect the game.</div>'}</div></section>`;
  $('#changeset-form').addEventListener('submit',e=>{e.preventDefault();attempt(async()=>{const row=await api('/api/changesets/create',{name:$('#changeset-name').value,note:$('#changeset-note').value});WUI.activeSet=row.id;localStorage.setItem(wPrefix()+'active-set',row.id);await renderChanges();toast('Change set created. Choose an editor to add changes.')})});
  $('#changes-updates').addEventListener('click',()=>navigate('updates'));
  $$('[data-review-save-recovery]').forEach(button=>button.addEventListener('click',()=>preview('/api/recovery/preview',{id:button.dataset.reviewSaveRecovery})));
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
function customMergeMarkup(row,file,report){
  const gameFirst=report.kind==='package',laterMerge=report.kind==='installed';
  const title=gameFirst?'Game update takes priority':row.conflict?(laterMerge?'Conflict · game value selected':'Choose a value'):'Custom change available to merge';
  const values=[['Original',row.original],['Your custom value',row.custom],['Game update',row.incoming]];
  const choice=gameFirst?'<p class="work-help">The game value is installed first. Your custom value stays available in the later merge review.</p>':
    `<label class="work-choice">Merge decision<select data-custom-choice="${esc(row.id)}" aria-label="Decision for custom change on line ${row.line}">${row.conflict&&!laterMerge?'<option value="">Choose…</option>':''}<option value="keep" ${laterMerge&&!row.conflict?'selected':''}>Keep my custom value</option><option value="update" ${laterMerge&&row.conflict?'selected':''}>Use game value</option></select></label>`;
  return `<article class="work-conflict ${row.conflict&&!gameFirst?'needs-choice':''}"><div class="work-conflict-title"><strong>${title}</strong><small>Original version ${esc(file.originalVersion)} · line ${row.line}</small></div><pre class="work-context">${esc(row.context)}</pre><div class="work-three">${values.map(([label,value])=>`<div><span>${label}</span><pre>${value===null?'(not present)':esc(value)}</pre></div>`).join('')}</div>${choice}</article>`;
}
function renderUpdateReport(report){
  WUI.report=report;
  const pack=report.package;
  const gameFirst=report.priority==='game';
  $('#update-report').innerHTML=`<div class="work-report-heading"><div><h2>${pack?'Package '+esc(pack.version):'Installed file changes'}</h2><p>${report.affectedFiles} affected files · ${report.conflicts} conflicting custom changes · ${report.trackedFiles} tracked files</p></div><button class="button small" id="update-export">Download report</button></div>${pack?`<p class="notice ${pack.verified?'info':''}">${pack.files} package files · ${pack.verified?'SHA-256 matched the supplied release checksum':'Preview only: import with the published SHA-256 to enable installation'} · ${esc(pack.kind)} package</p>`:''}
    <p class="work-help">${esc(report.scope)}</p>${report.files.map(file=>`<section class="work-conflict-file"><h3>${esc(file.path)}${file.deferred?' · pending merge':''}</h3>${file.choices.map(row=>customMergeMarkup(row,file,report)).join('')||`<p class="work-help">${gameFirst?'This game file will be installed first. Original and custom values are preserved for later review.':'The current game already contains these custom values. Review the merge to accept the game as the new baseline.'}</p>`}</section>`).join('')||'<div class="empty">No incoming changes affect tracked custom entries. Unrelated update changes need no individual approval.</div>'}
    <div class="work-actions work-report-actions">${pack?`<button id="install-reviewed-update" class="button primary" ${pack.verified?'':'disabled'}>Review game package installation</button>`:`<button id="reconcile-custom" class="button primary" ${report.affectedFiles?'':'disabled'}>Review selected merge</button>${report.kind==='installed'?`<button id="defer-custom-merge" class="button" ${report.affectedFiles?'':'disabled'}>Keep game; decide later</button>`:''}`}</div>`;
  $('#update-export').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify({...report,decisions:updateChoices()},null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download=`metin2-custom-update-review-${Date.now()}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});
  $('#reconcile-custom')?.addEventListener('click',()=>preview('/api/customisations/preview',{id:report.id,decisions:updateChoices()}));
  $('#defer-custom-merge')?.addEventListener('click',()=>preview('/api/customisations/defer',{id:report.id}));
  $('#install-reviewed-update')?.addEventListener('click',()=>{
    if($$('[data-custom-choice]').some(select=>!select.value))return toast('Choose Keep custom or Use update for each conflict.',true);
    const dialog=$('#update-install-dialog');$('#update-install-summary').textContent=`Install ${pack.version}: ${pack.files} package files, ${report.affectedFiles} tracked custom files supplied by the package. Game values are installed first. Original and custom values are archived and retained for a later merge review; no custom merge is applied automatically. The native updater creates its normal backups. Build/Apply is separate.`;
    $('#confirm-update-install').onclick=()=>attempt(async()=>{const result=await api('/api/updates/install',{id:report.id,decisions:updateChoices()});dialog.close();$('#update-operation').textContent=result.message;pollUpdateOperation()});dialog.showModal();
  });
}
async function pollUpdateOperation(){
  clearTimeout(WUI.updatePoll);
  try{const job=await api('/api/updates/status');if(S.page!=='updates')return;$('#update-operation').textContent=job.message||'No update operation running.';if(job.report)renderUpdateReport(job.report);if(job.status==='running')WUI.updatePoll=setTimeout(pollUpdateOperation,2000);if(job.requiresReload){$('#update-operation').insertAdjacentHTML('beforeend',' <button class="button small" id="reload-after-package">Reload Studio catalog</button>');$('#reload-after-package').onclick=()=>attempt(async()=>{await api('/api/catalog/reload',{});location.reload()})}}catch(error){if($('#update-operation'))$('#update-operation').textContent=error.message}
}
async function renderUpdates(){
  await workspaceRefresh();
  $('#content').innerHTML=head('UPDATE FIRST, MERGE LATER','Update protection','Review your preserved custom work after a game update.')+
    `<div class="notice info">Install and run the game update first, then review your custom changes.</div>${helpDetails('How update protection works','<p>Studio preserves original, custom and updated values. Conflicts default to the game value. Choose what to keep, reapply or adapt; Keep game, decide later preserves unresolved custom work for a later review.</p>')}
    <div class="work-grid"><section class="panel"><div class="panel-header"><h2>Review custom merges</h2></div><div class="work-body"><p>Compare your custom work with the installed game update. Scanning leaves game files untouched.</p><button class="button primary" id="scan-customisations">Scan installed files / pending merges</button><p class="work-help">${WUI.info.tracked.length} tracked files · ${WUI.info.pendingMerges?.length||0} pending merges. Earlier edits made outside Studio need an original backup.</p></div></section>
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
    `${info.pendingMerges?.length?`<div class="notice info">${info.pendingMerges.length} custom merges await review. The game values remain in place until you save a merge. <button class="button small" data-go="updates">Review custom merges</button></div>`:''}<div class="stats">${[[info.drafts.length,'Preserved drafts','Unfinished editor work'],[info.changesets.filter(row=>row.status==='draft').length,'Open change sets','Related changes reviewed together'],[info.pending.length,'Files awaiting apply',info.deploymentKnown?'Since the last Studio deployment':'Deployment state not yet recorded'],[info.tracked.length,'Protected custom files','Originals retained outside the game']].map(([n,label,hint])=>`<div class="stat"><div class="stat-label">${label}</div><strong>${fmt(n)}</strong><small>${hint}</small></div>`).join('')}</div>
    <div class="work-grid work-section"><section class="panel"><div class="panel-header"><h2>Continue your work</h2><button class="subtle-link" data-go="changes">All drafts &amp; changes ↗</button></div><div class="work-list">${info.drafts.slice(0,4).map(row=>`<article><div><strong>${esc(row.title)}</strong><p>${esc(titles[row.kind])} · ${wDate(row.updated)}</p></div><button class="button small" data-home-draft="${esc(row.id)}">Resume</button></article>`).join('')||'<div class="empty">Choose an editor to begin. Drafts are preserved as you work.</div>'}</div></section>
    <section class="panel"><div class="panel-header"><h2>Recent activity</h2></div><div class="work-list">${info.recent.slice(0,5).map(row=>`<article><div><strong>${esc(row.title)}</strong><p>${esc(row.kind)} · ${wDate(row.at)}</p></div></article>`).join('')||'<div class="empty">Studio saves, staged changes and apply results will appear here.</div>'}</div></section></div>
    <div class="quick-grid work-section"><article class="feature-card"><div class="mini-label">LOOT &amp; REWARDS</div><h2>Shape the rewards.</h2><p>Compare targets and inspect shared pools before changing the loot.</p><button class="button primary" data-go="drops">Open drop editor ↗</button></article><article class="feature-card secondary"><div class="mini-label">STORIES &amp; PROGRESSION</div><h2>Build an adventure.</h2><p>Manage quests and crafting alongside the items they use.</p><div class="work-actions"><button class="button" data-go="quests">Browse quests ↗</button><button class="button" data-go="crafting">Crafting ↗</button></div></article></div>
    <details class="panel work-catalog"><summary>Installed catalog · ${fmt(c.items)} items · ${fmt(c.mobs)} targets · ${fmt(c.files)} files</summary><p>Version ${esc(S.data.version)}. Catalog and source definitions can differ from the running database. Docker availability alone does not verify game health.</p><div class="work-actions"><button class="button" data-go="settings">World settings</button><button class="button" data-go="files">Config library</button><button class="button" data-go="economy">Game economy &amp; archived Studio history</button></div></details>`;
  bindNavigation();$$('[data-home-draft]').forEach(button=>button.onclick=()=>attempt(()=>resumeWorkspaceDraft(button.dataset.homeDraft)));
  const shortcut=document.createElement('section');shortcut.className='panel work-section';
  shortcut.innerHTML=`<div class="work-body"><h2>Game economy</h2><p>Currency, item circulation and shops.</p>${gameEconomyLink()}</div>`;
  $('#content').append(shortcut);bindGameDashboardLinks();
  renderAddonOverview();
}

const baseUpdatesPage=renderUpdates;
renderUpdates=async function(){await baseUpdatesPage();const pending=(await workspaceRefresh()).preferences.nativeUpdatePending;if(pending&&!pending.ready){$('#update-operation').insertAdjacentHTML('afterend','<p class="notice">Package installation or verification needs recovery. Check the native launcher result, scan changed files and keep the game values before verifying recovery. Custom merge decisions can remain deferred.</p><button class="button" id="finish-update-recovery">Verify package recovery</button>');$('#finish-update-recovery').onclick=()=>attempt(async()=>{await api('/api/updates/recovery',{});await renderUpdates();toast('Package recovery recorded. Apply the game update when ready; review custom merges separately.')})}};

const recoverableUpdatesPage=renderUpdates;
renderUpdates=async function(){await recoverableUpdatesPage();$('#update-operation').insertAdjacentHTML('afterend','<div class="editor-actions"><button class="button" id="adopt-custom-file">Track an existing edit from its original backup</button><small>Earlier manual edits need an original file to identify your custom differences. New Studio saves are tracked automatically.</small></div>');$('#adopt-custom-file').onclick=()=>attempt(async()=>{const paths=await api('/api/customisations/adopt-sources');toolDialog('Track existing configuration edits',`<p>Choose the current file and its unmodified original backup. Review the differences before registering them. Game files are unchanged.</p><label>Current configuration<select id="adopt-path" class="wide-input">${paths.map(path=>`<option>${esc(path)}</option>`).join('')}</select></label><label>Original backup file<input id="adopt-original" type="file"></label><button class="button primary" id="adopt-review">Review custom differences</button>`);$('#adopt-review').onclick=()=>attempt(async()=>{const file=$('#adopt-original').files[0];if(!file||file.size>2000000)throw new Error('Choose an original backup under 2 MB.');const bytes=new Uint8Array(await file.arrayBuffer());let raw='';for(const byte of bytes)raw+=String.fromCharCode(byte);const body={path:$('#adopt-path').value,original:btoa(raw)};$('#tool-dialog').close();await preview('/api/customisations/adopt',body)})})};
