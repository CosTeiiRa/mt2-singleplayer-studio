'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const workspace=fs.readFileSync(path.join(__dirname,'../web/workspace.js'),'utf8');
const app=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');

function setup(job={id:'previous',kind:'apply',status:'succeeded',started:1,lines:['Old success log']}){
  const nodes=new Map(),requests=[];
  const $=id=>{
    if(!nodes.has(id))nodes.set(id,{open:id==='#apply-dialog',hidden:false,disabled:false,checked:id==='#apply-include-server',dataset:{},textContent:'',innerHTML:'',showModal(){this.open=true;}});
    return nodes.get(id);
  };
  const storage=new Map();
  const context={$,S:{data:{root:'test-world'},status:{docker:{available:true},job}},WUI:{info:{pending:[{path:'custom-quests/new.quest'}],preferences:{},drafts:[],deploymentKnown:true}},
    ApplyUI:{jobId:null,starting:'',loading:false,connectionFailed:false,error:'',review:{id:'review',server:true,files:[{path:'custom-quests/new.quest'}],drafts:0}},
    OperationUI:{scope:null,dismissed:null,signature:'',timer:null},StudioOperations:require('../web/operations.js'),statusRequest:0,
    $$:()=>[],setInterval:()=>1,clearInterval(){},sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},
    esc:String,wDate:at=>'date:'+at,api:async url=>{requests.push(url);return url.endsWith('/review')?{id:'refreshed',server:true,files:[],drafts:0}:{id:'new-job',kind:url.endsWith('validate')?'validation':'apply',status:'running',lines:['New operation']};},
    refreshAddonNotice:()=>{},updateStatus:async()=>context.refreshApplyControl(),toast:()=>{}};
  vm.createContext(context);
  vm.runInContext(workspace.slice(workspace.indexOf('function operationJob('),workspace.indexOf('const wDate=')),context);
  vm.runInContext(workspace.slice(workspace.indexOf('function refreshApplyControl('),workspace.indexOf('async function initWorkspace(')),context);
  vm.runInContext(app.slice(app.indexOf('function openApplyDialog('),app.indexOf('let applyTimer;')),context);
  return {context,$,requests};
}

test('a previous success cannot imply new pending changes were applied',()=>{
  const {context,$}=setup();context.refreshApplyControl();
  assert.equal($('#apply-current-title').textContent,'1 change is still not applied');
  assert.equal($('#apply-operation').hidden,true);
  assert.equal($('#apply-log').textContent,'');
  assert.equal($('#apply-previous').hidden,false);
  assert.equal($('#apply-previous').open,false);
  assert.match($('#apply-previous-title').textContent,/Previous apply · completed/);
  assert.match($('#apply-previous-note').textContent,/does not mean newer saved changes have been applied/);
  assert.equal($('#apply-previous-log').textContent,'Old success log');
  assert.equal($('#run-apply').disabled,false);
});

test('validation completion retains pending changes and explicitly says nothing was applied',()=>{
  const {context,$}=setup({id:'validation',kind:'validation',status:'validated',lines:['Build OK']});
  context.ApplyUI.jobId='validation';context.refreshApplyControl();
  assert.match($('#apply-current-title').textContent,/still not applied/);
  assert.equal($('#apply-operation').hidden,false);
  assert.match($('#apply-operation-result').textContent,/did not apply changes or restart the game/);
  assert.equal($('#run-apply').disabled,false);
  context.ApplyUI.jobId=null;context.refreshApplyControl();
  assert.equal($('#apply-operation').hidden,true);
  assert.match($('#apply-previous-title').textContent,/Previous validation/);
});

test('reopening hides a completed operation and collapses its old log while refreshing',()=>{
  const {context,$,requests}=setup();context.ApplyUI.jobId='previous';
  $('#apply-previous').open=true;context.refreshApplyControl();
  assert.equal($('#apply-operation').hidden,false);
  context.openApplyDialog();
  assert.equal(context.ApplyUI.jobId,null);
  assert.equal($('#apply-operation').hidden,true);
  assert.equal($('#apply-previous').hidden,true);
  assert.equal($('#apply-previous').open,false);
  assert.equal($('#run-apply').disabled,true);
  assert.equal($('#run-validate').disabled,true);
  assert.equal(requests.length,0);
});

