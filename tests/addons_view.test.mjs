// DOM boundary mocks exercise the embedded view contract; this is not browser QA.
import test from 'node:test';
import assert from 'node:assert/strict';

const nodes=new Map(),listeners=new Map();
const integrityTimers=new Map();let timerId=0;
globalThis.window={setTimeout:callback=>{integrityTimers.set(++timerId,callback);return timerId;},clearTimeout:id=>integrityTimers.delete(id),
  addEventListener:(kind,callback)=>listeners.set('window:'+kind,[callback])};
class Element {
  constructor(){this.children=[];this.dataset={};this.innerHTML='';this.open=false;this.className='';}
  set id(value){this._id=value;nodes.set(value,this);}get id(){return this._id;}
  append(child){this.children.push(child);}setAttribute(){}addEventListener(){}
  querySelector(selector){return selector.startsWith('#')?nodes.get(selector.slice(1))??null:null;}
  close(){this.open=false;}showModal(){this.open=true;}
}
globalThis.document={
  createElement:()=>new Element(),body:new Element(),
  querySelector:selector=>selector.startsWith('#')?nodes.get(selector.slice(1))??null:null,
  querySelectorAll:()=>[],
  addEventListener:(kind,handler)=>{const list=listeners.get(kind)??[];list.push(handler);listeners.set(kind,list);}
};
const views=await import('../web/addons.mjs');
const root=new Element();
let current=true,requests=[],opened;
const state={version:'0.1',installation:{kind:'installation',writable:false,path:'client'},installed:[],warnings:[],dependencies:{lzokay:false},world:{server_root:'world'},sandbox_targets:[],source_path:'client'};
const item={id:'community.example',name:'Example <unsafe>',version:'1.0',author:'Community',description:'An example',category:'Maps'};
const context=page=>({page,root,current:()=>current,toast:()=>{},openDrops:async id=>{opened=id;},openMapSource:async path=>{opened=path;},api:async(path)=>{
  requests.push(path);
  if(path.endsWith('/state'))return {ok:true,state};
  if(path.endsWith('/catalog'))return {ok:true,catalog:{items:[item]}};
  if(path.endsWith('/history'))return {ok:true,history:[]};
  if(path.endsWith('/repositories'))return {ok:true,repositories:[{id:'repo',name:'Creator <unsafe>',url:'https://example.test/catalog.json',publisher:'Creator',enabled:true,channel:'stable',package_count:1}]};
  if(path.endsWith('/updates'))return {ok:true,policy:'manual',updates:[]};
  if(path.endsWith('/releases'))return {ok:true,releases:[{id:'creator.extra',name:'Extra release',author:'Creator',description:'Repository fixture',category:'Maps',repository_id:'repo',repository_name:'Creator catalog',publisher:'Creator',releases:[{version:'1.0.0',cached:true}],latest:{version:'1.0.0',cached:true}}]};
  if(path.endsWith('/maps'))return {ok:true,maps:[{id:64,name:'Orc Valley'}]};
  if(path.includes('/map?'))return {ok:true,map:{id:64,name:'Orc Valley',width:1024,height:1024,image_url:'/api/addons/map-image?map=64',regions:[{name:'Chief Orc',mob_id:691,x:100,y:200,type:'boss',source:'map/boss.txt'}]}};
  if(path.endsWith('/diagnostics'))return {ok:true,diagnostics:{}};
  throw Error('Unexpected API '+path);
}});

test('embedded catalog uses the shared API, escapes metadata and exposes optional support guidance',async()=>{
  requests=[];await views.mount(context('addons'));
  assert.deepEqual(requests.slice(0,3),['/api/addons/state','/api/addons/catalog','/api/addons/history']);
  assert.match(root.innerHTML,/Example &lt;unsafe&gt;/);
  assert.match(root.innerHTML,/Install Add-on Support.bat/);
  assert.doesNotMatch(root.innerHTML,/<aside/);
});

