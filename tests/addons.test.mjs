import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {escapeHtml,descriptionSummary,descriptionMarkup,unwrap,filterCatalog,installedRecord,addonStatus,compatibilityStatus,formatTime,changeRows,mapRegions,mapBounds,respawnLabel,sourceLabel,booleanSettings,settingFields,parseSettingValue} from '../web/addon_helpers.mjs';

test('sectioned descriptions show headings and lists while cards keep a short summary',()=>{
  const description='## What it does\n\nFind useful items.\n\n## How to use\n\n1. Open the game.\n2. Click the button.\n\n## Shortcuts\n\n- Ctrl+U: toggle.';
  assert.equal(descriptionSummary(description),'Find useful items.');
  const markup=descriptionMarkup(description);
  assert.match(markup,/<section class="addon-description-section"><h3>How to use<\/h3><ol><li>Open the game\.<\/li><li>Click the button\.<\/li><\/ol><\/section>/);
  assert.match(markup,/<h3>Shortcuts<\/h3><ul><li>Ctrl\+U: toggle\.<\/li><\/ul>/);
  assert.equal((markup.match(/<section /g)??[]).length,(markup.match(/<\/section>/g)??[]).length);
});

test('description formatting escapes every author-controlled heading and list item',()=>{
  const markup=descriptionMarkup('## <script>run()</script>\n\n1. <img src=x onerror=run()>\n\n- <svg onload=run()>\n\nPlain <iframe> text.');
  assert.doesNotMatch(markup,/<script>|<img|<svg|<iframe/);
  assert.match(markup,/&lt;script&gt;/);
  assert.match(markup,/&lt;img/);
  assert.match(markup,/&lt;svg/);
  assert.match(markup,/&lt;iframe&gt;/);
  assert.match(descriptionMarkup('Plain description.'),/<p class="detail-description">Plain description\.<\/p>/);
});

test('settings keep the installed schema when a newer catalog release changes it',()=>{
  const catalog={settings_schema:{properties:{new_field:{type:'boolean',default:true}}}};
  const installed={settings_schema:{properties:{count:{type:'integer',default:3}}},settings:{count:0}};
  assert.deepEqual(settingFields(catalog,installed).map(field=>[field.key,field.value]),[['count',0]]);
});
test('typed settings preserve numbers, enums and JSON structures',()=>{
  assert.equal(parseSettingValue('12',{type:'integer'}),12);
  assert.equal(parseSettingValue('1.25',{type:'number'}),1.25);
  assert.equal(parseSettingValue('"copper"',{type:'string',enum:['copper','green']}),'copper');
  assert.deepEqual(parseSettingValue('[1,2]',{type:'array'}),[1,2]);
  assert.deepEqual(parseSettingValue('{"a":true}',{type:'object'}),{a:true});
  for(const [value,spec] of [['',{type:'integer'}],['1.5',{type:'integer'}],['Infinity',{type:'number'}],['wrong',{enum:['copper']}],['[]',{type:'object'}]])assert.throws(()=>parseSettingValue(value,spec));
});

test('catalog search matches every term across metadata and respects category',()=>{
  const items=[{id:'hub.boss-map',name:'Boss atlas',description:'Configured spawn regions',author:'Hub',category:'maps'},{id:'hub.legend',name:'Map legend',description:'Small coordinate display',category:'interface'}];
  assert.deepEqual(filterCatalog(items,' BOSS   configured ','maps'),[items[0]]);
  assert.deepEqual(filterCatalog(items,'map','interface'),[items[1]]);
  assert.deepEqual(filterCatalog(items,'spawn coordinates'),[]);
});

test('remote strings are escaped before interpolating into markup',()=>{
  assert.equal(escapeHtml('<img src=x onerror="run()"> & \'text\''),'&lt;img src=x onerror=&quot;run()&quot;&gt; &amp; &#39;text&#39;');
  assert.equal(escapeHtml(null),'');
});

