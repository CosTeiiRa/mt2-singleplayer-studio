'use strict';
(function(root){
  const settings=[
    {id:'world',label:'World & features',group:'World & features',icon:'☷',description:'Language, inventory, starter equipment and optional game systems.'},
    {id:'progression',label:'Progression & difficulty',group:'Progression & difficulty',icon:'↗',description:'Difficulty, level limits, waiting times and new-world rates.'},
    {id:'drops',label:'Drops & economy',group:'Drops & economy',icon:'◇',description:'Extra rewards, scrolls, exchanges, chest rules and prices.'},
    {id:'bots',label:'Bots & population',group:'Bots & population',icon:'♧',description:'Bot counts, kingdoms, arrivals and channel distribution.'}
  ];
  const files=[
    {id:'drops',label:'Drops & rewards',icon:'◇',description:'Common loot, material drops, chest tables and reward overrides.'},
    {id:'crafting',label:'Crafting & shops',icon:'⚒',description:'Cube recipes, NPC crafting definitions and shop configuration.'},
    {id:'maps',label:'Maps & spawns',icon:'⌖',description:'Monster groups, boss schedules and map-specific spawn files.'},
    {id:'items',label:'Items, fishing & alchemy',icon:'◈',description:'Potion bonuses, fishing rewards and Dragon Soul tables.'},
    {id:'quests',label:'Quest scripts & helpers',icon:'▤',description:'Original quest sources, shared helpers and Studio quest files.'},
    {id:'events',label:'Skills & events',icon:'✦',description:'Skill power, OX questions and event configuration.'},
    {id:'other',label:'Other & build overrides',icon:'▧',description:'Remaining world files and overrides that do not fit another topic.'}
  ];
  function settingTopic(row){return settings.find(section=>section.group===row.group)?.id||'world'}
  function fileTopic(row){
    const path=String(row.id||'').replaceAll('\\','/').toLowerCase(),base=path.split('/').at(-1),category=row.category;
    if(category==='Crafting'||category==='Shops'||/^cube(?:\.|$)/.test(base)||/^(?:shop_|refine_)/.test(base)||/crafting_data\.lua$/.test(base))return 'crafting';
    if(category==='Drops'||/^(?:mob_drop_item|special_item_group|common_drop_item|etc_drop_item|drop_item_group)(?:\.|$)/.test(base))return 'drops';
    if(category==='Items'||category==='Fishing')return 'items';
    if(['Quests','Package quests','Custom quests'].includes(category)||path.includes('/quest/'))return 'quests';
    if(category==='Spawns & maps'||path.includes('/map/')||base.startsWith('special_spawns')||['forkedmapindex.txt','bluedragon.lua','monkey_dungeon.lua'].includes(base))return 'maps';
    if(category==='Skills'||category==='Events'||['oxquiz.lua','skill_power.txt'].includes(base))return 'events';
    return 'other';
  }
  function mapFolder(row){const path=String(row.id||'').replaceAll('\\','/');return path.includes('/map/')?path.split('/map/')[1].split('/')[0]:'shared'}
  function parse(value){
    const [page,requested]=String(value||'overview').replace(/^#/,'').split('/');
    if(!['settings','files'].includes(page))return {page,section:null,route:page};
    const sections=page==='settings'?settings:files;
    const section=['menu','all',...sections.map(s=>s.id)].includes(requested)?requested:'menu';
    return {page,section,route:section==='menu'?page:page+'/'+section};
  }
  function matchingSettings(rows,section,query=''){
    const term=query.toLowerCase().trim();
    return rows.filter(row=>(section==='all'||settingTopic(row)===section)&&`${row.key} ${row.label} ${row.group}`.toLowerCase().includes(term));
  }
  function matchingFiles(rows,section,query='',category='all',folder='all'){
    const term=query.toLowerCase().trim();
    return rows.filter(row=>(section==='all'||fileTopic(row)===section)&&(category==='all'||row.category===category)&&(section!=='maps'||folder==='all'||mapFolder(row)===folder)&&`${row.name} ${row.id} ${row.category}`.toLowerCase().includes(term));
  }
  const api={settings,files,settingTopic,fileTopic,mapFolder,parse,matchingSettings,matchingFiles};
  if(typeof module==='object'&&module.exports)module.exports=api;else root.StudioNavigation=api;
})(typeof window==='undefined'?globalThis:window);

function configSections(page){return page==='settings'?StudioNavigation.settings:StudioNavigation.files}
function configTopicCount(page,id){return page==='settings'?S.settings.settings.filter(r=>id==='all'||StudioNavigation.settingTopic(r)===id).length:S.files.filter(r=>id==='all'||StudioNavigation.fileTopic(r)===id).length}
function configTopicMenu(page){
  const unit=page==='settings'?'settings':'files';
  return `<form class="config-menu-search" id="config-menu-search"><div class="searchbox"><span aria-hidden="true">⌕</span><input id="config-menu-query" aria-label="Search all ${unit}" placeholder="Search all ${unit} by name or keyword…"></div><button class="button" type="submit">Search all ${unit}</button></form><div class="config-topic-grid ${page==='settings'?'config-settings-topics':''}">${configSections(page).map(s=>`<button class="config-topic" data-config-route="${page+'/'+s.id}"><span class="config-topic-icon" aria-hidden="true">${s.icon}</span><span><strong>${s.label}</strong><span>${s.description}</span><small>${configTopicCount(page,s.id)} ${unit}</small></span><span class="config-topic-arrow" aria-hidden="true">→</span></button>`).join('')}</div><div class="config-menu-all"><button class="button ghost" data-config-route="${page}/all">Browse all ${configTopicCount(page,'all')} ${unit}</button></div>`;
}
function configSubmenu(page){
  const selected=S.section;
  return `<div class="config-subnav" role="navigation" aria-label="${page==='settings'?'World settings':'Configuration file'} topics"><button data-config-route="${page}" class="config-back">← All topics</button>${[...configSections(page),{id:'all',label:page==='settings'?'All settings':'All files'}].map(s=>`<button data-config-route="${page+'/'+s.id}" ${selected===s.id?'class="selected" aria-current="page"':''}>${s.label}<span>${configTopicCount(page,s.id)}</span></button>`).join('')}</div>`;
}
function bindConfigNavigation(page){
  $$('[data-config-route]',$('#content')).forEach(button=>button.onclick=()=>attempt(()=>navigate(button.dataset.configRoute)));
  const search=$('#config-menu-search');
  if(search)search.onsubmit=e=>{e.preventDefault();const term=$('#config-menu-query').value;attempt(async()=>{await navigate(page+'/all');if(S.route!==page+'/all')return;if(page==='settings'){S.settingSearch=term;$('#setting-search').value=term;renderSettingGrid(term)}else{S.fileSearch=term;$('#file-search').value=term;renderFileList()}})};
}
function syncSidebar(){
  $$('nav [data-page]').forEach(button=>{
    const active=button.dataset.page===S.page;button.classList.toggle('active',active);
    if(active){button.setAttribute('aria-current','page');const group=button.closest('details');if(group)group.open=true}else button.removeAttribute('aria-current');
  });
  const configured=['drops','quests','crafting','settings','files'].includes(S.page);
  $('#crumb-context').textContent=configured?'Game configuration':'Workspace';
  const section=configSections(S.page).find(s=>s.id===S.section);
  $('#crumb').textContent=titles[S.page]+(section?' / '+section.label:S.section==='all'?' / All':'');
}
function initSidebarNavigation(){
  const key=wPrefix()+'sidebar-groups';let saved={};
  try{saved=JSON.parse(localStorage.getItem(key)||'{}')}catch(error){}
  $$('nav details[data-nav-group]').forEach(group=>{
    if(typeof saved[group.dataset.navGroup]==='boolean')group.open=saved[group.dataset.navGroup];
    group.addEventListener('toggle',()=>{saved[group.dataset.navGroup]=group.open;try{localStorage.setItem(key,JSON.stringify(saved))}catch(error){}});
  });
  window.addEventListener('hashchange',()=>{const route=StudioNavigation.parse(location.hash.slice(1)||'overview').route;if(route!==S.route)navigate(route)});
}