test('a running validation is resumed on reopen and blocks both actions',()=>{
  const {context,$}=setup({id:'running',kind:'validation',status:'running',lines:['Compiling']});
  context.refreshApplyControl();
  assert.match($('#apply-current-title').textContent,/Validation in progress/);
  assert.equal($('#apply-operation').hidden,false);
  assert.equal($('#apply-log').textContent,'Compiling');
  assert.equal($('#run-apply').disabled,true);
  assert.equal($('#run-validate').disabled,true);
});

test('a successful current Apply shows completion and disables Apply when no changes remain',()=>{
  const {context,$}=setup();context.ApplyUI.jobId='previous';context.WUI.info.pending=[];context.ApplyUI.review=null;
  context.refreshApplyControl();
  assert.equal($('#apply-current-title').textContent,'No saved changes awaiting Apply');
  assert.match($('#apply-operation-title').textContent,/Apply · completed/);
  assert.equal($('#run-apply').disabled,true);
  assert.equal($('#run-validate').disabled,false);
  context.WUI.info.pending=[{path:'.env'}];context.refreshApplyControl();
  assert.match($('#apply-current-title').textContent,/still not applied/);
});

test('failed, unverified, and unreachable operations do not clear the pending indication',()=>{
  for(const status of ['failed','unverified']){
    const {context,$}=setup({id:'new',kind:'apply',status,lines:['Trouble']});
    context.ApplyUI.jobId='new';context.refreshApplyControl();
    assert.match($('#apply-current-title').textContent,/still not applied/);
    assert.equal($('#apply-log').textContent,'Trouble');
    assert.equal($('#run-apply').disabled,false);
    context.ApplyUI.connectionFailed=true;context.refreshApplyControl();
    assert.match($('#apply-explanation').textContent,/could not be refreshed/);
    assert.equal($('#run-apply').disabled,true);
    assert.equal($('#run-validate').disabled,true);
  }
});

test('starting either operation blocks a duplicate request before the server replies',async()=>{
  const {context,$,requests}=setup();let reply;
  context.api=url=>{requests.push(url);return new Promise(resolve=>{reply=resolve;});};
  const first=context.runServerOperation(true);
  assert.equal($('#run-apply').disabled,true);
  assert.equal($('#run-validate').disabled,true);
  context.openApplyDialog();
  assert.equal(context.ApplyUI.starting,'validation');
  await context.runServerOperation(false);
  assert.deepEqual(requests,['/api/validate']);
  reply({id:'new',kind:'validation',status:'running',lines:[]});await first;
  assert.equal(context.ApplyUI.jobId,'new');
  assert.equal($('#run-apply').disabled,true);
});

test('a saved deployment can be inspected after Studio restarts without becoming the current result',()=>{
  const {context,$}=setup({status:'idle',lines:[]});
  context.WUI.info.lastDeployment={id:'saved',status:'succeeded',started:5,finished:8,payload:{kind:'apply',lines:['Saved deployment']}};
  context.refreshApplyControl();
  assert.equal($('#apply-operation').hidden,true);
  assert.equal($('#apply-previous-log').textContent,'Saved deployment');
  assert.match($('#apply-current-title').textContent,/still not applied/);
});

test('request errors are shown without presenting the previous success as the current result',async()=>{
  const {context,$}=setup();context.api=async()=>{throw new Error('Review required');};
  await context.runServerOperation(false);
  assert.equal($('#apply-error').hidden,false);
  assert.equal($('#apply-error').textContent,'Review required');
  assert.equal($('#apply-operation').hidden,true);
  assert.match($('#apply-current-title').textContent,/still not applied/);
});

test('interrupted-save recovery blocks both actions and exposes the recovery route',()=>{
  const {context,$}=setup();context.WUI.info.saveRecovery=[{id:'receipt'}];
  context.refreshApplyControl();
  assert.equal($('#apply-button').disabled,false);
  assert.equal($('#apply-button').textContent,'Save recovery required');
  assert.equal($('#run-apply').disabled,true);
  assert.equal($('#run-validate').disabled,true);
  assert.match($('#apply-current-title').textContent,/recovery required/);
  assert.match($('#studio-recovery').innerHTML,/Drafts &amp; changes/);
});

