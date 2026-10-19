'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const script=source.slice(source.indexOf('function backToItemResults(){'),source.indexOf('function renderItemUsage(data){'));
function fixture(inspectOnly=true){
  const search={value:'Dragon',focus(options){this.options=options}},results={scrollTop:480};
  const picker={open:true,close(){this.open=false}},usage={open:true,close(){this.open=false}},focus={isConnected:true,focus(options){this.options=options}};
  const ctx={S:{picker:{inspectOnly,filters:{category:'stones'},limit:200,callback:item=>ctx.selected=item},usageReturnFocus:focus},
    $:id=>({'#picker':picker,'#item-usage':usage,'#picker-search':search,'#picker-results':results})[id],
    hideItemHelp(){},browseItems(){ctx.browsed=true},esc:value=>String(value).replaceAll('<','&lt;').replaceAll('>','&gt;')};
  vm.createContext(ctx);vm.runInContext(script,ctx);return {ctx,picker,usage,search,results,focus};
}
test('exploring keeps the result picker open and Back preserves its search and scroll',()=>{
  const {ctx,picker,usage,search,results,focus}=fixture();
  ctx.choosePickerResult({id:'110000'});assert.equal(picker.open,true);assert.equal(ctx.selected.id,'110000');
  ctx.backToItemResults();assert.equal(usage.open,false);assert.equal(picker.open,true);
  assert.equal(search.value,'Dragon');assert.equal(results.scrollTop,480);assert.equal(ctx.S.picker.limit,200);
  assert.equal(focus.options.preventScroll,true);assert.equal(ctx.browsed,undefined);
});
test('editor selection still closes its picker and calls its editor callback',()=>{
  const {ctx,picker}=fixture(false);ctx.choosePickerResult({id:'10'});
  assert.equal(picker.open,false);assert.equal(ctx.selected.id,'10');
});
test('Back safely focuses search if catalogue refresh replaced the original result',()=>{
  const {ctx,search,focus}=fixture();focus.isConnected=false;ctx.backToItemResults();
  assert.equal(search.options.preventScroll,true);
});
test('inspection from an editor returns to its source instead of opening a new explorer',()=>{
  const {ctx,picker,focus}=fixture();picker.open=false;ctx.backToItemResults();
  assert.equal(focus.options.preventScroll,true);assert.equal(ctx.browsed,undefined);
});
test('configured effect text is escaped before rendering',()=>{
  const {ctx}=fixture();
  const html=ctx.itemEffectsMarkup({effects:[{title:'Base effects',values:['<script>bad()</script>'],note:'Calculated'}]});
  assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
});