test('response envelopes preserve direct data and reject server errors',()=>{
  assert.deepEqual(unwrap({ok:true,state:{installed:[]}},'state'),{installed:[]});
  assert.equal(unwrap({ok:true,version:'1'},'state').version,'1');
  assert.throws(()=>unwrap({ok:false,error:'Baseline changed'},'plan'),/Baseline changed/);
});

test('installed state takes precedence over catalog flags and invalid packages stay visible',()=>{
  const item={id:'hub.map',installed:false};
  assert.equal(installedRecord(item,[{id:'hub.map',enabled:false}]).enabled,false);
  assert.deepEqual(addonStatus(item,[{id:'hub.map',enabled:false,integrity:{status:'healthy'}}]),{label:'Disabled',tone:'muted'});
  assert.equal(addonStatus({...item,error:'Checksum mismatch'},[]).label,'Package issue');
  assert.equal(addonStatus(item,[]).label,'Available');
  assert.equal(addonStatus({...item,status:'incompatible'},[]).label,'Available');
});

test('file integrity takes precedence over saved enabled preferences',()=>{
  const item={id:'hub.map',installed:true,enabled:true,integrity:{status:'healthy'}};
  for(const [status,label] of [['missing','Needs reinstall'],['changed','Files changed'],['unavailable','Cannot verify files'],['unverified','Files not checked']]){
    for(const enabled of [true,false])assert.equal(addonStatus(item,[{id:item.id,enabled,integrity:{status}}]).label,label);
  }
  assert.equal(addonStatus(item,[{id:item.id,enabled:true,integrity:{status:'healthy'}}]).label,'Enabled');
  assert.equal(addonStatus({id:item.id},[{id:item.id,enabled:true}]).label,'Files not checked');
});

test('the main Studio notice checks local files and clears after a successful reinstall',async()=>{
  const source=fs.readFileSync(new URL('../web/app.js',import.meta.url),'utf8');
  const notice={hidden:true,innerHTML:''},requests=[];
  let response={state:{integrity:{status:'missing',repair_available:true,message:'Missing <file>'}}},fail=false;
  const context={$:()=>notice,document:{hidden:false},esc:escapeHtml,api:async path=>{requests.push(path);if(fail)throw Error('offline');return response;}};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('let addonNoticeBusy='),source.indexOf('async function updateStatus(')),context);
  await context.refreshAddonNotice(true);
  assert.equal(notice.hidden,false);
  assert.match(notice.innerHTML,/Add-ons need reinstalling/);
  assert.match(notice.innerHTML,/Missing &lt;file&gt;/);
  assert.match(notice.innerHTML,/href="#installed">Review reinstall/);
  response={state:{integrity:{status:'healthy'}}};
  await context.refreshAddonNotice(true);
  assert.equal(notice.hidden,true);
  fail=true;await context.refreshAddonNotice(true);
  assert.equal(notice.hidden,false);
  assert.match(notice.innerHTML,/could not be checked/);
  assert.ok(requests.every(path=>path==='/api/addons/state'));
});

test('compatibility distinguishes uncertainty, publisher declarations and recorded incompatibility',()=>{
  assert.equal(compatibilityStatus({compatibility_status:'unverified'}).label,'Compatibility unverified');
  assert.equal(compatibilityStatus({compatibility_status:'experimental'}).label,'Compatibility unverified');
  assert.equal(compatibilityStatus({compatibility_status:'incompatible'}).label,'Compatibility unverified');
  assert.equal(compatibilityStatus({compatibility_status:'declared'}).label,'Declared compatible');
  assert.equal(compatibilityStatus({compatibility_status:'unknown'}).label,'Compatibility not checked');
  const known=compatibilityStatus({compatibility_status:'incompatible',incompatibility_reasons:['Required API is missing']});
  assert.equal(known.label,'Known incompatibility');
  assert.deepEqual(known.notes,['Required API is missing']);
});

test('change plans preserve actionable path, operation, and conflict detail',()=>{
  assert.deepEqual(changeRows([{target:'root.data',operation:'replace',description:'Rebuild pack'}]),[{path:'root.data',action:'Replace',detail:'Rebuild pack'}]);
  assert.deepEqual(changeRows(['m2hub_config.py']),[{path:'m2hub_config.py',action:'Change'}]);
});