test('validation does not dismiss an interrupted deployment and retry requires acknowledgement',()=>{
  const {context,$}=setup({id:'validation',kind:'validation',status:'validated',lines:[]});
  context.WUI.info.interruptedDeployment={id:'interrupted',status:'interrupted'};
  context.refreshApplyControl();
  assert.equal($('#studio-recovery').hidden,false);
  assert.equal($('#apply-interrupted-check').hidden,false);
  assert.equal($('#run-apply').disabled,true);
  assert.match($('#apply-explanation').textContent,/previous interrupted deployment/);
  $('#apply-interrupted-ack').checked=true;context.refreshApplyControl();
  assert.equal($('#run-apply').disabled,false);
  context.openApplyDialog();
  assert.equal($('#apply-interrupted-ack').checked,false);
});

test('operation feedback remains available outside the Apply dialog and dismisses only the current result',()=>{
  const {context,$}=setup();$('#apply-dialog').open=false;context.refreshApplyControl();
  assert.equal($('#operation-status').hidden,false);
  assert.match($('#operation-status').innerHTML,/Server Apply complete/);
  assert.match($('#operation-status').innerHTML,/1 saved change still needs Apply/);
  $('#operation-dismiss').onclick();assert.equal($('#operation-status').hidden,true);
  context.S.status.job={id:'new',kind:'apply',status:'running',started:100,lines:[]};context.refreshApplyControl();
  assert.equal($('#operation-status').hidden,false);assert.match($('#operation-status').innerHTML,/View progress/);
});
test('a completed operation stays inspectable when there are no new saved changes',()=>{
  const {context,$}=setup();context.WUI.info.pending=[];context.refreshApplyControl();
  assert.equal($('#apply-button').disabled,false);assert.equal($('#apply-button').textContent,'View last operation');
  $('#operation-open').onclick();assert.equal(context.ApplyUI.jobId,'previous');
});
test('failure opens the technical log once and does not force it open after the user collapses it',()=>{
  const {context,$}=setup({id:'bad',kind:'apply',status:'failed',lines:['Failure details']});
  context.ApplyUI.jobId='bad';context.refreshApplyControl();assert.equal($('#apply-log-details').open,true);
  $('#apply-log-details').open=false;context.refreshApplyControl();assert.equal($('#apply-log-details').open,false);
});
test('the elapsed clock does not continue timing an older completed receipt without a finish time',()=>{
  const {context}=setup();const node={dataset:{started:'100',finished:'0',status:'succeeded'}};
  context.$$=()=>[node];context.updateOperationElapsed();assert.equal(node.textContent,'');
  node.dataset.finished='180';context.updateOperationElapsed();assert.equal(node.textContent,'1m 20s');
});

test('add-ons can be applied without Docker or a server restart',()=>{
  const {context,$}=setup();context.WUI.info.pending=[];context.S.status.docker.available=false;
  context.ApplyUI.review={id:'addons',server:false,files:[],drafts:0,addons:{action:'reapply',can_apply:true,summary:'Reapply 4 add-ons',installed:[]}};
  $('#apply-include-addons').checked=true;context.refreshApplyControl();
  assert.equal($('#run-apply').disabled,false);
  assert.equal($('#run-apply').textContent,'Apply add-ons');
  assert.equal($('#apply-restart-note').hidden,true);
});