test('add-on details show usage sections while the catalog shows only the summary',async()=>{
  const previous=item.description;
  item.description='## What it does\n\nSearch game data.\n\n## How to use\n\n1. Enter a character.\n2. Click Pocket Wiki.\n\n## Shortcuts\n\n- Ctrl+U: toggle.';
  try{
    await views.mount(context('addons'));
    assert.match(root.innerHTML,/Search game data\./);
    assert.doesNotMatch(root.innerHTML,/## What it does|Enter a character\./);
    const details={dataset:{action:'details',id:item.id},closest:()=>details};
    await listeners.get('click')[0]({target:details});
    const markup=nodes.get('ah-details-content').innerHTML;
    assert.match(markup,/<h3>What it does<\/h3>/);
    assert.match(markup,/<h3>How to use<\/h3><ol><li>Enter a character\.<\/li>/);
    assert.match(markup,/<h3>Shortcuts<\/h3><ul><li>Ctrl\+U: toggle\.<\/li>/);
  }finally{item.description=previous;nodes.get('ah-details-dialog').close();}
});

test('unverified compatibility explains versions and leaves reviewed installation available',async()=>{
  const previous=state.installation;
  item.compatibility_status='unverified';item.compatibility={client_versions:['2.0.112']};
  item.warnings=['Compatibility unverified for client <2.0.113>. Publisher lists 2.0.112.'];
  state.installation={kind:'sandbox',writable:true,client_version:'2.0.113',server_version:'2.2.109'};
  const ctx=context('addons'),original=ctx.api;
  ctx.api=async(path,body)=>path.endsWith('/plan')?{plan:{id:'unverified-plan',action:'install',addon_id:item.id,can_apply:true,changes:[],warnings:item.warnings,conflicts:[]}}:original(path,body);
  try{
    await views.mount(ctx);
    assert.match(root.innerHTML,/Compatibility unverified/);
    assert.doesNotMatch(root.innerHTML,/>Incompatible</);
    const details={dataset:{action:'details',id:item.id},closest:()=>details};
    await listeners.get('click')[0]({target:details});
    const markup=nodes.get('ah-details-content').innerHTML;
    assert.match(markup,/does not mean the add-on is incompatible/);
    assert.match(markup,/Current client version/);
    assert.match(markup,/2\.0\.113/);
    assert.match(markup,/Publisher lists client versions/);
    assert.match(markup,/2\.0\.112/);
    assert.match(markup,/&lt;2\.0\.113&gt;/);
    assert.match(markup,/data-operation="install" data-mutation data-blocked="false"/);
    const review={dataset:{action:'plan',id:item.id,operation:'install'},closest:()=>review};
    await listeners.get('click')[0]({target:review});
    assert.match(nodes.get('ah-plan-content').innerHTML,/data-action="apply" data-mutation data-blocked="false"/);
  }finally{
    state.installation=previous;delete item.compatibility_status;delete item.compatibility;delete item.warnings;
    nodes.get('ah-plan-dialog').close();
  }
});

test('installed compatibility stays separate from enabled state',async()=>{
  state.installed=[{id:'unverified.installed',name:'Unverified example',version:'1.0.0',enabled:true,compatibility_status:'unverified',settings:{}}];
  try{
    await views.mount(context('installed'));
    assert.match(root.innerHTML,/<th>Compatibility<\/th>/);
    assert.match(root.innerHTML,/Compatibility unverified/);
    assert.match(root.innerHTML,/aria-checked="true"/);
    assert.match(root.innerHTML,/data-operation="disable" data-mutation data-blocked="false"/);
    assert.match(root.innerHTML,/data-operation="remove" data-mutation data-blocked="false"/);
  }finally{state.installed=[];}
});

test('playable copies have an accurate writable target label and creation control',async()=>{
  const previous=state.installation;
  try{
    state.installation={kind:'test-client',writable:true,path:'owned-copy',name:'Playable add-on test copy'};
    await views.mount(context('addonsettings'));
    assert.match(root.innerHTML,/Playable test copy/);
    assert.match(root.innerHTML,/Create playable test copy/);
    assert.doesNotMatch(root.innerHTML,/Your game installation is connected for inspection/);
  }finally{state.installation=previous;}
});

test('normal client is writable and extra copies are optional advanced tools',async()=>{
  const previous=state.installation;
  try{
    state.installation={kind:'installation',writable:true,path:'client',name:'Normal game'};
    await views.mount(context('addonsettings'));
    assert.match(root.innerHTML,/Normal game client/);
    assert.match(root.innerHTML,/Use the normal game client you already launch/);
    assert.match(root.innerHTML,/Close this game client before applying/);
    assert.match(root.innerHTML,/<details[^>]*><summary>Advanced testing tools<\/summary>[\s\S]*Create playable test copy/);
    assert.doesNotMatch(root.innerHTML,/Game client · Read only|connected for inspection/);
  }finally{state.installation=previous;}
});

test('updated game exposes an explicit review before reapplying installed addons',async()=>{
  const previous=state.installation;
  state.installation={kind:'installation',writable:true,path:'client'};
  state.installed=[{id:item.id,version:'1.0.0',enabled:true}];
  state.game_update={detected:true,reapply_available:true,message:'Current game files take priority.'};
  const ctx=context('addons'),original=ctx.api;
  let reviewed;
  ctx.api=async(path,body)=>{
    if(path.endsWith('/plan')){reviewed=body;return {plan:{id:'reapply-plan',action:'reapply',addon_id:item.id,can_apply:true,changes:[],warnings:[],conflicts:[]}};}
    return original(path,body);
  };
  try{
    await views.mount(ctx);
    assert.match(root.innerHTML,/The game client changed/);
    assert.match(root.innerHTML,/Review reinstall/);
    const button={dataset:{action:'reapply'},closest:()=>button};
    await listeners.get('click')[0]({target:button});
    assert.deepEqual(reviewed,{addon_id:item.id,action:'reapply'});
    assert.match(nodes.get('ah-plan-content').innerHTML,/data-action="apply"/);
    assert.ok(!requests.some(path=>path.endsWith('/apply')));
  }finally{state.installation=previous;state.installed=[];delete state.game_update;nodes.get('ah-plan-dialog').close();}
});
test('open installed view automatically detects deleted files and offers reviewed reinstall without applying',async()=>{
  const previous=structuredClone(state);
  state.installed=[{...item,enabled:true,integrity:{status:'healthy'}}];
  state.integrity={status:'healthy',repair_available:false};
  const ctx=context('installed'),original=ctx.api;
  let reviewed;
  ctx.api=async(path,body)=>{
    if(path.endsWith('/state')){requests.push(path);return {state:structuredClone(state)};}
    if(path.endsWith('/plan')){reviewed=body;return {plan:{id:'repair-plan',action:'repair',addon_id:item.id,can_apply:true,changes:[],warnings:[],conflicts:[]}};}
    return original(path,body);
  };
  const tick=async()=>{const [id,callback]=[...integrityTimers].at(-1);integrityTimers.delete(id);await callback();};
  try{
    await views.mount(ctx);
    assert.doesNotMatch(root.innerHTML,/Needs reinstall/);
    state.installed[0].integrity={status:'missing'};
    state.integrity={status:'missing',repair_available:true,repair_action:'repair',message:'Missing <payload>',missing_files:['m2hub_addons/<payload>.py']};
    requests=[];await tick();
    assert.deepEqual(requests,['/api/addons/state']);
    assert.match(root.innerHTML,/Needs reinstall/);
    assert.match(root.innerHTML,/Missing &lt;payload&gt;/);
    assert.match(root.innerHTML,/m2hub_addons\/&lt;payload&gt;\.py/);
    assert.match(root.innerHTML,/data-action="repair"/);
    assert.match(root.innerHTML,/aria-checked="true"/);
    const button={dataset:{action:'repair',id:item.id},closest:()=>button};
    await listeners.get('click')[0]({target:button});
    assert.deepEqual(reviewed,{addon_id:item.id,action:'repair'});
    assert.ok(!requests.some(path=>path.endsWith('/apply')));
    nodes.get('ah-plan-dialog').close();
    state.integrity={status:'healthy',repair_available:false};state.installed[0].integrity={status:'healthy'};
    await tick();
    assert.doesNotMatch(root.innerHTML,/Needs reinstall|Add-ons need reinstalling/);
  }finally{for(const key of Object.keys(state))delete state[key];Object.assign(state,previous);}
});

test('returning to Studio rechecks files and failed checks cannot leave a healthy status',async()=>{
  const previous=structuredClone(state);
  state.installed=[{...item,enabled:true,integrity:{status:'healthy'}}];
  state.integrity={status:'healthy'};
  const ctx=context('installed'),original=ctx.api;let fail=false;
  ctx.api=async(path,body)=>{
    if(path.endsWith('/state')){if(fail)throw Error('offline');return {state:structuredClone(state)};}
    return original(path,body);
  };
  try{
    await views.mount(ctx);fail=true;
    await listeners.get('window:focus')[0]();
    assert.match(root.innerHTML,/Cannot verify files/);
    fail=false;await listeners.get('visibilitychange')[0]();
    assert.doesNotMatch(root.innerHTML,/Cannot verify files/);
    current=false;
    const [id,callback]=[...integrityTimers].at(-1);integrityTimers.delete(id);
    requests=[];await callback();
    assert.equal(integrityTimers.size,0);
    assert.deepEqual(requests,[]);
  }finally{current=true;for(const key of Object.keys(state))delete state[key];Object.assign(state,previous);}
});

test('review all combines local installs into one preview and one explicit apply',async()=>{
  const extra={...item,id:'community.second',name:'Second package'},invalid={...item,id:'broken.package',error:'Invalid checksum'};
  const ctx=context('addons'),original=ctx.api,operations=[];
  ctx.api=async(path,body)=>{
    if(path.endsWith('/catalog'))return {catalog:{items:[item,extra,invalid]}};
    if(path.endsWith('/plan/batch')){operations.push({path,body});return {plan:{id:'batch-plan',action:'batch',addon_id:item.id,batch:[{name:item.name,action:'install',version:'1.0'},{name:extra.name,action:'update',version:'2.0',enabled:false}],can_apply:true,changes:[],warnings:[],conflicts:[]}};}
    if(path.endsWith('/apply')){operations.push({path,body});return {ok:true,status:'success'};}
    return original(path,body);
  };
  try{
    await views.mount(ctx);
    assert.match(root.innerHTML,/Review all \(2\)/);
    const review={dataset:{action:'batch-all'},closest:()=>review};
    await listeners.get('click')[0]({target:review});
    assert.deepEqual(operations,[{path:'/api/addons/plan/batch',body:{addon_ids:[item.id,extra.id]}}]);
    assert.match(nodes.get('ah-plan-content').innerHTML,/2 add-ons in one installation/);
    assert.match(nodes.get('ah-plan-content').innerHTML,/stays disabled/);
    assert.match(nodes.get('ah-plan-content').innerHTML,/Example &lt;unsafe&gt;/);
    const apply={dataset:{action:'apply'},closest:()=>apply};
    await listeners.get('click')[0]({target:apply});
    assert.equal(operations.filter(item=>item.path.endsWith('/apply')).length,1);
    assert.equal(operations[1].body.plan_id,'batch-plan');
  }finally{nodes.get('ah-plan-dialog').close();}
});

test('selected batch review excludes unselected packages',async()=>{
  const extra={...item,id:'selected.second',name:'Selected package'};
  const ctx=context('addons'),original=ctx.api;let reviewed;
  ctx.api=async(path,body)=>{
    if(path.endsWith('/catalog'))return {catalog:{items:[item,extra]}};
    if(path.endsWith('/plan/batch')){reviewed=body;return {plan:{id:'selected-batch',action:'batch',can_apply:true,batch:[],changes:[],warnings:[],conflicts:[]}};}
    return original(path,body);
  };
  const input={dataset:{batchId:extra.id},checked:true,classList:{contains:()=>false},closest:()=>root};
  try{
    await views.mount(ctx);
    await listeners.get('change')[0]({target:input});
    assert.match(root.innerHTML,/Review selected \(1\)/);
    const button={dataset:{action:'batch-selected'},closest:()=>button};
    await listeners.get('click')[0]({target:button});
    assert.deepEqual(reviewed,{addon_ids:[extra.id]});
  }finally{input.checked=false;await listeners.get('change')[0]({target:input});nodes.get('ah-plan-dialog').close();}
});

test('opening the client after the batch is an explicit option on the one apply request',async()=>{
  const previous=state.installation;
  state.installation={kind:'installation',writable:true};
  const ctx=context('addons'),original=ctx.api;let applied;
  ctx.api=async(path,body)=>{
    if(path.endsWith('/plan/batch'))return {plan:{id:'batch-open',action:'batch',batch:[],can_apply:true,changes:[],warnings:[],conflicts:[]}};
    if(path.endsWith('/apply')){applied=body;return {ok:true,status:'success',client_launch:{status:'launched'}};}
    return original(path,body);
  };
  try{
    await views.mount(ctx);
    const review={dataset:{action:'batch-all'},closest:()=>review};
    await listeners.get('click')[0]({target:review});
    const markup=nodes.get('ah-plan-content').innerHTML;
    assert.match(markup,/Open the game client once after all changes succeed/);
    assert.doesNotMatch(markup,/id="ah-launch-client" checked/);
    const checkbox=new Element();checkbox.id='ah-launch-client';checkbox.checked=true;
    const apply={dataset:{action:'apply'},closest:()=>apply};
    await listeners.get('click')[0]({target:apply});
    assert.deepEqual(applied,{plan_id:'batch-open',launch_client:true});
  }finally{state.installation=previous;nodes.delete('ah-launch-client');nodes.get('ah-plan-dialog').close();}
});

test('batch update review includes only packages already ready to install',async()=>{
  const ctx=context('installed'),original=ctx.api;let reviewed;
  ctx.api=async(path,body)=>{
    if(path.endsWith('/updates'))return {updates:[{id:'ready.one',download_ready:true},{id:'remote.only',download_ready:false}]};
    if(path.endsWith('/plan/batch')){reviewed=body;return {plan:{id:'updates-batch',action:'batch',can_apply:true,batch:[],changes:[],warnings:[],conflicts:[]}};}
    return original(path,body);
  };
  try{
    await views.mount(ctx);
    const button={dataset:{action:'batch-updates'},closest:()=>button};
    await listeners.get('click')[0]({target:button});
    assert.deepEqual(reviewed,{addon_ids:['ready.one']});
  }finally{nodes.get('ah-plan-dialog').close();}
});

test('atlas uses namespaced images and links the resolved mob to Studio editors',async()=>{
  await views.mount(context('atlas'));
  assert.match(root.innerHTML,/href="\/api\/addons\/map-image\?map=64"/);
  assert.match(root.innerHTML,/data-action="open-drops" data-id="691"/);
  assert.match(root.innerHTML,/data-action="open-map-source" data-path="map\/boss.txt"/);
  const button={dataset:{action:'open-drops',id:'691'},closest:()=>button};
  await listeners.get('click')[0]({target:button});
  assert.equal(opened,'691');
});
test('repository view exposes source controls and discovery separates download from install',async()=>{
  await views.mount(context('repositories'));
  assert.match(root.innerHTML,/Creator &lt;unsafe&gt;/);
  assert.match(root.innerHTML,/Check for updates/);
  assert.doesNotMatch(root.innerHTML,/Publisher unverified|verification badge|Verified publisher/);
  await views.mount(context('addons'));
  assert.match(root.innerHTML,/Extra release/);
  assert.match(root.innerHTML,/Review download/);
  assert.match(root.innerHTML,/Downloading does not install it/);
});
test('local file import uses the shared host and opens installation details without applying',async()=>{
  const ctx=context('addons'),original=ctx.api;
  const local={id:'creator.local',name:'Imported package',version:'1.0.0',author:'Creator',
    distribution:{kind:'local',filename:'Creator <local>.zip',sha256:'a'.repeat(64)}};
  let selected,imported=false;
  ctx.importPackage=async file=>{selected=file;imported=true;return {ok:true,imported:local.id};};
  ctx.api=path=>path.endsWith('/catalog')&&imported?{ok:true,catalog:{items:[item,local]}}:original(path);
  await views.mount(ctx);
  assert.match(root.innerHTML,/data-action="choose-package"/);
  const file={name:'creator.m2addon.zip',size:2048};
  const input={id:'ah-package-file',files:[file],closest:()=>root};
  await listeners.get('change')[0]({target:input});
  assert.equal(selected,file);
  assert.match(nodes.get('ah-details-content').innerHTML,/Local file: Creator &lt;local&gt;.zip/);
  assert.match(nodes.get('ah-details-content').innerHTML,/Review install/);
  assert.equal(requests.some(path=>path.endsWith('/apply')),false);
});
test('oversized local files are refused before uploading',async()=>{
  const ctx=context('addons');let uploaded=false;
  ctx.importPackage=async()=>{uploaded=true;};
  await views.mount(ctx);
  await listeners.get('change')[0]({target:{id:'ah-package-file',files:[{size:66*1024*1024+1}],closest:()=>root}});
  assert.equal(uploaded,false);
});
test('an installed package retains its details and removal after its repository disappears',async()=>{
  state.installed=[{id:'removed.source',name:'Retained package',version:'1.0.0',enabled:true,settings:{}}];
  try{
    await views.mount(context('installed'));
    assert.match(root.innerHTML,/data-action="details" data-id="removed.source"/);
    const button={dataset:{action:'details',id:'removed.source'},closest:()=>button};
    await listeners.get('click')[0]({target:button});
    assert.match(nodes.get('ah-details-content').innerHTML,/Retained package/);
    assert.match(nodes.get('ah-details-content').innerHTML,/Review removal/);
  }finally{state.installed=[];}
});
test('installed settings remain editable after the catalog selection is removed',async()=>{
  state.installed=[{id:'removed.settings',name:'Retained settings',version:'1.0.0',enabled:true,
    settings:{labels:true},settings_schema:{type:'object',properties:{labels:{type:'boolean'}}}}];
  const ctx=context('installed'),original=ctx.api;let submitted;
  ctx.api=async(path,body)=>{
    if(path.endsWith('/plan')){submitted=body;return {plan:{id:'settings-plan',addon_id:'removed.settings',action:'configure',can_apply:true,changes:[]}};}
    return original(path);
  };
  try{
    await views.mount(ctx);
    const form={id:'addon-settings-form',dataset:{id:'removed.settings'},closest:()=>root,elements:{namedItem:()=>({checked:false})}};
    await listeners.get('submit')[0]({target:form,preventDefault(){}});
    assert.deepEqual(submitted,{addon_id:'removed.settings',action:'configure',settings:{labels:false}});
  }finally{state.installed=[];nodes.get('ah-plan-dialog').close();}
});
test('a delayed download review cannot open over a different Studio page',async()=>{
  const ctx=context('addons'),original=ctx.api;
  let finish;
  ctx.api=path=>path.endsWith('/jobs/start')?new Promise(resolve=>{finish=resolve;}):original(path);
  await views.mount(ctx);
  nodes.get('ah-download-dialog').close();
  const card={dataset:{repository:'repo',addon:'creator.extra'},querySelector:()=>({value:'1.0.0'})};
  const button={dataset:{action:'review-download'},closest:selector=>selector==='.remote-release-card'?card:button};
  const pending=listeners.get('click')[0]({target:button});
  current=false;
  try{finish({job:{id:'late-review',status:'queued',operation:'releases/review'}});await pending;assert.equal(nodes.get('ah-download-dialog').open,false);}
  finally{current=true;}
});
test('settings distinguish private diagnostics from the support report export',async()=>{
  await views.mount(context('addonsettings'));
  assert.match(root.innerHTML,/data-action="support-report"/);
  assert.match(root.innerHTML,/omits paths, tokens, settings, repository URLs and game content/);
});
test('module ignores controls belonging to the surrounding Studio',async()=>{
  opened=null;
  await listeners.get('click')[0]({target:{closest:()=>null}});
  assert.equal(opened,null);
});
test('a completed request cannot overwrite a different Studio page',async()=>{
  root.innerHTML='Server editor';current=false;
  await views.mount(context('addons'));
  assert.equal(root.innerHTML,'Server editor');
  current=true;
});

test('GitHub sources expose the development channel and branch identity',async()=>{
  const ctx=context('repositories'),original=ctx.api;
  ctx.api=path=>path.endsWith('/repositories')?{repositories:[{id:'github',kind:'github',name:'GitHub fixture',url:'https://github.com/creator/addon',publisher:'Creator',default_branch:'main<unsafe>',channel:'development',enabled:true,package_count:1}]}:original(path);
  await views.mount(ctx);
  assert.match(root.innerHTML,/GitHub repository or catalog URL/);
  assert.match(root.innerHTML,/value="development" selected/);
  assert.match(root.innerHTML,/default branch main&lt;unsafe&gt;/);
});

test('GitHub download review escapes README content and shows the exact commit before packaging',async()=>{
  const ctx=context('addons'),original=ctx.api;
  const review={id:'github-review',source_kind:'github',kind:'development',name:'GitHub fixture',version:'1.0.0',source_ref:'main',commit:'a'.repeat(40),manifest_digest:'b'.repeat(64),repository_url:'https://github.com/creator/addon',publisher:'Creator',sha256:null,bytes:null,readme:'# Usage\n<script>bad()</script>',notice:'Choose sources you trust.'};
  ctx.api=path=>path.endsWith('/jobs/start')?{job:{id:'github-review-job',status:'queued',operation:'releases/review'}}:path.includes('/job?id=')?{job:{id:'github-review-job',status:'succeeded',operation:'releases/review',result:{review}}}:original(path);
  await views.mount(ctx);
  const card={dataset:{repository:'github',addon:'creator.extra'},querySelector:()=>({value:'development'})};
  const button={dataset:{action:'review-download'},closest:selector=>selector==='.remote-release-card'?card:button};
  await listeners.get('click')[0]({target:button});
  await new Promise(setImmediate);
  const html=nodes.get('ah-download-content').innerHTML;
  assert.match(html,/Pinned commit/);
  assert.match(html,/a{40}/);
  assert.match(html,/Development · main/);
  assert.match(html,/Computed after source validation/);
  assert.match(html,/&lt;script&gt;bad\(\)&lt;\/script&gt;/);
  assert.doesNotMatch(html,/<script>|null bytes|>null</);
  nodes.get('ah-download-dialog').close();state.network_job=null;views.unmount();
});

test('development offers use branch labels and no-release guidance stays actionable',async()=>{
  const ctx=context('addons'),original=ctx.api;
  let releases=[];
  ctx.api=path=>path.endsWith('/releases')?{releases:[{id:'github.fixture',name:'Development fixture',source_kind:'github',default_branch:'main',releases,latest:releases[0]}]}:original(path);
  await views.mount(ctx);
  assert.match(root.innerHTML,/Choose Development in Repositories/);
  releases=[{version:'development',kind:'development',source_ref:'main'}];
  await views.mount(ctx);
  assert.match(root.innerHTML,/>Development · main</);
});

test('installed GitHub revision is retained when a newer package is selected',async()=>{
  const ctx=context('installed'),original=ctx.api;
  const selected={id:'github.fixture',name:'Revision fixture',version:'1.1.0',distribution:{kind:'github',repository_url:'https://github.com/creator/addon',commit:'b'.repeat(40),source_ref:'v1.1.0'}};
  state.installed=[{...selected,version:'1.0.0',distribution:{...selected.distribution,commit:'a'.repeat(40),source_ref:'v1.0.0'}}];
  ctx.api=path=>path.endsWith('/catalog')?{catalog:{items:[selected]}}:original(path);
  try{
    await views.mount(ctx);
    assert.match(root.innerHTML,/a{12}/);
    assert.doesNotMatch(root.innerHTML,/b{12}/);
    const button={dataset:{action:'details',id:'github.fixture'},closest:()=>button};
    await listeners.get('click')[0]({target:button});
    const html=nodes.get('ah-details-content').innerHTML;
    assert.match(html,/Installed commit/);
    assert.match(html,/a{40}/);
    assert.match(html,/b{40}/);
  }finally{state.installed=[];nodes.get('ah-details-dialog').close();}
});

test('an active job reconnects after navigation and exposes cancellation without blocking navigation links',async()=>{
  state.network_job={id:'resume-job',operation:'repositories/refresh',status:'running',message:'Reading repository metadata',progress:{received_bytes:1024,total_bytes:null}};
  const ctx=context('repositories'),original=ctx.api;let complete,cancelled=false;
  ctx.api=async(path,body)=>{
    if(path.includes('/job?id='))return new Promise(resolve=>{complete=resolve;});
    if(path.endsWith('/jobs/cancel')){cancelled=body.job_id==='resume-job';return {job:{...state.network_job,cancel_requested:true}};}
    return original(path);
  };
  try{
    await views.mount(ctx);
    assert.match(root.innerHTML,/Reading repository metadata/);
    assert.match(root.innerHTML,/1.0 KiB received/);
    assert.match(root.innerHTML,/data-action="cancel-network-job"/);
    assert.match(root.innerHTML,/href="#addonsettings"/);
    assert.match(root.innerHTML,/data-action="repository-refresh"[^>]*disabled/);
    const button={dataset:{action:'cancel-network-job',job:'resume-job'},closest:()=>button};
    await listeners.get('click')[0]({target:button});assert.equal(cancelled,true);
  }finally{
    views.unmount();state.network_job=null;complete({job:{status:'cancelled'}});await new Promise(setImmediate);
  }
});

test('interrupted job errors are escaped and completed work does not replay automatically',async()=>{
  state.network_job={id:'interrupted',operation:'releases/download',status:'interrupted',error:'Stopped <unsafe>',result_available:false};
  try{
    await views.mount(context('addons'));
    assert.match(root.innerHTML,/Stopped &lt;unsafe&gt;/);
    assert.doesNotMatch(root.innerHTML,/data-action="cancel-network-job"/);
    assert.doesNotMatch(root.innerHTML,/data-action="network-job-result"/);
  }finally{state.network_job=null;views.unmount();}
});

const updateFixture={id:'community.example',name:'Example <unsafe>',kind:'repository',installed_version:'1.0.0',available_version:'1.2.0',selection:'1.2.0',repository_id:'repo',repository_name:'Creator catalog',repository_url:'https://example.test/catalog.json',download_ready:false,can_download:true,checked_at:'2026-10-18T12:00:00Z',changes:[{version:'1.2.0',release_notes:'New labels\n<script>bad()</script>'},{version:'1.1.0',release_notes:'Earlier changes'}]};

test('installed update notices expose a cached changelog without any mutation or remote check',async()=>{
  const ctx=context('installed'),original=ctx.api;
  state.installed=[{...item,version:'1.0.0',enabled:true}];
  ctx.api=path=>path.endsWith('/updates')?{policy:'manual',updates:[updateFixture]}:original(path);
  try{
    await views.mount(ctx);
    assert.match(root.innerHTML,/1 update available/);
    assert.match(root.innerHTML,/Updates are manual/);
    assert.match(root.innerHTML,/Read changelog/);
    const count=requests.length;
    const button={dataset:{action:'update-details',id:item.id},closest:()=>button};
    await listeners.get('click')[0]({target:button});
    assert.equal(requests.length,count);
    const html=nodes.get('ah-update-content').innerHTML;
    assert.match(html,/1.0.0 → 1.2.0/);
    assert.match(html,/Earlier changes/);
    assert.match(html,/&lt;script&gt;bad\(\)&lt;\/script&gt;/);
    assert.doesNotMatch(html,/<script>/);
    assert.match(html,/data-action="review-update-download"/);
    const close={dataset:{action:'close-update'},closest:()=>close};
    await listeners.get('click')[0]({target:close});
    assert.equal(nodes.get('ah-update-dialog').open,false);
    assert.equal(requests.length,count);
  }finally{state.installed=[];views.unmount();}
});

test('manual check only submits metadata work and never downloads or applies an update',async()=>{
  const ctx=context('installed'),original=ctx.api,mutations=[];
  ctx.api=async(path,body)=>{
    if(body!==undefined)mutations.push({path,body});
    if(path.endsWith('/jobs/start'))return {job:{id:'check-all',operation:'repositories/check-updates',status:'queued'}};
    if(path.includes('/job?id='))return {job:{id:'check-all',operation:'repositories/check-updates',status:'succeeded',result:{checked_repositories:[{repository_id:'repo',status:'succeeded'}],check_errors:0}}};
    return original(path);
  };
  try{
    await views.mount(ctx);
    assert.deepEqual(mutations,[]);
    const button={dataset:{action:'check-addon-updates'},closest:()=>button};
    await listeners.get('click')[0]({target:button});
    await new Promise(setImmediate);
    assert.deepEqual(mutations,[{path:'/api/addons/jobs/start',body:{operation:'repositories/check-updates',data:{}}}]);
  }finally{state.network_job=null;views.unmount();}
});

test('a selected update still requires installation review and can be postponed',async()=>{
  const ctx=context('installed'),original=ctx.api;let mutations=0;
  state.installed=[{...item,version:'1.0.0',enabled:true}];
  ctx.api=(path,body)=>{
    if(body!==undefined)mutations++;
    if(path.endsWith('/updates'))return {updates:[{...updateFixture,download_ready:true}]};
    return original(path);
  };
  try{
    await views.mount(ctx);
    const button={dataset:{action:'update-details',id:item.id},closest:()=>button};
    await listeners.get('click')[0]({target:button});
    const html=nodes.get('ah-update-content').innerHTML;
    assert.match(html,/data-action="plan" data-operation="update"/);
    assert.match(html,/Review installation changes/);
    assert.doesNotMatch(html,/data-action="review-update-download"/);
    assert.equal(mutations,0);
  }finally{state.installed=[];nodes.get('ah-update-dialog').close();views.unmount();}
});

test('a failed source check keeps the changelog readable and disables an uncached download',async()=>{
  const ctx=context('installed'),original=ctx.api;
  ctx.api=path=>path.endsWith('/updates')?{updates:[{...updateFixture,check_error:'Offline <unsafe>',can_download:false}]}:original(path);
  try{
    await views.mount(ctx);
    const button={dataset:{action:'update-details',id:item.id},closest:()=>button};
    await listeners.get('click')[0]({target:button});
    const html=nodes.get('ah-update-content').innerHTML;
    assert.match(html,/Last known update/);
    assert.match(html,/Offline &lt;unsafe&gt;/);
    assert.match(html,/Earlier changes/);
    assert.match(html,/data-action="review-update-download"[^>]*disabled/);
  }finally{nodes.get('ah-update-dialog').close();views.unmount();}
});

test('a collection source exposes separate add-on cards without an install-all action',async()=>{
  const ctx=context('repositories'),original=ctx.api;
  ctx.api=path=>path.endsWith('/repositories')?{repositories:[{id:'collection',kind:'github',layout:'collection',name:'Collection <unsafe>',url:'https://github.com/creator/collection',publisher:'Creator',enabled:true,channel:'stable',default_branch:'main',package_count:2}]}:path.endsWith('/releases')?{releases:[
    {id:'creator.atlas',name:'Atlas member',collection:true,package_path:'addons/atlas',source_kind:'github',repository_id:'collection',repository_name:'Collection',publisher:'Creator',releases:[{version:'1.0.0'}],latest:{version:'1.0.0'}},
    {id:'creator.legend',name:'Legend member',collection:true,package_path:'addons/legend',source_kind:'github',repository_id:'collection',repository_name:'Collection',publisher:'Creator',releases:[{version:'2.0.0'}],latest:{version:'2.0.0'}}]}:original(path);
  await views.mount(ctx);
  assert.match(root.innerHTML,/GitHub collection/);
  assert.match(root.innerHTML,/2 packages/);
  await views.mount({...ctx,page:'addons'});
  assert.match(root.innerHTML,/Atlas member/);
  assert.match(root.innerHTML,/Legend member/);
  assert.match(root.innerHTML,/addons\/atlas/);
  assert.match(root.innerHTML,/addons\/legend/);
  assert.equal((root.innerHTML.match(/data-action="review-download"/g)??[]).length,2);
  assert.doesNotMatch(root.innerHTML,/Install all|Enable all/);
});

test('collection download review identifies the selected folder and leaves siblings unselected',async()=>{
  const ctx=context('addons'),original=ctx.api;
  const review={id:'collection-review',source_kind:'github',collection:true,package_path:'addons/atlas',name:'Atlas member',addon_id:'creator.atlas',version:'1.0.0',source_ref:'creator.atlas/v1.0.0',commit:'a'.repeat(40),manifest_digest:'b'.repeat(64),repository_url:'https://github.com/creator/collection',publisher:'Creator',readme:'Original member documentation'};
  ctx.api=path=>path.endsWith('/jobs/start')?{job:{id:'collection-job',status:'queued',operation:'releases/review'}}:path.includes('/job?id=')?{job:{id:'collection-job',status:'succeeded',operation:'releases/review',result_available:true,result:{review}}}:original(path);
  try{
    await views.mount(ctx);
    const card={dataset:{repository:'collection',addon:'creator.atlas'},querySelector:()=>({value:'1.0.0'})};
    const button={dataset:{action:'review-download'},closest:selector=>selector==='.remote-release-card'?card:button};
    await listeners.get('click')[0]({target:button});
    await new Promise(setImmediate);
    const html=nodes.get('ah-download-content').innerHTML;
    assert.match(html,/addons\/atlas/);
    assert.match(html,/Only this add-on is downloaded/);
    assert.match(html,/other collection members stay unselected/);
    assert.match(html,/creator.atlas\/v1.0.0/);
  }finally{state.network_job=null;nodes.get('ah-download-dialog').close();views.unmount();}
});