test('spawn normalization preserves zero coordinates and does not fabricate missing ones',()=>{
  const regions=mapRegions({regions:[{name:'Tiger',x:0,y:'10',width:20,height:30},{vnum:1093,x:null,y:'invalid'}]});
  assert.equal(regions[0].x,0);assert.equal(regions[0].y,10);
  assert.equal(regions[1].x,undefined);assert.equal(regions[1].y,undefined);
  assert.equal(regions[1].name,'Boss 1093');
});

test('map display uses source extents when available and labels inferred bounds',()=>{
  assert.deepEqual(mapBounds({width:2560,height:5120},[]),{x:0,y:0,width:2560,height:5120,inferred:false});
  const bounds=mapBounds({},[{x:100,y:150,width:40,height:60}]);
  assert.deepEqual(bounds,{x:30,y:70,width:140,height:160,inferred:true});
});

test('fallback source dimensions do not masquerade as verified map bounds',()=>{
  const bounds=mapBounds({width:1024,height:1024,coverage:{bounds_verified:false}},[{x:20,y:30,width:10,height:10}]);
  assert.deepEqual(bounds,{x:0,y:0,width:1024,height:1024,inferred:true});
  assert.equal(mapBounds({width:1024,height:1024,coverage:{bounds_verified:true}},[]).inferred,false);
});

test('respawn and source labels disclose unknown values without live status claims',()=>{
  assert.equal(respawnLabel({}),'Interval not provided');
  assert.equal(respawnLabel({respawn:{min:48,max:52,unit:'minutes'}}),'48–52 minutes');
  assert.equal(respawnLabel({respawn_seconds:60}),'60 seconds');
  assert.equal(sourceLabel({path:'map/boss.txt'}),'map/boss.txt');
  assert.equal(formatTime(null),'Time not recorded');
});

test('boolean settings use saved false values before package defaults',()=>{
  const item={settings:{show_labels:true},settings_schema:{properties:{show_labels:{type:'boolean',default:true},count:{type:'integer'},show_areas:{type:'boolean',default:true}}}};
  assert.deepEqual(booleanSettings(item,{settings:{show_labels:false}}),[
    {key:'show_labels',label:'Show labels',description:'',value:false},
    {key:'show_areas',label:'Show areas',description:'',value:true}
  ]);
});

test('atlas species groups repeated zones and combines type and text filters',async()=>{
  const {atlasSpecies}=await import('../web/addon_helpers.mjs');
  const map={regions:[{mob_id:101,name:'Wolf',type:'monster',level:1,x:0,y:0},{mob_id:101,name:'Wolf',type:'monster',level:1,x:10,y:20},{mob_id:8001,name:'Metin of Sorrow',type:'metin',level:5,x:30,y:40}]};
  assert.equal(atlasSpecies(map).length,2);
  assert.equal(atlasSpecies(map,'monster','101')[0].zones.length,2);
  assert.equal(atlasSpecies(map,'metin','wolf').length,0);
  assert.equal(atlasSpecies(map,'metin','sorrow')[0].mob_id,'8001');
  assert.deepEqual(atlasSpecies(map,'all','missing'),[]);
});


test('atlas quick categories keep mining deposits separate from mobs and NPCs',async()=>{
  const {atlasSpecies}=await import('../web/addon_helpers.mjs');
  const map={regions:[['101','Wolf','monster'],['691','Chief Orc','boss'],['8001','Metin','metin'],['20047','Diamond vein','ore'],['9001','Shopkeeper','npc']].map(([mob_id,name,type])=>({mob_id,name,type,x:1,y:2}))};
  assert.equal(atlasSpecies(map,'all').length,5);
  assert.equal(atlasSpecies(map,'enemies').length,3);
  assert.equal(atlasSpecies(map,'ore')[0].mob_id,'20047');
  assert.equal(atlasSpecies(map,'npc')[0].mob_id,'9001');
  assert.equal(atlasSpecies(map,'ore','diamond').length,1);
  assert.equal(atlasSpecies(map,'monster','diamond').length,0);
});
