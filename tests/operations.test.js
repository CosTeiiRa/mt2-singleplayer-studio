'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {view,elapsed}=require('../web/operations.js');
const running={id:'a',kind:'apply',status:'running',started:100,lines:['build output'],progress:{current:'migration',steps:[
  {id:'build',label:'Build & compile',status:'complete'},
  {id:'migration',label:'Apply settings',detail:'Checking migration.',status:'running'},
  {id:'health',label:'Check game health',status:'pending'}]}};
test('running operations report observed stages without a fictional time percentage',()=>{
  const result=view(running,{now:185,pending:2});
  assert.equal(result.title,'Apply settings');assert.equal(result.complete,1);assert.equal(result.total,3);
  assert.equal(result.elapsed,'1m 25s');assert.equal(result.tone,'working');
  assert.match(result.message,/pending until Apply is verified/);assert.equal(result.percent,undefined);
});
test('validation success never implies deployment or restart',()=>{
  const result=view({status:'validated',kind:'validation',started:100,finished:160},{pending:1});
  assert.match(result.message,/not applied/);assert.match(result.message,/not restarted/);
  assert.match(result.message,/1 saved change still needs Apply/);assert.equal(result.active,false);
});
test('a new save stays pending even when the last Apply succeeded',()=>{
  const result=view({...running,status:'succeeded',finished:190},{pending:3,now:999});
  assert.equal(result.title,'Server Apply complete');assert.match(result.message,/3 saved changes still need Apply/);
  assert.equal(result.elapsed,'1m 30s');
});
test('lost status remains unknown and never claims success or failure',()=>{
  const result=view(running,{connectionFailed:true,pending:2});
  assert.match(result.title,/status unknown/);assert.equal(result.tone,'warning');assert.equal(result.active,true);
  assert.equal(result.lastLine,'');assert.match(result.message,/not confirmed completion/);
  assert.equal(result.stale,true);
});
test('failure identifies the last stage and preserves pending work',()=>{
  const result=view({...running,status:'failed',finished:200},{pending:2});
  assert.equal(result.tone,'danger');assert.match(result.message,/Stopped at Apply settings/);
  assert.match(result.message,/backups are retained/);assert.equal(result.attention,true);
});
test('unverified and interrupted deployments stay distinct from success',()=>{
  for(const status of ['unverified','interrupted']){
    const result=view({...running,status});assert.equal(result.tone,'warning');assert.equal(result.attention,true);
    assert.match(result.message,/pending/);
    assert.equal(result.steps.some(step=>step.status==='running'),false);
    assert.equal(result.steps.find(step=>step.id==='migration').status,'warning');
  }
});
test('older deployments without stages or a finish timestamp do not invent either',()=>{
  const result=view({status:'succeeded',started:100},{now:999});
  assert.deepEqual(result.steps,[]);assert.equal(result.elapsed,'');assert.equal(elapsed({started:100,finished:90}),'0s');
});
test('unknown source status values cannot become CSS states',()=>{
  const result=view({progress:{steps:[{id:'a',label:'<script>',status:'bad" onclick="x'},null]}});
  assert.equal(result.steps[0].status,'pending');assert.equal(result.steps.length,1);
});
