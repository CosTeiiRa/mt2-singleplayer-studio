export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
}

export function descriptionSummary(value) {
  return String(value??'').trim().split(/\r?\n\s*\r?\n/).find(block=>!/^#{2,3}\s/.test(block))?.replace(/\r?\n/g,' ')??'';
}

export function descriptionMarkup(value) {
  const blocks=String(value||'No description provided.').trim().split(/\r?\n\s*\r?\n/);
  let output='',section=false;
  for(const block of blocks){
    const heading=block.match(/^#{2,3}\s+([^\r\n]+)$/);
    if(heading){
      if(section)output+='</section>';
      output+=`<section class="addon-description-section"><h3>${escapeHtml(heading[1])}</h3>`;
      section=true;
      continue;
    }
    const lines=block.split(/\r?\n/);
    const ordered=lines.every(line=>/^\d+\.\s+/.test(line));
    const unordered=lines.every(line=>/^-\s+/.test(line));
    if(ordered||unordered){
      const tag=ordered?'ol':'ul',prefix=ordered?/^\d+\.\s+/:/^-\s+/;
      output+=`<${tag}>${lines.map(line=>`<li>${escapeHtml(line.replace(prefix,''))}</li>`).join('')}</${tag}>`;
    }else output+=`<p class="detail-description">${escapeHtml(block)}</p>`;
  }
  return `<div class="addon-description">${output}${section?'</section>':''}</div>`;
}

export function unwrap(payload, key) {
  if (payload?.ok === false) throw new Error(payload.error || 'The request could not be completed.');
  return payload?.[key] ?? payload ?? {};
}

export function asArray(value) {
  if (Array.isArray(value)) return value;
  if (value && typeof value === 'object') return Object.entries(value).map(([id, entry]) => typeof entry === 'object' && entry !== null ? {id, ...entry} : {id, value: entry});
  return [];
}

export function filterCatalog(items, query = '', category = 'all') {
  const words = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  return items.filter(item => (category === 'all' || item.category === category) && words.every(word => [item.name, item.id, item.description, item.author, item.category].join(' ').toLocaleLowerCase().includes(word)));
}

export function installedRecord(item, installed = []) {
  return asArray(installed).find(record => record.id === item.id || record.addon_id === item.id) || (item.installed && typeof item.installed === 'object' ? item.installed : item.installed ? {id: item.id, enabled: item.enabled !== false, version: item.version} : null);
}

export function addonStatus(item, installed) {
  const record = installedRecord(item, installed);
  if (item.error || item.valid === false || item.validation_errors?.length || item.status === 'invalid') return {label: 'Package issue', tone: 'danger'};
  if (record) {
    const integrity=record.integrity??item.integrity;
    if(integrity?.status==='missing')return {label:'Needs reinstall',tone:'danger'};
    if(integrity?.status==='changed')return {label:'Files changed',tone:'copper'};
    if(integrity?.status==='unavailable')return {label:'Cannot verify files',tone:'danger'};
    if(integrity?.status!=='healthy')return {label:'Files not checked',tone:'muted'};
    return record.enabled === false ? {label: 'Disabled', tone: 'muted'} : {label: 'Enabled', tone: 'success'};
  }
  return {label: 'Available', tone: 'muted'};
}

export function compatibilityStatus(item) {
  const reasons = planMessages(item.incompatibility_reasons);
  if (item.compatibility_status === 'incompatible' && reasons.length) return {
    label:'Known incompatibility',tone:'danger',
    description:'A specific compatibility problem has been recorded for this target.',notes:reasons
  };
  if (item.compatibility_status === 'declared') return {
    label:'Declared compatible',tone:'muted',
    description:'This target matches the publisher’s declared versions and profiles. Independent in-game verification has not been recorded.',notes:[]
  };
  if (item.compatibility_status === 'unknown') return {
    label:'Compatibility not checked',tone:'muted',
    description:'Select a target to compare its game and client versions with the publisher’s declarations.',notes:[]
  };
  return {label:'Compatibility unverified',tone:'copper',
    description:'Compatibility with this target has not been verified. This does not mean the add-on is incompatible. You can still review and apply it to a supported game client.',
    notes:planMessages(item.warnings)};
}

export function formatTime(value) {
  if (!value) return 'Time not recorded';
  const date = new Date(typeof value === 'number' && value < 1e12 ? value * 1000 : value);
  return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat(undefined, {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'}).format(date);
}

export function humanize(value) {
  return String(value ?? '').replace(/[_-]/g, ' ').replace(/^\w/, character => character.toUpperCase());
}

export function changeRows(changes) {
  return asArray(changes).map(change => typeof change === 'string' ? {path: change, action: 'Change'} : {
    path: change.path ?? change.target ?? change.file ?? change.id ?? 'Configuration',
    action: humanize(change.action ?? change.operation ?? change.type ?? change.status ?? 'change'),
    detail: change.detail ?? change.description ?? (change.before_sha256 && change.after_sha256 ? 'Content fingerprint changes' : '')
  });
}

export function planMessages(value) {
  return asArray(value).map(entry => typeof entry === 'string' ? entry : entry.message ?? entry.reason ?? entry.description ?? JSON.stringify(entry));
}

export function sourceLabel(source) {
  if (!source) return 'Source details not provided';
  if (typeof source === 'string') return source;
  return source.path ?? source.file ?? source.label ?? source.name ?? JSON.stringify(source);
}

export function mapRegions(map) {
  return asArray(map?.regions ?? map?.spawns ?? map?.bosses ?? map?.spawn_regions).map((region, index) => {
    const center = region.center ?? region.position ?? {};
    const coordinates = Array.isArray(region.coordinates) ? region.coordinates : [];
    const number = (...values) => {
      const first = values.find(value => value !== undefined && value !== null && value !== '' && Number.isFinite(Number(value)));
      return first === undefined ? undefined : Number(first);
    };
    return {...region, index, name: region.name ?? region.boss_name ?? region.mob_name ?? region.label ?? (region.vnum ? `Boss ${region.vnum}` : `Spawn area ${index + 1}`), x: number(region.x, center.x, coordinates[0]), y: number(region.y, center.y, coordinates[1]), width: Math.max(0, number(region.width, region.range_x, region.radius_x, region.rx) ?? 0), height: Math.max(0, number(region.height, region.range_y, region.radius_y, region.ry) ?? 0)};
  });
}

export function mapBounds(map, regions) {
  const points = regions.filter(region => Number.isFinite(region.x) && Number.isFinite(region.y));
  const supplied = map?.bounds ?? {};
  const width = Number(map?.width ?? map?.size?.width ?? supplied.width);
  const height = Number(map?.height ?? map?.size?.height ?? supplied.height);
  if (width > 0 && height > 0) return {x: Number(supplied.x ?? supplied.min_x) || 0, y: Number(supplied.y ?? supplied.min_y) || 0, width, height, inferred: map?.coverage?.bounds_verified === false};
  if (!points.length) return {x: 0, y: 0, width: 1000, height: 1000, inferred: true};
  const minX = Math.min(...points.map(region => region.x - region.width / 2));
  const minY = Math.min(...points.map(region => region.y - region.height / 2));
  const maxX = Math.max(...points.map(region => region.x + region.width / 2));
  const maxY = Math.max(...points.map(region => region.y + region.height / 2));
  const padding = Math.max((maxX - minX) * 0.12, (maxY - minY) * 0.12, 50);
  return {x: Math.floor(minX - padding), y: Math.floor(minY - padding), width: Math.max(100, maxX - minX + 2 * padding), height: Math.max(100, maxY - minY + 2 * padding), inferred: true};
}

export function respawnLabel(region) {
  const value = region.respawn ?? region.respawn_range ?? region.interval ?? region.respawn_seconds;
  if (value === undefined || value === null || value === '') return 'Interval not provided';
  if (Array.isArray(value)) return `${value.join('–')}${region.respawn_unit ? ` ${region.respawn_unit}` : ''}`;
  if (typeof value === 'object') return `${value.min ?? value.minimum ?? '?'}–${value.max ?? value.maximum ?? '?'} ${value.unit ?? region.respawn_unit ?? ''}`.trim();
  return `${value}${region.respawn_unit ? ` ${region.respawn_unit}` : region.respawn_seconds !== undefined ? ' seconds' : ''}`;
}

export function booleanSettings(item, record) {
  return Object.entries(item.settings_schema?.properties ?? {}).filter(([, specification]) => specification.type === 'boolean').map(([key, specification]) => ({
    key,
    label: specification.title ?? humanize(key),
    description: specification.description ?? '',
    value: record?.settings?.[key] ?? item.settings?.[key] ?? specification.default ?? false
  }));
}

export function settingFields(item,record){
  const schema=record?.settings_schema??item.settings_schema??{};
  return Object.entries(schema.properties??{}).map(([key,spec])=>({key,spec,type:spec.type??'string',
    label:spec.title??humanize(key),description:spec.description??'',
    value:record?.settings?.[key]??item.settings?.[key]??spec.default??(spec.type==='boolean'?false:spec.type==='object'?{}:spec.type==='array'?[]:'')}));
}

export function parseSettingValue(value,spec,label='Setting'){
  if(spec.enum){
    let parsed;try{parsed=JSON.parse(value);}catch{throw Error(`${label}: choose a listed value.`);}
    if(!spec.enum.some(item=>JSON.stringify(item)===JSON.stringify(parsed)))throw Error(`${label}: choose a listed value.`);
    return parsed;
  }
  if(spec.type==='boolean')return value===true;
  if(spec.type==='integer'||spec.type==='number'){
    const parsed=Number(value);
    if(String(value).trim()===''||!Number.isFinite(parsed)||spec.type==='integer'&&!Number.isInteger(parsed))throw Error(`${label}: enter a valid ${spec.type}.`);
    return parsed;
  }
  if(spec.type==='array'||spec.type==='object'){
    let parsed;try{parsed=JSON.parse(value);}catch{throw Error(`${label}: enter valid JSON.`);}
    if(spec.type==='array'?!Array.isArray(parsed):parsed===null||Array.isArray(parsed)||typeof parsed!=='object')throw Error(`${label}: enter a JSON ${spec.type}.`);
    return parsed;
  }
  return String(value);
}

export function atlasSpecies(map, type='all', search='') {
  const species=new Map(),query=search.trim().toLocaleLowerCase();
  for(const region of mapRegions(map)){
    if(type==='enemies'?!['monster','boss','metin'].includes(region.type):type!=='all'&&region.type!==type)continue;
    if(query&&!`${region.name} ${region.mob_id} ${region.level??''}`.toLocaleLowerCase().includes(query))continue;
    const id=String(region.mob_id);
    if(!species.has(id))species.set(id,{...region,mob_id:id,zones:[]});
    species.get(id).zones.push(region);
  }
  return [...species.values()].sort((a,b)=>(a.level??0)-(b.level??0)||a.name.localeCompare(b.name));
}
