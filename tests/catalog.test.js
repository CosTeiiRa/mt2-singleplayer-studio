'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {query, help} = require('../web/catalog.js');
const item = (id, name, group, func, label, extra = {}) => ({id, name, catalogGroups:[group], catalogKind:func, catalogLabel:label, ...extra});
const items = [
  item('71084', 'Enchant Item', 'bonus', 'bonus-changer', 'Bonus changer', {keywords:'efsún nesnesi'}),
  item('71085', 'Reinforce Item', 'bonus', 'bonus-adder', 'Bonus adder'),
  item('70024', 'Blessing Marble', 'bonus', 'fifth-bonus', 'Fifth bonus marble'),
  item('25040', 'Blessing Scroll', 'scrolls', 'upgrade-scroll', 'Upgrade scroll & protection'),
  item('27002', 'Red Potion(M)', 'potions', 'recovery-potion', 'HP & MP potion'),
  item('27101', 'Green Potion(M)', 'potions', 'speed-potion', 'Speed potion'),
  item('10', 'Bonus Sword', 'equipment', 'weapon-0', 'Sword', {requiredLevel:1}),
  item('100', 'Sword+9', 'equipment', 'weapon-0', 'Sword', {requiredLevel:50}),
  item('s8001', 'Metin loot pool', 'pools', 'reward-pool', 'Shared reward pool'),
];

test('category and function filters combine with a multiword search', () => {
  assert.deepEqual(query(items, {category:'bonus', function:'bonus-changer', search:'changer 71084'}).results.map(i=>i.id), ['71084']);
  assert.equal(query(items, {category:'bonus'}).results.length, 3);
  assert.equal(query(items, {category:'bonus', search:'sword'}).results.length, 0);
  assert.equal(query(items, {category:'scrolls', function:'bonus-changer'}).results.length, 0);
});

test('search matches accents, translated keywords, labels and separate words', () => {
  assert.equal(query(items, {search:' EFSUN   item '}).results[0].id, '71084');
  assert.equal(query(items, {search:'protection'}).results[0].id, '25040');
  assert.equal(query(items, {category:'potions', search:'green M'}).results[0].id, '27101');
});

test('facet counts and functions respect the context and search', () => {
  const result = query(items, {category:'bonus', search:'enchant', allow:i=>i.id!=='70024'});
  assert.equal(result.counts.all, 1);
  assert.equal(result.counts.bonus, 1);
  assert.equal(result.functions.find(i=>i.id==='bonus-changer').count, 1);
  assert.equal(result.functions.find(i=>i.id==='bonus-adder').count, 0);
  assert.equal(result.functions.some(i=>i.id==='fifth-bonus'), false);
});

test('numeric ID and level sorting do not mutate the catalog', () => {
  const original = items.map(i=>i.id);
  assert.deepEqual(query(items, {category:'equipment', sort:'id'}).results.map(i=>i.id), ['10','100']);
  assert.deepEqual(query(items, {category:'equipment', sort:'id-desc'}).results.map(i=>i.id), ['100','10']);
  assert.equal(query(items, {sort:'level'}).results[0].id, '10');
  assert.deepEqual(items.map(i=>i.id), original);
});

test('shared pools stay separate from ordinary item categories', () => {
  assert.deepEqual(query(items, {category:'pools'}).results.map(i=>i.id), ['s8001']);
  assert.equal(query(items, {category:'pools', allow:i=>!i.id.startsWith('s')}).results.length, 0);
});

test('mob filtering preserves picker restrictions and level sorting', () => {
  const mobs = [
    {id:'8001', name:'Metin of Sorrow', category:'metin', level:5},
    {id:'9001', name:'Weapon Shop Dealer', category:'npc', level:1},
    {id:'101', name:'Wild Dog', category:'monster', level:1},
  ];
  assert.deepEqual(query(mobs, {kind:'mob', category:'metin'}).results.map(i=>i.id), ['8001']);
  const result = query(mobs, {kind:'mob', allow:i=>i.category==='npc'});
  assert.equal(result.counts.all, 1);
  assert.equal(result.counts.metin, 0);
  assert.equal(result.functions.length, 0);
});

test('item help labels uncertainty and handles missing descriptions', () => {
  assert.match(help(items[0]).text, /No reliable effect/);
  assert.equal(help(items[0]).source, 'Effect not documented');
  const detail = help({...items[0], description:{text:'Rerolls bonuses.', note:'Restriction.', source:'guide', facts:[['Level','40'],null,['bad']]}});
  assert.match(detail.source, /server rules may differ/);
  assert.equal(detail.note, 'Restriction.');
  assert.deepEqual(detail.facts, [['Level','40']]);
});

test('effect descriptions are searchable together with existing filters', () => {
  const described = {...items[0], description:{text:'Rerolls existing bonuses.'}};
  assert.deepEqual(query([described,items[1]], {category:'bonus', search:'rerolls 71084'}).results.map(i=>i.id), ['71084']);
});

test('installed scope excludes catalogue-only rows but preserves pools and explicit ID inspection',()=>{
  const rows=[item('10','Sword','equipment','weapon','Sword',{definitionStatus:'installed-seed'}),
    item('310','Archived sword','equipment','weapon','Sword',{definitionStatus:'catalogue-only'}),items[8]];
  assert.deepEqual(query(rows,{scope:'installed',sort:'id'}).results.map(row=>row.id),['10','s8001']);
  assert.deepEqual(query(rows,{scope:'all',sort:'id'}).results.map(row=>row.id),['10','310','s8001']);
  assert.deepEqual(query(rows,{scope:'installed',search:'310'}).results.map(row=>row.id),['310']);
  assert.equal(query(rows,{scope:'installed',search:'310',allow:row=>row.id!=='310'}).results.length,0);
});

test('catalogue quality filters and original names remain searchable',()=>{
  const rows=[item('30315','Bread','quest','quest-item','Quest item',{catalogName:'NoNAme',original:'Chleb',definitionStatus:'installed-seed',iconAvailable:false,nameStatus:'named'}),
    item('30528','Unnamed item #30528','quest','quest-item','Quest item',{definitionStatus:'installed-seed',nameStatus:'unnamed',iconAvailable:true})];
  assert.deepEqual(query(rows,{scope:'missing-icons'}).results.map(row=>row.id),['30315']);
  assert.deepEqual(query(rows,{scope:'name-issues'}).results.map(row=>row.id),['30528']);
  assert.equal(query(rows,{search:'chleb'}).results[0].id,'30315');
  assert.equal(query(rows,{search:'noname'}).results[0].id,'30315');
});
