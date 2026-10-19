'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
function fixture(){
  const ctx={S:{itemMap:{19:{name:'Current Sword+9',iconAvailable:true},20:{name:'Unnamed item #20',iconAvailable:false,nameStatus:'unnamed'}}},
    esc:value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
    icon:id=>`<img src="/icons/${id}">`,name:(kind,id)=>'#'+id};
  vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function itemHelpAttrs('),source.indexOf('function bindItemUsageLinks(')),ctx);return ctx;
}
test('all item references prefer the shared current catalogue over stale result names',()=>{
  const ctx=fixture(),html=ctx.itemReference('19',{fallback:'Old name',detail:'Crafting'});
  assert.match(html,/Current Sword\+9/);assert.doesNotMatch(html,/Old name/);
  assert.match(html,/data-help-item="19"/);assert.match(html,/data-inspect-item="19"/);assert.match(html,/#19/);
});
test('missing names and icons receive the same labels everywhere',()=>{
  const html=fixture().itemContent('20');assert.match(html,/Icon unavailable/);assert.match(html,/Name unavailable/);
});
test('unknown IDs remain inspectable and source text is escaped',()=>{
  const html=fixture().itemReference('999',{fallback:'<img bad>',detail:'<script>bad'});
  assert.match(html,/data-inspect-item="999"/);assert.match(html,/&lt;img bad>/);assert.match(html,/&lt;script>/);
});
test('recipe titles can retain their own identity without changing the shared item name',()=>{
  const ctx=fixture();assert.match(ctx.itemContent('19',{title:'My recipe'}),/My recipe/);
  assert.equal(ctx.S.itemMap['19'].name,'Current Sword+9');
});
test('error notifications use the top layer and persist until dismissed',()=>{
  const nodes=new Map(),timers=[];
  const $=id=>{if(!nodes.has(id))nodes.set(id,{hidden:true,classList:{toggle(){}},setAttribute(k,v){this[k]=v},matches(){return !!this.open},showPopover(){this.open=true},hidePopover(){this.open=false}});return nodes.get(id)};
  const ctx={$,setTimeout:(fn,ms)=>timers.push({fn,ms}),clearTimeout(){}};
  vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('let toastTimer;'),source.indexOf('async function attempt(')),ctx);
  ctx.toast('Cannot save',true);assert.equal($('#toast').open,true);assert.equal($('#toast-announcement').role,'alert');
  assert.equal($('#toast-message').textContent,'Cannot save');assert.equal(timers.length,0);
  ctx.closeToast();assert.equal($('#toast').hidden,true);assert.equal($('#toast').open,false);
  ctx.toast('Saved');assert.equal(timers[0].ms,6500);
});

test('creature references share portraits, names and game levels with honest category fallbacks',()=>{
  const ctx={S:{mobMap:{101:{name:'Wolf <test>',level:1,category:'monster',iconAvailable:true,iconKind:'portrait'},102:{name:'Boss',level:50,category:'boss',iconAvailable:true,iconKind:'category'},103:{name:'Unknown',level:20,category:'metin',iconAvailable:false}}},esc:value=>String(value).replaceAll('<','&lt;')};
  vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function mobIcon('),source.indexOf('function helpDetails(')),ctx);
  assert.match(ctx.mobContent(101),/src="\/mob-icons\/101"/);
  assert.match(ctx.mobContent(101),/Wolf &lt;test>/);assert.match(ctx.mobContent(101),/Lv. 1/);
  assert.match(ctx.mobIcon(102),/Client category badge/);
  assert.doesNotMatch(ctx.mobIcon(103),/<img/);
});
