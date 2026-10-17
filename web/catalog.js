/* Catalog filtering is shared by every item selector. No editor state is changed. */
(function(root) {
  'use strict';
  const groups = [
    ['all', 'All categories'], ['bonus', 'Bonus items'], ['scrolls', 'Scrolls'],
    ['potions', 'Potions & buffs'], ['equipment', 'Equipment'], ['materials', 'Materials'],
    ['chests', 'Chests & keys'], ['books', 'Books'], ['stones', 'Spirit & dragon stones'],
    ['tools', 'Tools'], ['fishing', 'Fish & bait'], ['quest', 'Quest items'],
    ['other', 'Other items'], ['pools', 'Shared reward pools']
  ];
  const mobGroups = [['all', 'All types'], ['metin', 'Metins'], ['boss', 'Bosses'], ['monster', 'Monsters'], ['npc', 'NPCs']];
  const normalize = text => String(text ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const searchCache = new WeakMap();
  function groupKeys(item, kind = 'item') {
    return kind === 'mob' ? [item.category] : item.catalogGroups || ['other'];
  }
  function label(item, kind = 'item') {
    return kind === 'mob' ? (mobGroups.find(([key]) => key === item.category)?.[1] || item.category) : item.catalogLabel || 'Other item';
  }
  function help(item) {
    const description = item?.description;
    const sourceLabels = {
      definition: 'Installed seed values · live settings may differ',
      guide: 'General Metin2 guide · server rules may differ',
      catalog: 'Catalog category guide · effect unverified',
      unknown: 'Effect not documented'
    };
    return {
      text: description?.text || 'No reliable effect description is available for this item. Check the in-game tooltip or Singleplayer wiki using its ID.',
      note: description?.note || '',
      source: sourceLabels[description?.source] || sourceLabels.unknown,
      facts: Array.isArray(description?.facts) ? description.facts.filter(fact=>Array.isArray(fact)&&fact.length===2) : []
    };
  }
  function searchText(item, kind) {
    if (!searchCache.has(item)) {
      const categories = groupKeys(item, kind).map(key => (kind === 'mob' ? mobGroups : groups).find(([id]) => id === key)?.[1] || key);
      searchCache.set(item, normalize([item.id, item.name, item.keywords, item.original, item.description?.text, label(item, kind), ...categories].filter(Boolean).join(' ')));
    }
    return searchCache.get(item);
  }
  function query(items, options = {}) {
    const {kind = 'item', category = 'all', function: func = 'all', search = '', sort = 'name', allow} = options;
    const tokens = normalize(search).trim().split(/\s+/).filter(Boolean);
    const eligible = allow ? items.filter(allow) : items;
    const searched = eligible.filter(item => tokens.every(token => searchText(item, kind).includes(token)));
    const counts = Object.fromEntries((kind === 'mob' ? mobGroups : groups).map(([key]) => [key, key === 'all' ? searched.length : searched.filter(item => groupKeys(item, kind).includes(key)).length]));
    const inCategory = item => category === 'all' || groupKeys(item, kind).includes(category);
    const functions = new Map();
    if (kind === 'item') eligible.filter(inCategory).forEach(item => {
      const key = item.catalogKind || 'unclassified';
      if (!functions.has(key)) functions.set(key, {id: key, name: label(item, kind), count: 0});
    });
    const categoryMatches = searched.filter(inCategory);
    categoryMatches.forEach(item => { const fn = functions.get(item.catalogKind || 'unclassified'); if (fn) fn.count++; });
    const results = categoryMatches.filter(item => func === 'all' || item.catalogKind === func);
    results.sort((a, b) => {
      if (sort === 'id' || sort === 'id-desc') return (sort === 'id-desc' ? -1 : 1) * a.id.localeCompare(b.id, 'en', {numeric: true});
      if (sort === 'level') {
        const difference = (a.requiredLevel ?? a.level ?? Infinity) - (b.requiredLevel ?? b.level ?? Infinity);
        if (difference && !Number.isNaN(difference)) return difference;
      }
      return a.name.localeCompare(b.name, 'en', {numeric: true, sensitivity: 'base'}) || a.id.localeCompare(b.id, 'en', {numeric: true});
    });
    return {results, counts, functions: [...functions.values()].sort((a, b) => a.name.localeCompare(b.name))};
  }
  const api = {groups, mobGroups, normalize, groupKeys, label, help, query};
  root.StudioCatalog = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