test('extension activation requires server selection and explains the blocked Apply',async()=>{
  const {context,$,requests}=setup();
  context.ApplyUI.review.addons={kind:'game-extension',addon_id:'community.legacy-mount-support',action:'install',can_apply:true,server_required:true,components:[{id:'activation',name:'Mount activation',status:'provided'},{id:'client-data',name:'Client-data fixes',status:'ready'}],changes:[]};
  $('#apply-include-addons').checked=true;$('#apply-include-server').checked=false;context.refreshApplyControl();
  assert.match($('#apply-pending').innerHTML,/Server &amp; client add-on/);
  assert.match($('#apply-pending').innerHTML,/Provided by game/);
  assert.match($('#apply-pending').innerHTML,/Mounted combat remains a separate option/);
  assert.equal($('#run-apply').disabled,true);
  assert.equal($('#apply-blocker').hidden,false);
  assert.match($('#apply-blocker').textContent,/Select Server files/);
  await context.runServerOperation(false);assert.equal(requests.length,0);
  $('#apply-include-server').checked=true;context.renderApplyDialog();
  assert.equal($('#run-apply').disabled,false);
  assert.equal($('#apply-blocker').hidden,true);
  context.S.status.docker.available=false;context.renderApplyDialog();
  assert.equal($('#run-apply').disabled,true);
  assert.match($('#apply-blocker').textContent,/Start Docker Desktop/);
});

test('an extension whose activation is already provided can apply client fixes alone',()=>{
  const {context,$}=setup();context.S.status.docker.available=false;
  context.ApplyUI.review={id:'client-fixes',server:false,files:[],drafts:0,addons:{kind:'game-extension',action:'reapply',can_apply:true,server_required:false,components:[{id:'activation',status:'provided'}]}};
  $('#apply-include-addons').checked=true;context.refreshApplyControl();
  assert.equal($('#run-apply').disabled,false);
  assert.equal($('#apply-restart-note').hidden,true);
  assert.equal($('#apply-blocker').hidden,true);
});

test('an add-on-only review cannot present an earlier server result as its own',()=>{
  const {context,$}=setup();context.WUI.info.pending=[];
  context.ApplyUI.addonState={installed:[{id:'example'}],integrity:{repair_available:true}};
  context.openApplyDialog();
  assert.equal(context.ApplyUI.jobId,null);
  assert.equal($('#apply-operation').hidden,true);
});

test('the combined confirmation sends the reviewed ID and selected scopes',async()=>{
  const {context,$}=setup();const calls=[];
  context.ApplyUI.review.addons={can_apply:true,action:'reapply',summary:'Reapply saved add-ons',installed:[]};
  $('#apply-include-addons').checked=true;
  context.api=async(url,body)=>{calls.push({url,...body});return {id:'combined',kind:'combined',status:'running'};};
  context.refreshApplyControl();assert.equal($('#run-apply').textContent,'Apply files & add-ons');
  await context.runServerOperation(false);
  assert.deepEqual(calls,[{url:'/api/apply',reviewId:'review',includeServer:true,includeAddons:true}]);
  assert.equal(context.ApplyUI.review,null);
});

test('status polling preserves the scope choices in an existing review',()=>{
  const {context,$}=setup();context.refreshApplyControl();
  $('#apply-include-server').checked=false;context.refreshApplyControl();
  assert.equal($('#apply-include-server').checked,false);
  assert.equal($('#run-apply').disabled,true);
});

test('an add-on failure after server success only asks to retry add-ons',()=>{
  const {context,$}=setup({id:'combined',kind:'combined',status:'failed',serverStatus:'succeeded',addons:{status:'failed'},lines:[]});
  context.WUI.info.pending=[];context.ApplyUI.review=null;context.refreshApplyControl();
  assert.match($('#apply-explanation').textContent,/Only the add-ons still need attention/);
  assert.equal($('#refresh-apply-review').hidden,false);
});

test('reapply notification and navigation count persist until client files are healthy',()=>{
  const {context,$}=setup();
  vm.runInContext(app.slice(app.indexOf('function renderAddonNotice('),app.indexOf('async function refreshAddonNotice(')),context);
  context.renderAddonNotice({installed:[{id:'one'},{id:'two'}],integrity:{status:'missing',repair_available:true,message:'Game update replaced client packs.'}});
  assert.equal($('#addon-installation-notice').hidden,false);
  assert.match($('#addon-installation-notice').innerHTML,/2 add-ons need to be applied again/);
  assert.match($('#addon-installation-notice').innerHTML,/Review &amp; apply together/);
  assert.equal($('#addon-reapply-count').textContent,'2 to reapply');
  assert.equal($('#apply-button').textContent,'Review & apply (3)');
  context.renderAddonNotice({installed:[{id:'one'},{id:'two'}],integrity:{status:'healthy',repair_available:false}});
  assert.equal($('#addon-installation-notice').hidden,true);
  assert.equal($('#addon-reapply-count').hidden,true);
  assert.equal($('#apply-button').textContent,'Review & apply (1)');
});

