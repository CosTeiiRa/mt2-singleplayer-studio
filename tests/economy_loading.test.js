'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/economy.js'),'utf8');
function fixture(storage=new Map()){
  const nodes=new Map(),views=[],pending=[];
  const $=key=>{if(!nodes.has(key))nodes.set(key,{textContent:'',innerHTML:'',disabled:false,attrs:{},classList:{toggle(){}},setAttribute(k,v){this.attrs[k]=v}});return nodes.get(key)};
  const ctx={URLSearchParams,S:{page:'economy',data:{root:'world-a'}},$, $$:()=>[],sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
    api:()=>new Promise((resolve,reject)=>pending.push({resolve,reject})),esc:String,toast(){},renderEconomyView:()=>views.push(ctx.state.data)};
  vm.createContext(ctx);vm.runInContext(source.slice(0,source.indexOf('function renderEconomyShell('))+'\nthis.state=Econ;',ctx);
  return {ctx,nodes,views,pending,storage,key:()=>JSON.stringify([ctx.S.data.root,ctx.state.filters])};
}
const observation=at=>({at,connected:true,filters:{},items:[]});
test('economy keeps the matching observation visible during refresh and after failure',async()=>{
  const f=fixture(),saved=observation(100);f.ctx.state.cache.set(f.key(),saved);
  const request=f.ctx.loadEconomy();assert.equal(f.views.at(-1),saved);
  assert.equal(f.nodes.get('#eco-connection').textContent,'PREVIOUS OBSERVATION');
  assert.match(f.nodes.get('#eco-status').textContent,/Updating/);
  f.pending[0].reject(Error('Connection lost'));await request;
  assert.equal(f.ctx.state.data,saved);assert.match(f.nodes.get('#eco-status').textContent,/Refresh failed/);
  assert.equal(f.nodes.get('#economy-view').attrs['aria-busy'],'false');
});
test('economy ignores late responses from an earlier filter selection',async()=>{
  const f=fixture(),first=f.ctx.loadEconomy();f.ctx.state.filters.days=28;
  const second=f.ctx.loadEconomy(),latest=observation(200);
  f.pending[1].resolve(latest);await second;f.pending[0].resolve(observation(100));await first;
  assert.equal(f.ctx.state.data,latest);assert.equal(f.views.length,1);
  assert.equal(JSON.parse(f.storage.get('studio-economy-last')).data.at,200);
});
test('session cache survives reload and cannot cross world or filter boundaries',async()=>{
  const f=fixture();f.storage.set('studio-economy-last',JSON.stringify({key:f.key(),data:observation(100)}));
  const loaded=f.ctx.loadEconomy();assert.equal(f.views.at(-1).at,100);
  f.pending[0].resolve(observation(200));await loaded;
  const other=fixture(f.storage);other.ctx.S.data.root='world-b';const request=other.ctx.loadEconomy();
  assert.equal(other.views.length,0);assert.equal(other.ctx.state.data,null);
  other.pending[0].reject(Error('Offline'));await request;
  const filtered=fixture(f.storage);filtered.ctx.state.filters.days=1;const next=filtered.ctx.loadEconomy();
  assert.equal(filtered.views.length,0);filtered.pending[0].reject(Error('Offline'));await next;
});
