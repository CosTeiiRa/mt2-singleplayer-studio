'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
function helpers(images=[]){
  const context={esc:value=>String(value).replaceAll('"','&quot;'),document:{createElement:()=>({setAttribute(){}})},$$:()=>images};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('function iconPlaceholder('),source.indexOf('function pool(')),context);
  return context;
}
function image(complete,width){
  return {dataset:{iconId:'30353'},complete,naturalWidth:width,handlers:[],addEventListener(event,handler){this.handlers.push(handler)},replaceWith(node){this.replacement=node}};
}
test('observed item IDs can render icons without a catalog entry',()=>{
  const ctx=helpers();
  assert.match(ctx.icon('30353'),/src="\/icons\/30353"/);
  assert.match(ctx.icon('s8001'),/item-placeholder/);
  assert.doesNotMatch(ctx.icon('s8001'),/<img/);
});
test('a cached image failure is replaced even if the error event already fired',()=>{
  const img=image(true,0);helpers([img]).bindImages();
  assert.equal(img.replacement.className,'item-icon item-placeholder');
  assert.match(img.replacement.title,/#30353/);
});
test('lazy images wait for load and get only one error listener',()=>{
  const img=image(false,0),ctx=helpers([img]);ctx.bindImages();ctx.bindImages();
  assert.equal(img.replacement,undefined);
  assert.equal(img.handlers.length,1);
  img.handlers[0]();assert.equal(img.replacement.textContent,'◇');
});
test('successful images are retained',()=>{
  const img=image(true,32);helpers([img]).bindImages();assert.equal(img.replacement,undefined);
});
