'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web/game_dashboard.js'),'utf8');
function fixture(){
  const content={innerHTML:''},links=[{removeAttribute(k){delete this[k]}}],requests=[];
  const ctx={S:{page:'economy',navigation:1,data:{gameDashboard:{economyUrl:'http://127.0.0.1:8890/economy'}}},
    esc:s=>String(s).replaceAll('<','&lt;').replaceAll('"','&quot;'),head:()=>'<h1>Economy</h1>',
    $:()=>content,$$:()=>links,api:async url=>{requests.push(url);return {economyUrl:'http://127.0.0.1:8890/economy',archiveAvailable:true}}};
  vm.createContext(ctx);vm.runInContext(source,ctx);return {ctx,content,links,requests};
}
test('sidebar and homepage shortcuts use the configured game URL in a separate tab',()=>{
  const {ctx,links}=fixture();ctx.bindGameDashboardLinks();
  assert.equal(links[0].href,'http://127.0.0.1:8890/economy');assert.equal(links[0].target,'_blank');assert.equal(links[0].rel,'noopener noreferrer');
  ctx.S.data.gameDashboard={};ctx.bindGameDashboardLinks();assert.equal(links[0].href,'#economy');assert.equal(links[0].target,undefined);
});
test('old Economy bookmarks open only shortcut metadata and the saved archive download',async()=>{
  const {ctx,content,requests}=fixture();await ctx.renderGameEconomy();
  assert.deepEqual(requests,['/api/game-dashboard']);assert.match(content.innerHTML,/Open game economy/);assert.match(content.innerHTML,/\/api\/economy\/archive/);
  assert.doesNotMatch(content.innerHTML,/eco-refresh|setInterval/);
});
test('new installations do not show a nonexistent Studio archive',async()=>{
  const {ctx,content}=fixture();ctx.api=async()=>({economyUrl:'http://127.0.0.1:7790/economy',archiveAvailable:false});await ctx.renderGameEconomy();
  assert.doesNotMatch(content.innerHTML,/Download history/);
});
test('late metadata cannot replace another editor and configuration errors are escaped',async()=>{
  const {ctx,content}=fixture();let resolve;ctx.api=()=>new Promise(done=>resolve=done);
  const pending=ctx.renderGameEconomy();ctx.S.navigation=2;ctx.S.page='crafting';resolve({});await pending;assert.equal(content.innerHTML,'');
  ctx.S.page='economy';ctx.api=async()=>({economyUrl:null,error:'<bad configuration>',archiveAvailable:false});await ctx.renderGameEconomy();
  assert.match(content.innerHTML,/&lt;bad configuration>/);assert.doesNotMatch(content.innerHTML,/<bad configuration>/);
});

test('item inspectors link directly to the matching game economy item without fetching analytics',()=>{
  const {ctx,links,requests}=fixture();links[0].dataset={gameEconomyItem:'25041'};ctx.bindGameDashboardLinks();
  assert.equal(links[0].href,'http://127.0.0.1:8890/economy/item/25041');assert.deepEqual(requests,[]);
});
