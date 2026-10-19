'use strict';
// Both editors use the game's existing menus. Unreachable legacy Cube entries
// remain available explicitly, without suggesting they are active NPC crafts.
const CraftUI={system:'active',npc:'all',output:''};
function craftingRoutes(){
  return [...S.craftingAccess.npcs.map(n=>({...n,system:'cube'})),
    ...(S.craftingAccess.native.available?S.craftingAccess.native.npcs:[])];
}
function recipeIdentity(r){return `${r.source}:${r.index}:${r.window||''}`}
function craftingCandidates(){
  const term=(S.recipeSearch||'').toLowerCase();
  return S.recipes.filter(r=>(CraftUI.system==='all'||CraftUI.system==='legacy'?!r.npcSupported||CraftUI.system==='all':CraftUI.system==='active'?r.npcSupported:r.system===CraftUI.system&&r.npcSupported)
    &&(CraftUI.npc==='all'||(r.npcIds||[r.fields.npc]).includes(CraftUI.npc))
    &&(!CraftUI.output||r.rewards.some(e=>e.item===CraftUI.output))
    &&`${r.name} ${r.npcName} ${(r.npcIds||[r.fields.npc]).join(' ')} ${r.index} ${[...r.materials,...r.rewards].map(e=>`${name('item',e.item)} ${e.item}`).join(' ')}`.toLowerCase().includes(term));
}
const cubeRecipeRows=renderRecipeRows;
renderRecipeRows=function(kind){
  cubeRecipeRows(kind);
  if(S.recipe.system==='native')$$('[data-recipe-qty]',$('#recipe-'+kind)).forEach(input=>input.max='2147483647');
  const add=$(`[data-add-recipe="${kind}"]`);
  if(add)add.disabled=S.recipe[kind].length>=(kind==='materials'?10:S.recipe.system==='native'?1:5);
};
renderCrafting=function(){
  const native=S.craftingAccess.native;
  const npcs=[...new Set(craftingRoutes().map(n=>n.id))];
  $('#content').innerHTML=head('GAME CONFIGURATION','Crafting recipes','Choose an existing crafting NPC. Studio uses the recipe system behind its menu.','<div class="editor-actions"><button class="button" id="refresh-crafting">Refresh from server</button><button class="button primary" id="new-recipe">＋ New recipe</button></div>')+
    `<p class="notice info">${npcs.length} NPCs with identified crafting menus · Cube and native crafting. Level, quest, herbalism and guild access conditions still apply. Saving and applying are separate.</p>`+
    (!native.available?`<p class="notice">Native crafting is unavailable: ${esc(native.error)}. Refresh after the database is available. Cube editing remains available.</p>`:'')+
    (native.conflicts.length?`<div class="notice recipe-conflict-banner"><strong>${native.conflicts.length} customised native crafting fields changed on the server.</strong><button class="button" id="review-craft-conflicts">Review crafting conflicts</button></div>`:'')+
    `<div class="toolbar"><div class="searchbox"><span>⌕</span><input id="recipe-search" value="${esc(S.recipeSearch||'')}" placeholder="Find a reward, ingredient, NPC or recipe ID…" aria-label="Search crafting recipes"></div></div>
    <div class="editor-filters"><label>System<select id="recipe-system-filter">${[['active','All active crafting'],['native','Native crafting'],['cube','Cube'],['legacy','Legacy Cube · menu unconfirmed'],['all','All entries including legacy']].map(([v,t])=>`<option value="${v}" ${CraftUI.system===v?'selected':''}>${t}</option>`).join('')}</select></label><label>NPC<select id="recipe-npc-filter"><option value="all">All NPCs</option>${[...new Set(S.recipes.flatMap(r=>r.npcIds||[r.fields.npc]).concat(npcs))].sort((a,b)=>name('mob',a).localeCompare(name('mob',b))).map(id=>`<option value="${esc(id)}" ${CraftUI.npc===id?'selected':''}>${esc(name('mob',id))} · #${esc(id)}</option>`).join('')}</select></label><button class="button small" id="recipe-output-filter">${CraftUI.output?esc(name('item',CraftUI.output)):'Produces item…'}</button><button class="button small" id="recipe-filter-clear">Clear filters</button></div>
    <div class="editor-layout"><div class="panel"><div class="list-head" id="recipe-count"></div><div class="entity-list" id="recipe-list"></div></div><div class="panel" id="recipe-detail"><div class="empty"><div class="empty-symbol">⚒</div>Choose a recipe, or create one at an existing crafting NPC.</div></div></div>`;
  $('#new-recipe').disabled=!craftingRoutes().length;
  $('#new-recipe').onclick=()=>{if(leaveOkay())chooseCraftNpc(null,route=>startCraftRecipe(route))};
  $('#refresh-crafting').onclick=()=>{if(leaveOkay())attempt(async()=>{const data=await api('/api/crafting?fresh=1');S.recipes=data.recipes;S.craftingAccess=data.access;S.recipe=null;renderCrafting();toast('Crafting refreshed from the current database and saved configuration.')})};
  $('#recipe-search').oninput=e=>{S.recipeSearch=e.target.value;renderRecipeList()};
  $('#recipe-system-filter').onchange=e=>{CraftUI.system=e.target.value;renderRecipeList()};
  $('#recipe-npc-filter').onchange=e=>{CraftUI.npc=e.target.value;renderRecipeList()};
  $('#recipe-output-filter').onclick=()=>pick('item',null,e=>{CraftUI.output=e.id;$('#recipe-output-filter').textContent=e.name;renderRecipeList()});
  $('#recipe-filter-clear').onclick=()=>{CraftUI.system='active';CraftUI.npc='all';CraftUI.output='';S.recipeSearch='';renderCrafting();if(S.recipe)renderRecipeDetail()};
  $('#review-craft-conflicts')?.addEventListener('click',reviewCraftingConflicts);
  renderRecipeList();
};
renderRecipeList=function(){
  const rows=craftingCandidates();
  $('#recipe-count').textContent=`${rows.length} RECIPES`;
  $('#recipe-list').innerHTML=rows.map((r,i)=>`<button class="entity ${S.recipe&&recipeIdentity(r)===recipeIdentity(S.recipe)?'selected':''}" data-recipe="${i}" ${r.rewards[0]?.item?itemHelpAttrs(r.rewards[0].item):''}>${itemContent(r.rewards[0]?.item,{title:r.name,detail:`${r.npcName} · ${r.system==='native'?'Native':'Cube'} · ${r.fields.percent}%${r.npcSupported?'':' · menu unconfirmed'}${r.conflicted?' · review server change':''}`})}</button>`).join('')||'<div class="empty">No matching recipes. New recipes can also use NPCs with empty crafting windows.</div>';
  $$('[data-recipe]').forEach(button=>button.onclick=()=>{if(!leaveOkay())return;S.recipe=structuredClone(rows[Number(button.dataset.recipe)]);S.recipe.originalWindow=S.recipe.window;dirty(false);renderRecipeDetail();renderRecipeList()});
  bindImages($('#recipe-list'));
};
function chooseCraftNpc(system,choose){
  const routes=craftingRoutes().filter(r=>!system||r.system===system).sort((a,b)=>a.name.localeCompare(b.name));
  toolDialog('Choose an existing crafting NPC',`<p>The recipe uses the system this NPC already opens. NPCs sharing a window use the same recipe list.</p><div class="searchbox"><input id="craft-npc-search" placeholder="Search NPC name or ID…" aria-label="Search crafting NPCs"></div><div class="craft-npc-list">${routes.map((r,i)=>`<button class="file-entry" data-craft-npc="${i}"><strong>${esc(r.name)} · #${esc(r.id)}</strong><small>${r.system==='native'?'Native crafting · window #'+esc(r.window):'Cube crafting'}</small></button>`).join('')}</div>`);
  $('#craft-npc-search').oninput=e=>{$$('[data-craft-npc]').forEach(button=>{button.hidden=!`${routes[button.dataset.craftNpc].name} ${routes[button.dataset.craftNpc].id}`.toLowerCase().includes(e.target.value.toLowerCase())})};
  $$('[data-craft-npc]').forEach(button=>button.onclick=()=>{$('#tool-dialog').close();choose(routes[button.dataset.craftNpc])});
}
function startCraftRecipe(route,from){
  workspaceStash();
  CraftUI.system='active';CraftUI.npc=route.id;CraftUI.output='';S.recipeSearch='';
  $('#recipe-system-filter').value='active';$('#recipe-npc-filter').value=route.id;$('#recipe-search').value='';$('#recipe-output-filter').textContent='Produces item…';
  const native=route.system==='native',table=native?null:S.craftingAccess.tables[route.source];
  S.recipe={system:route.system,source:native?'native':route.source,index:-1,new:true,name:from?'Copy of '+from.name:'New recipe',
    hash:native?'':table.hash,configHash:S.craftingAccess.native.configHash,window:route.window,originalWindow:route.window,
    file:native?'linux-port/docker/game/share-add/studio-crafting.json':table.file,
    sourceHashes:Object.fromEntries(Object.entries(S.craftingAccess.tables).map(([k,v])=>[k,v.hash])),
    npcName:route.name,npcIds:[route.id],npcSupported:true,fields:{npc:route.id,percent:from?.fields.percent||'100',gold:from?.fields.gold||'0'},
    requirements:structuredClone(from?.requirements||{req_level:0,req_progress:0,recipe_vnum:0}),materials:structuredClone(from?.materials||[]),rewards:structuredClone(from?.rewards||[])};
  dirty(true);renderRecipeDetail();renderRecipeList();
}
renderRecipeDetail=function(){
  const r=S.recipe,native=r.system==='native';
  const sharing=native?S.craftingAccess.native.npcs.filter(n=>n.window===r.window).map(n=>n.name):[];
  $('#recipe-detail').innerHTML=`<div class="panel-header"><h2>${esc(r.name)}</h2><span class="pill gold">${r.new?'NEW · ':''}${native?'NATIVE':'CUBE'}</span></div>
    <div class="editor-actions"><button class="button small" id="clone-recipe">Clone to a crafting NPC…</button><button class="button small" id="recipe-variants">Compare output variants</button></div>
    ${!r.npcSupported?'<p class="notice">Legacy Cube entry: no matching menu was identified. It may be unused by this version. Clone it to an active crafting NPC to make a new accessible recipe.</p>':''}
    ${r.conflicted?'<p class="notice">The server changed a customised field in this recipe. Review crafting conflicts before editing or applying it.</p>':''}
    <div class="panel-body"><div class="form-grid"><div class="field full"><label>${native?'Native crafting NPC / window':'Compatible Cube NPC'}</label><button class="button" id="recipe-npc">${esc(name('mob',r.fields.npc))} · #${esc(r.fields.npc)}</button>${native?`<small>Window #${esc(r.window)} · ${esc(sharing.join(', '))}</small>`:''}</div><div class="field"><label for="recipe-percent">Success chance %</label><input id="recipe-percent" type="number" min="1" max="100" value="${esc(r.fields.percent)}"></div><div class="field"><label for="recipe-gold">Yang cost</label><input id="recipe-gold" type="number" min="0" max="${native?'2147483647':'100000000'}" value="${esc(r.fields.gold||'0')}"></div></div>
    ${native?`<p class="small-text">NPC and quest requirements remain in effect. Native pricing can also have a higher minimum set by an existing event flag.</p>${r.sharedWith?.length?`<p class="notice">This recipe definition is also used at ${esc(r.sharedWith.join(', '))}. Ingredient, reward and chance edits affect those windows too. Clone for an independent recipe.</p>`:''}<details class="craft-requirements"><summary>Recipe requirements</summary><div class="form-grid"><div class="field"><label for="recipe-req_level">Minimum level</label><input id="recipe-req_level" type="number" min="0" max="255" value="${esc(r.requirements.req_level)}"></div><div class="field"><label for="recipe-req_progress">Required learning progress</label><input id="recipe-req_progress" type="number" min="0" max="2147483647" value="${esc(r.requirements.req_progress)}"></div><div class="field full"><label for="recipe-recipe_vnum">Learning progress key</label><input id="recipe-recipe_vnum" type="number" min="0" max="2147483647" value="${esc(r.requirements.recipe_vnum)}"><small>A game progress key, rather than an item ID. Keep existing values unless changing the learning requirement.</small></div></div></details>`:''}</div>
    <div class="panel-header"><h3>Ingredients</h3><button class="button small ghost" data-add-recipe="materials">＋ Add ingredient</button></div><div id="recipe-materials"></div><div class="panel-header"><h3>${native?'Reward · one item type':'Rewards'}</h3><button class="button small ghost" data-add-recipe="rewards">＋ Add reward</button></div><div id="recipe-rewards"></div>
    <div class="drop-save"><span id="dirty-label">Saved configuration · no changes</span><button class="button ghost danger" id="remove-recipe" ${r.new?'disabled':''}>${native?'Remove from NPC':'Remove recipe'}</button><button class="button primary" id="review-recipe" ${r.conflicted?'disabled':''}>Review changes →</button></div><div class="panel-body path">${native?'Native recipe #'+esc(r.index)+' · ':''}${esc(r.file)}</div>`;
  ['percent','gold'].forEach(key=>$('#recipe-'+key).oninput=e=>{r.fields[key]=e.target.value;dirty()});
  if(native)['req_level','req_progress','recipe_vnum'].forEach(key=>$('#recipe-'+key).oninput=e=>{r.requirements[key]=e.target.value;dirty()});
  $('#recipe-npc').onclick=()=>chooseCraftNpc(native?'native':'cube',route=>{r.fields.npc=route.id;r.window=route.window;r.npcSupported=true;r.npcName=route.name;r.npcIds=[route.id];dirty();renderRecipeDetail()});
  $$('[data-add-recipe]').forEach(button=>button.onclick=()=>{const kind=button.dataset.addRecipe;if(r[kind].length>=(kind==='materials'?10:native?1:5))return toast(kind==='materials'?'At most 10 ingredients.':native?'Native crafting has exactly one reward item type.':'At most 5 rewards.',true);pick('item',e=>e.id!=='1',e=>{r[kind].push({item:e.id,count:'1'});dirty();renderRecipeRows(kind)})});
  $('#review-recipe').onclick=()=>preview('/api/preview/recipe',r);
  $('#remove-recipe').onclick=()=>{if(S.dirty)return toast('Save or discard the current draft before removing a saved recipe.',true);preview('/api/preview/recipe-delete',r)};
  $('#clone-recipe').onclick=()=>{if(leaveOkay())chooseCraftNpc(null,route=>startCraftRecipe(route,r))};
  $('#recipe-variants').onclick=()=>{const rows=S.recipes.filter(x=>x.rewards.some(e=>r.rewards.some(t=>t.item===e.item)));toolDialog('Recipes for the same output',`<p>Configured cost per attempt. Existing game rules determine consumption on failure.</p><div class="table-wrap"><table><thead><tr><th>System / NPC</th><th>Ingredients</th><th>Yang</th><th>Success</th></tr></thead><tbody>${rows.map(v=>`<tr><td>${esc(v.system+' / '+v.npcName)}</td><td>${v.materials.map(e=>itemReference(e.item,{detail:'×'+e.count})).join('')}</td><td>${esc(v.fields.gold||'0')}</td><td>${esc(v.fields.percent)}%</td></tr>`).join('')}</tbody></table></div>`)};
  renderRecipeRows('materials');renderRecipeRows('rewards');
  if(native)$$('#recipe-detail [data-recipe-qty]').forEach(input=>input.max='2147483647');
  dirty(r.new||S.dirty);workspaceRestore();
};
async function reviewCraftingConflicts(){
  if(!leaveOkay())return;
  await attempt(async()=>{
    const report=await api('/api/crafting/conflicts');
    if(!report.conflicts.length)return toast('No native crafting conflicts. Refresh to see the current recipes.');
    const value=v=>typeof v==='object'?JSON.stringify(v):String(v??'(absent)');
    toolDialog('Review customised crafting changes',`<p>Only fields changed by Studio are reviewed. Other server changes are retained. Saving choices does not restart the game.</p>${report.conflicts.map((c,i)=>`<article class="craft-conflict"><h3>Recipe #${esc(c.recipe)} · ${esc(c.field)}</h3><p>Previous: ${esc(value(c.expected))}</p><p>Server: ${esc(value(c.server))}</p><p>Studio: ${esc(value(c.studio))}</p>${c.reason?`<p class="notice">${esc(c.reason)}</p>`:`<label>Version to apply<select data-craft-choice="${i}"><option value="">Choose…</option><option value="studio">Keep Studio value</option><option value="server">Accept server value</option></select></label>`}</article>`).join('')}<button class="button primary" id="save-craft-choices">Review selected changes</button>`);
    $('#save-craft-choices').onclick=()=>{const choices={};$$('[data-craft-choice]').forEach(select=>{const c=report.conflicts[Number(select.dataset.craftChoice)];choices[c.recipe+':'+c.field]=select.value});$('#tool-dialog').close();preview('/api/preview/crafting-resolve',{signature:report.signature,choices})};
  });
}