function selectableReview(ids=['one','two'],id='selection-review'){
  const choices=[{id:'one',name:'Boss Atlas',version:'1.0',enabled:true},{id:'two',name:'Pocket Wiki',version:'1.0',enabled:false}];
  return {id,server:true,files:[{path:'drops.txt'}],drafts:0,selectableAddons:choices,selectedAddonIds:ids,
    addons:ids.length?{id:'packs-'+id,action:'reapply',can_apply:true,summary:`Reapply ${ids.length} add-ons`,installed:choices.filter(row=>ids.includes(row.id)),conflicts:[],changes:[]}:null};
}
function setupSelection(){
  const result=setup(),{context}=result;
  context.ApplyUI.review=selectableReview();context.ApplyUI.addonSelection=['one','two'];context.ApplyUI.reviewRequest=1;
  const controls=context.ApplyUI.review.selectableAddons.map(row=>({dataset:{applyAddon:row.id},checked:true,disabled:false,addEventListener(){}}));
  context.$$=selector=>selector==='[data-apply-addon]'?controls:[];
  context.refreshApplyControl();
  return {...result,controls};
}

test('add-on selection exposes individual choices, Select all, Clear and the selected count',()=>{
  const {context,$,controls}=setupSelection();
  assert.match($('#apply-pending').innerHTML,/data-apply-addon="one"/);
  assert.match($('#apply-pending').innerHTML,/data-apply-addon="two"/);
  assert.match($('#apply-pending').innerHTML,/Select all/);
  assert.match($('#apply-pending').innerHTML,/>Clear</);
  assert.equal($('#apply-addons-count').textContent,'2 of 2 selected');
  assert.equal($('#run-apply').textContent,'Apply all (3)');
  $('#apply-include-server').checked=false;context.renderApplyDialog();
  assert.equal($('#run-apply').textContent,'Apply selected (2)');
  assert.ok(controls.every(row=>!row.disabled));
});

test('changing a subset disables Apply until its exact new plan is ready',async()=>{
  const {context,$,controls}=setupSelection(),calls=[];let reply;
  context.api=(url,body)=>{calls.push({url,...JSON.parse(JSON.stringify(body))});return new Promise(resolve=>{reply=resolve;});};
  const selected=context.setApplyAddonSelection(['two']);
  assert.deepEqual(calls,[{url:'/api/apply/review',reviewId:'selection-review',addonIds:['two']}]);
  assert.equal(context.ApplyUI.selectionPending,true);
  assert.equal($('#apply-addon-plan').hidden,true);
  assert.equal($('#run-apply').disabled,true);
  assert.equal($('#apply-addons-count').textContent,'1 of 2 selected');
  assert.equal($('#apply-include-addons').indeterminate,true);
  assert.equal(controls[0].checked,false);assert.equal(controls[1].checked,true);
  await context.runServerOperation(false);assert.equal(calls.length,1);
  reply(selectableReview(['two'],'subset-ready'));await selected;
  assert.equal(context.ApplyUI.selectionPending,false);
  assert.equal($('#apply-addon-plan').hidden,false);
  assert.equal($('#run-apply').disabled,false);
  assert.equal($('#run-apply').textContent,'Apply selected (2)');
  assert.equal(context.ApplyUI.review.id,'subset-ready');
});

