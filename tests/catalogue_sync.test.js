'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const script=source.slice(source.indexOf('let catalogueRefreshBusy='),source.indexOf('async function updateStatus(){'));
function fixture(){
  const status={},picker={open:true},draft={entries:[{item:'10',count:'3'}]};
  const context={S:{data:{catalogue:{revision:'old'},counts:{items:1,mobs:0}},group:draft,itemMap:{},mobMap:{},
    picker:{kind:'item',filter:item=>item.id!=='99',items:[{id:'s1',catalogKind:'reward-pool'}]}},
    $:selector=>selector==='#catalogue-status'?status:picker,renderPicker:()=>{context.renders++},renders:0,calls:0,
    api:async()=>{context.calls++;return {catalogue:{revision:'new',serverMode:'live',clientMode:'current'},items:[{id:'10',name:'Updated'},{id:'99',name:'Excluded'}],mobs:[{id:'691',name:'Current boss'}]}}};
  vm.createContext(context);vm.runInContext(script,context);
  return {context,status,draft};
}
test('catalogue refresh replaces shared maps and picker data without changing the draft',async()=>{
  const {context,status,draft}=fixture();
  await context.refreshCatalogue({revision:'new',serverMode:'live',clientMode:'current'});
  assert.equal(context.S.itemMap['10'].name,'Updated');assert.equal(context.S.mobMap['691'].name,'Current boss');
  assert.equal(context.S.data.counts.items,2);assert.equal(context.renders,1);
  assert.deepEqual(Array.from(context.S.picker.items,item=>item.id),['10','s1']);
  assert.equal(context.S.group,draft);assert.equal(context.S.data.catalogue.revision,'new');
  assert.match(status.textContent,/synced with server/);
});
test('same revision updates offline status without reloading item data',async()=>{
  const {context,status}=fixture();
  await context.refreshCatalogue({revision:'old',serverMode:'cached',clientMode:'cached'});
  assert.equal(context.calls,0);assert.match(status.textContent,/cached/);
});
test('failed refresh retains old data and allows a later retry',async()=>{
  const {context,status}=fixture(),working=context.api;
  context.api=async()=>{throw new Error('Unavailable')};
  await context.refreshCatalogue({revision:'new'});
  assert.equal(context.S.data.catalogue.revision,'old');assert.match(status.textContent,/retained/);
  context.api=working;await context.refreshCatalogue({revision:'new'});
  assert.equal(context.S.data.catalogue.revision,'new');
});
