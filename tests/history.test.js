'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');

function setup(){
  const content={innerHTML:''},listeners=new Map(),requests=[];
  const typeSelect={addEventListener:(event,callback)=>listeners.set('type',callback)};
  const context={S:{},$:selector=>selector==='#history-type'?typeSelect:content,head:()=>'',esc:value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])),
    preview:(path,body)=>requests.push({path,body}),
    $$:selector=>{
      const field=selector==='[data-restore]'?'restore':'history-category';
      return [...content.innerHTML.matchAll(new RegExp('data-'+field+'="([^"]+)"','g'))].map(match=>({
        dataset:{[field==='restore'?'restore':'historyCategory']:match[1]},
        addEventListener:(event,callback)=>listeners.set(field+':'+match[1],callback)
      }));
    }};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('function renderHistory('),source.indexOf('\nasync function preview(')),context);
  return {context,content,listeners,requests};
}
const row=(id,title,category,areas=['crafting'])=>({id,title,category,areas,files:[{path:'recipe.txt'}],time:'2026-10-18T00:00:00Z',status:'saved',canRestore:true,restoreReason:'Review first.'});

test('history separates gameplay edits from reconciliation and can show the whole timeline',()=>{
  const {context,content,listeners}=setup();
  context.renderHistory([row('merge-id','Merge saved game update','reconciliation'),row('recipe-id','Remove recipe <unsafe>','gameplay')]);
  assert.match(content.innerHTML,/Remove recipe &lt;unsafe&gt;/);
  assert.doesNotMatch(content.innerHTML,/Merge saved game update/);
  assert.match(content.innerHTML,/Gameplay changes \(1\)/);
  assert.match(content.innerHTML,/Update reconciliations \(1\)/);
  listeners.get('history-category:reconciliation')();
  assert.match(content.innerHTML,/Merge saved game update/);
  assert.doesNotMatch(content.innerHTML,/Remove recipe &lt;unsafe&gt;/);
  listeners.get('history-category:all')();
  assert.match(content.innerHTML,/Merge saved game update/);
  assert.match(content.innerHTML,/Remove recipe &lt;unsafe&gt;/);
  assert.match(content.innerHTML,/including edits in the other category/);
});

test('filtered rollback uses the displayed record id instead of its position in the full history',()=>{
  const {context,listeners,requests}=setup();
  context.renderHistory([row('merge-first','Update merge','reconciliation'),row('recipe-second','Recipe edit','gameplay')]);
  listeners.get('restore:recipe-second')();
  assert.equal(requests[0].path,'/api/preview/restore');
  assert.equal(requests[0].body.id,'recipe-second');
  listeners.get('history-category:reconciliation')();
  listeners.get('restore:merge-first')();
  assert.equal(requests[1].body.id,'merge-first');
});

test('type filters combine with categories and include multi-area saves without narrowing rollback',()=>{
  const {context,content,listeners,requests}=setup();
  const mixed=row('mixed','Quest and recipe changes','gameplay',['quests','crafting']);
  mixed.files.push({path:'custom-quests/new.quest'});
  context.renderHistory([row('drop','Drop edit','gameplay',['drops']),mixed,row('merge','Merge quest','reconciliation',['quests'])]);
  listeners.get('type')({target:{value:'quests'}});
  assert.match(content.innerHTML,/Quest and recipe changes/);
  assert.doesNotMatch(content.innerHTML,/Drop edit|Merge quest<\/h3>/);
  assert.match(content.innerHTML,/Gameplay changes \(1\)/);
  assert.match(content.innerHTML,/Update reconciliations \(1\)/);
  assert.match(content.innerHTML,/Quests · Crafting/);
  assert.match(content.innerHTML,/Rollback restores the entire save/);
  listeners.get('restore:mixed')();
  assert.deepEqual(requests[0].body.id,'mixed');
  assert.equal(Object.keys(requests[0].body).length,1);
  listeners.get('history-category:all')();
  assert.match(content.innerHTML,/Merge quest<\/h3>/);
  listeners.get('type')({target:{value:'crafting'}});
  assert.match(content.innerHTML,/Quest and recipe changes/);
  assert.doesNotMatch(content.innerHTML,/Drop edit|Merge quest<\/h3>/);
  listeners.get('type')({target:{value:'fishing'}});
  assert.match(content.innerHTML,/No saved changes match this type/);
  assert.doesNotMatch(content.innerHTML,/data-restore=/);
});

test('unknown legacy areas remain discoverable as other files',()=>{
  const {context,content,listeners}=setup();
  const legacy=row('old','Older save','gameplay');delete legacy.areas;
  context.renderHistory([legacy]);
  listeners.get('type')({target:{value:'files'}});
  assert.match(content.innerHTML,/Older save/);
  assert.match(content.innerHTML,/Other server files/);
});