test('rapid checkbox changes serialize requests and coalesce to the latest selection',async()=>{
  const {context,$}=setupSelection(),calls=[],replies=[];
  context.api=(url,body)=>{calls.push(JSON.parse(JSON.stringify(body)));return new Promise(resolve=>replies.push(resolve));};
  const pending=context.setApplyAddonSelection(['one']);
  context.setApplyAddonSelection(['two']);
  context.setApplyAddonSelection(['one','two']);
  assert.equal(calls.length,1);
  replies[0](selectableReview(['one'],'first-preview'));
  await new Promise(setImmediate);
  assert.deepEqual(calls[1],{reviewId:'first-preview',addonIds:['one','two']});
  assert.equal($('#run-apply').disabled,true);
  replies[1](selectableReview(['one','two'],'latest-preview'));await pending;
  assert.deepEqual(Array.from(context.ApplyUI.addonSelection),['one','two']);
  assert.equal(context.ApplyUI.review.id,'latest-preview');
  assert.equal($('#run-apply').disabled,false);
  assert.equal($('#run-apply').textContent,'Apply all (3)');
});

test('Clear retains the full choice list so Select all can restore it',async()=>{
  const {context,$}=setupSelection(),calls=[];
  context.api=async(url,body)=>{calls.push(JSON.parse(JSON.stringify(body)));return selectableReview(body.addonIds,'selection-'+calls.length);};
  await context.setApplyAddonSelection([]);
  assert.equal(context.ApplyUI.review.addons,null);
  assert.equal(context.ApplyUI.review.selectableAddons.length,2);
  assert.equal($('#apply-addons-count').textContent,'0 of 2 selected');
  assert.equal($('#run-apply').textContent,'Apply selected (1)');
  $('#apply-include-server').checked=false;context.renderApplyDialog();
  assert.equal($('#run-apply').disabled,true);
  await context.setApplyAddonSelection(['one','two']);
  assert.deepEqual(calls[1],{reviewId:'selection-1',addonIds:['one','two']});
  assert.equal($('#apply-include-server').checked,false);
  assert.equal($('#run-apply').textContent,'Apply selected (2)');
  assert.equal($('#run-apply').disabled,false);
});

test('selection failures block stale Apply but keep checkbox choices editable',async()=>{
  const {context,$,controls}=setupSelection();
  context.api=async()=>{throw Error('Review expired. Refresh the review.');};
  await context.setApplyAddonSelection(['one']);
  assert.equal(context.ApplyUI.selectionError,true);
  assert.equal($('#run-apply').disabled,true);
  assert.equal($('#refresh-apply-review').hidden,false);
  assert.match($('#apply-error').textContent,/Review expired/);
  assert.ok(controls.every(row=>!row.disabled));
});

test('a conflicting selection keeps individual choices usable and cannot silently skip add-ons',()=>{
  const {context,$,controls}=setupSelection();
  context.ApplyUI.review.addons.can_apply=false;context.renderApplyDialog();
  assert.equal(context.applySelection().addons,true);
  assert.equal($('#run-apply').disabled,true);
  assert.equal($('#apply-include-addons').disabled,false);
  assert.ok(controls.every(row=>!row.disabled));
});

test('a late selection response cannot overwrite a newly opened review',async()=>{
  const {context}=setupSelection();let reply;
  context.api=()=>new Promise(resolve=>{reply=resolve;});
  const pending=context.setApplyAddonSelection(['one']);
  context.ApplyUI.reviewRequest=2;context.ApplyUI.review=selectableReview(['two'],'new-dialog');
  context.ApplyUI.addonSelection=['two'];context.ApplyUI.selectionPending=false;
  reply(selectableReview(['one'],'old-dialog'));await pending;
  assert.equal(context.ApplyUI.review.id,'new-dialog');
  assert.deepEqual(Array.from(context.ApplyUI.addonSelection),['two']);
});

test('partial completion counts only skipped add-ons in the notice and top bar',()=>{
  const {context,$}=setup();
  vm.runInContext(app.slice(app.indexOf('function renderAddonNotice('),app.indexOf('async function refreshAddonNotice(')),context);
  context.renderAddonNotice({installed:[{id:'one',integrity:{status:'healthy'}},{id:'two',reapply_pending:true,integrity:{status:'missing'}}],
    integrity:{status:'missing',repair_available:true,pending_addon_ids:['two'],message:'One saved add-on is still pending.'}});
  assert.equal($('#addon-reapply-count').textContent,'1 to reapply');
  assert.match($('#addon-installation-notice').innerHTML,/1 add-on needs to be applied again/);
  assert.equal($('#apply-button').textContent,'Review & apply (2)');
});
