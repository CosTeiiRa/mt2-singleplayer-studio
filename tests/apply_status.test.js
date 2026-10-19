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
    if(!nodes.has(id))nodes.set(id,{open:id==='#apply-dialog',hidden:false,disabled:false,textContent:'',innerHTML:'',showModal(){this.open=true;}});
    return nodes.get(id);
  };
  const storage=new Map();
  const context={$,S:{data:{root:'test-world'},status:{docker:{available:true},job}},WUI:{info:{pending:[{path:'custom-quests/new.quest'}],preferences:{},drafts:[],deploymentKnown:true}},
    ApplyUI:{jobId:null,starting:'',loading:false,connectionFailed:false,error:''},
    OperationUI:{scope:null,dismissed:null,signature:'',timer:null},StudioOperations:require('../web/operations.js'),statusRequest:0,
    $$:()=>[],setInterval:()=>1,clearInterval(){},sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},
    esc:String,wDate:at=>'date:'+at,api:async url=>{requests.push(url);return {id:'new-job',kind:url.endsWith('validate')?'validation':'apply',status:'running',lines:['New operation']};},
    updateStatus:async()=>context.refreshApplyControl(),toast:()=>{}};
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
  const {context,$}=setup();context.ApplyUI.jobId='previous';context.WUI.info.pending=[];
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
