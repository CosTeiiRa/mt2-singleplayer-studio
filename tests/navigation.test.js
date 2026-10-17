'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const nav=require('../web/navigation.js');

test('deep links choose a valid topic and older root links open its menu',()=>{
  assert.deepEqual(nav.parse('#settings/drops'),{page:'settings',section:'drops',route:'settings/drops'});
  assert.deepEqual(nav.parse('settings'),{page:'settings',section:'menu',route:'settings'});
  assert.equal(nav.parse('files/all').section,'all');
  assert.equal(nav.parse('files/removed-topic').route,'files');
  assert.equal(nav.parse('quests').section,null);
});

test('existing categories partition into topics while future categories remain reachable',()=>{
  const categories=['Items','World','Drops','Crafting','Fishing','Spawns & maps','Events','Shops','Skills','Quests','Package quests','Custom quests','Build overrides','Future category'];
  const rows=categories.map((category,i)=>({id:'test/'+i,name:'File '+i,category}));
  const partition=nav.files.flatMap(section=>nav.matchingFiles(rows,section.id));
  assert.deepEqual([...partition].sort((a,b)=>a.id.localeCompare(b.id)),[...rows].sort((a,b)=>a.id.localeCompare(b.id)));
  assert.equal(new Set(partition).size,rows.length);
  assert.equal(nav.fileTopic(rows.at(-1)),'other');
});

test('specific build overrides appear with their gameplay topic',()=>{
  const cases=[['share-add/cube.seon_pyeong.txt','crafting'],['quest/libs/crafting/crafting_data.lua','crafting'],['special_item_group.moonlight.custom.txt','drops'],['share-add/mob_drop_item.m3.append.txt','drops'],['special_spawns.txt','maps'],['share/locale/poland/map/metin2_map_a1/regen.txt','maps'],['Dockerfile','other']];
  for(const [id,expected] of cases)assert.equal(nav.fileTopic({id,category:'Build overrides'}),expected,id);
});

test('all settings remain reachable and topic searches stay inside that topic',()=>{
  const rows=nav.settings.map((section,i)=>({key:'M2_KEY_'+i,label:'Common keyword '+i,group:section.group}));
  rows.push({key:'M2_NEW',label:'Future setting',group:'Future group'});
  assert.equal(nav.settings.flatMap(s=>nav.matchingSettings(rows,s.id)).length,rows.length);
  assert.deepEqual(nav.matchingSettings(rows,'drops','  KEYWORD '),[rows[2]]);
  assert.equal(nav.matchingSettings(rows,'all','m2_new').length,1);
});

test('map, source and search filters combine without hiding shared files from All',()=>{
  const rows=[
    {id:'share/locale/poland/map/metin2_map_a1/regen.txt',name:'Regen',category:'Spawns & maps'},
    {id:'share/locale/poland/map/metin2_map_b1/regen.txt',name:'Regen',category:'Spawns & maps'},
    {id:'special_spawns.txt',name:'Special spawns',category:'Build overrides'},
    {id:'share/locale/poland/quest/quest/hunting.quest',name:'Hunting',category:'Quests'}
  ];
  assert.deepEqual(nav.matchingFiles(rows,'maps','regen','Spawns & maps','metin2_map_a1'),[rows[0]]);
  assert.deepEqual(nav.matchingFiles(rows,'maps','','all','shared'),[rows[2]]);
  assert.equal(nav.matchingFiles(rows,'all','','all','metin2_map_a1').length,4);
  assert.equal(nav.mapFolder({id:'share\\locale\\poland\\map\\metin2_map_a1\\npc.txt'}),'metin2_map_a1');
  assert.deepEqual(nav.matchingFiles(rows,'quests',' HUNTING '),[rows[3]]);
});
