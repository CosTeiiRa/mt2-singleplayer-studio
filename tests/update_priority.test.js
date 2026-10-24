'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/workspace.js'),'utf8');

function setup(){
  const elements=new Map(),requests=[];
  const $=selector=>{
    if(!elements.has(selector))elements.set(selector,{innerHTML:'',textContent:'',addEventListener(name,handler){this[name]=handler},showModal(){this.open=true},close(){this.open=false}});
    return elements.get(selector);
  };
  const context={WUI:{},$, $$:()=>[],esc:value=>String(value??'').replaceAll('<','&lt;').replaceAll('>','&gt;'),attempt:fn=>fn(),pollUpdateOperation(){},preview:(path,body)=>requests.push({path,body}),api:async(path,body)=>{requests.push({path,body});return {message:'Game package installed'}}};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('function updateChoices('),source.indexOf('async function pollUpdateOperation(')),context);
  return {context,$,requests};
}
function report(kind){return {id:'review',kind,priority:kind==='package'?'game':kind==='installed'?'merge':'review',affectedFiles:1,conflicts:1,trackedFiles:1,scope:'The game takes priority.',files:[{path:'recipe.txt',originalVersion:'1',deferred:kind==='installed',choices:[{id:'choice',line:1,conflict:true,context:'Recipe',original:'50',custom:'100',incoming:'<game>80</game>'}]}]};}

test('game update review uses game values without custom restoration controls',async()=>{
  const {context,$,requests}=setup(),value=report('package');
  value.package={version:'2',files:8,verified:true,kind:'ordinary'};
  context.renderUpdateReport(value);
  assert.match($('#update-report').innerHTML,/Game update takes priority/);
  assert.match($('#update-report').innerHTML,/&lt;game&gt;80&lt;\/game&gt;/);
  assert.doesNotMatch($('#update-report').innerHTML,/<select|Keep my custom value|Choose…/);
  await $('#install-reviewed-update').click();
  assert.match($('#update-report').innerHTML,/Original and custom values/);
  assert.equal(requests.length,1);
  assert.equal(requests[0].path,'/api/updates/install');
  assert.equal(requests[0].body.id,'review');
  assert.deepEqual(Object.keys(requests[0].body.decisions),[]);
});

test('later merge review defaults conflicts to game and supports keeping custom or deciding later',()=>{
  const {context,$,requests}=setup();
  context.renderUpdateReport(report('installed'));
  assert.match($('#update-report').innerHTML,/Review selected merge/);
  assert.match($('#update-report').innerHTML,/pending merge/);
  assert.match($('#update-report').innerHTML,/value="update" selected>Use game value/);
  assert.match($('#update-report').innerHTML,/Keep my custom value/);
  assert.match($('#update-report').innerHTML,/Keep game; decide later/);
  $('#defer-custom-merge').click();
  assert.equal(requests[0].path,'/api/customisations/defer');
  assert.equal(requests[0].body.id,'review');
  context.renderUpdateReport(report('changeset'));
  assert.match($('#update-report').innerHTML,/<select/);
  assert.match($('#update-report').innerHTML,/Keep my custom value/);
  assert.match($('#update-report').innerHTML,/<option value="">Choose…/);
});

test('compatible custom changes can be selected in the later review without hiding game changes',()=>{
  const {context,$}=setup(),value=report('installed');
  value.files[0].choices[0].conflict=false;
  context.renderUpdateReport(value);
  assert.match($('#update-report').innerHTML,/value="keep" selected>Keep my custom value/);
  assert.match($('#update-report').innerHTML,/&lt;game&gt;80&lt;\/game&gt;/);
});
