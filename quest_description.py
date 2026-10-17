"""Plain-language, evidence-labelled previews of saved/staged quest sources."""
import re

from quest_templates import template_values
from quest_support import quest_name
from quest_fields import analyse, tokens, calls, literal


def unique(values):
    return list(dict.fromkeys(values))


def short_list(values, limit=4):
    values = unique(values)
    return '; '.join(values[:limit]) + (f'; +{len(values)-limit} more' if len(values)>limit else '')


def integer(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def duration(seconds):
    n = integer(seconds)
    for unit, size in (('day',86400),('hour',3600),('minute',60)):
        if n and n % size == 0:
            count = n // size
            return f'{count:,} {unit}' + ('s' if count!=1 else '')
    return f'{n:,} seconds'


def title_for(identity):
    for pattern, label in ((r'collect_quest_lv(\d+)','Biologist research'),(r'(?:make|collect)_herb_lv(\d+)','Biologist herbs'),(r'main_quest_lv(\d+)','Main story')):
        match = re.fullmatch(pattern,identity)
        if match: return label+' · Level '+match[1]
    return 'Hunting quests' if identity=='hunting' else identity.replace('_',' ')


def describe(studio,ident):
    path = studio.safe(studio.root / str(ident))
    supported = path.parent in (studio.game/'quest',studio.game/'custom-quests') or path.is_relative_to(studio.locale/'quest/quest')
    if not supported or path.suffix!='.quest' or path.relative_to(studio.root).as_posix()!=ident or any(p in ('object','pre_qc','_unused') for p in path.parts):
        raise ValueError('Choose a quest from the quest library.')
    raw = studio.read(path)
    if raw is None or len(raw)>1200000 or not (identity:=quest_name(raw)):
        raise ValueError('This quest source is missing or unsupported.')
    result = {'id':ident,'questName':identity,'title':title_for(identity),'summary':'','facts':[], 'notes':[],
              'source':'Saved source values, including the active change set. Unsaved drafts and character progress are not included.'}
    def fact(label,value):
        if value: result['facts'].append([label,str(value)])
    def name(kind,ident):
        ident=str(ident)
        special={'primary_armor':'Armour for the player’s class','primary_helmet':'Helmet for the player’s class'}
        if ident in special:return special[ident]
        entry=(studio.items if kind=='item' else studio.mobs).get(ident,{})
        return entry.get('name','#'+ident) + (f' (#{ident})' if entry else '')
    template=template_values(raw)
    if template:
        kind=template.get('template','hunt')
        result['title']=str(template.get('title',identity))[:200]
        result['summary']={'hunt':'Defeat the required targets, then return to claim your rewards.',
                           'collection':'Bring the required items and hand them in for rewards.',
                           'exchange':'Exchange the required materials for the configured rewards.'}.get(kind,'A custom Studio quest.')
        fact('Level',f"{integer(template.get('level'),1)}+")
        if kind=='hunt':fact('Objective',f"Defeat {integer(template.get('kills')):,} × {name('mob',template.get('target',''))}")
        elif kind in ('collection','exchange'):
            fact('Turn in',f"{integer(template.get('requiredCount')):,} × {name('item',template.get('requiredItem',''))} (consumed)")
        fact('Start NPC',name('mob',template.get('npc','')))
        destination=template.get('returnNpc') or template.get('npc','')
        fact('Return to',name('mob',destination))
        rewards=[f"{integer(template.get('quantity'),1):,} × {name('item',template.get('reward',''))}"]
        for key,label in (('yang','Yang'),('exp','EXP')):
            if integer(template.get(key)): rewards.append(f'{integer(template[key]):,} {label}')
        fact('Rewards','; '.join(rewards))
        cooldown=integer(template.get('cooldown'))
        fact('Repeat',f'Available again after {duration(cooldown)}' if cooldown else 'Once per character')
        return result
    if identity=='hunting':
        result['summary']='A sequence of hunting quests. At each stage, choose one target option, defeat the required number and receive that stage’s rewards.'
    elif re.fullmatch(r'collect_quest_lv\d+',identity):
        result['summary']='Gather research specimens and submit them to the Biologist for analysis. Successful submissions advance the research towards its completion rewards.'
    elif re.fullmatch(r'(?:make|collect)_herb_lv\d+',identity):
        result['summary']='Gather specimens for the Biologist and hand them in for analysis. The quest advances when enough submissions are accepted.'
    elif identity.startswith('main_quest_'):
        result['summary']='A chapter of the main storyline, involving NPC conversations and the objectives recognised below.'
    elif identity in ('horse_levelup','pony_levelup'):
        result['summary']='Horse progression and training. Different stages can have different targets, requirements and waiting times.'
    elif identity.startswith('horse_'):
        result['summary']='A horse-related game quest or NPC interaction. Recognised requirements and operations are listed below.'
    else:
        result['summary']='An existing game quest or NPC/system interaction. The details below describe recognised source values; separate branches can have different requirements and rewards.'
    try:
        model=analyse(studio,ident)
        fields=model.fields
        analysis_notes=model.notes
    except (ValueError,OSError,KeyError,TypeError):
        fields=[]
        analysis_notes=[]
        result['notes'].append('Detailed objectives and rewards could not be read reliably for this source version.')
    if identity=='hunting' and fields:
        groups=unique(f['group'] for f in fields)
        levels=[integer(g.rsplit(' ',1)[-1]) for g in groups]
        fact('Progression',f'{len(groups)} stages · levels {min(levels)}–{max(levels)}')
        first=[f for f in fields if f['group']==groups[0]]
        options=[]
        for f in first:
            if f['kind']=='mob':
                suffix=f['key'].rsplit(':',1)[0]+':2'
                qty=next((v['value'] for v in first if v['key']==suffix),'?')
                options.append(f"{qty} × {name('mob',f['value'])}")
        fact('First stage · choose one',' OR '.join(options))
        reward=next((f['value'] for f in first if f['kind']=='item'),None)
        xp=next((f['value'] for f in first if f['label']=='EXP reward (% of stage level)'),None)
        fact('First-stage rewards',f'{name("item",reward)}; {xp}% EXP of the stage level' if reward and xp else '')
        result['notes'].append('Later stages have their own targets and rewards. EXP percentages refer to the stage level.')
        return result
    levels=unique(f['value']+'+' for f in fields if f['label']=='Minimum level')
    fact('Level checks',short_list(levels))
    total=next((f['value'] for f in fields if f['label']=='Successful submissions required'),None)
    chance=unique(f['value']+'%' for f in fields if f['label']=='Submission success (%)')
    if total:fact('Objective',total+' successful submissions')
    fact('Submission success',short_list(chance))
    items=[name('item',f['value']) for f in fields if f['kind']=='item' and f['label']=='Required / quest-drop item']
    fact('Required / quest-drop items',short_list(items))
    requirements=[f['value']+' × '+name('item',f['label'].split('#')[-1]) for f in fields if f['label'].startswith('Required & consumed quantity')]
    if requirements and not total:fact('Consumed quantities',short_list(requirements))
    targets=[name('mob',f['value']) for f in fields if f['kind']=='mob']
    fact('Kill targets',short_list(targets,3))
    counts=[f['label'].replace('Kill counter threshold · ','').replace('Starting kill count · ','')+': '+f['value'] for f in fields if f['label'].startswith(('Kill counter threshold','Starting kill count'))]
    fact('Kill counters',short_list(counts,2))
    completion=[];granted=[]
    stats={'POINT_MOV_SPEED':'Movement speed','POINT_ATT_SPEED':'Attack speed','POINT_DEF_GRADE_BONUS':'Defence','POINT_ATT_GRADE_BONUS':'Attack value','POINT_DEF_BONUS':'Defence bonus','POINT_ATT_BONUS':'Attack bonus','POINT_RESIST_HUMAN':'Resistance against humans','POINT_ATTBONUS_HUMAN':'Strong against humans'}
    for f in fields:
        if f['kind']=='item' and f['label']=='Granted item':
            quantities=unique(q['value'] for q in fields if q['group']==f['group'] and q['label']=='Granted quantity · #'+f['value'])
            text=(quantities[0]+' × ' if len(quantities)==1 else '')+name('item',f['value'])
            (completion if f['group'].startswith('Completion rewards') else granted).append(text)
        elif f['label'].startswith('Permanent bonus · '):
            stat=f['label'].split(' · ',1)[1]
            completion.append(stats.get(stat,stat)+' +'+f['value'])
        elif f['label'] in ('Yang reward','EXP reward'):
            granted.append(f"{integer(f['value']):,} "+('Yang' if f['label']=='Yang reward' else 'EXP'))
    fact('Completion rewards',short_list(completion))
    fact('Recognised grants',short_list(granted,3))
    if granted:result['notes'].append('Recognised grants can include intermediate quest items or branch-specific rewards; they are not necessarily all given at completion.')
    waits=unique(duration(f['value']) for f in fields if f['label']=='Cooldown (seconds)')
    fact('Saved-flag cooldowns',short_list(waits,2))
    shared=next((f for f in fields if f['label']=='Biologist wait (hours) · shared'),None)
    if shared:
        fact('Shared waiting time','Controlled by world difficulty; custom wait is inactive.' if shared['disabled'] else shared['value']+' hours · shared across Biologist research quests')
    ts=tokens(raw.decode('latin1'));npcs=[];database=False
    for name_,args,i,k in calls(ts):
        if name_=='find_npc_by_vnum' and args and (span:=literal(args[0])) and studio.mobs.get(span[0],{}).get('category')=='npc':npcs.append(name('mob',span[0]))
        if name_=='give_reward':database=True
    fact('NPC references',short_list(npcs,3))
    if database or any('database reward' in n for n in analysis_notes):
        result['notes'].append('Some rewards come from the game’s database reward table and are not included in this file-based preview.')
    # Biologist herb rewards are indirect through a shared helper.
    if identity.startswith('make_herb_') and not completion:
        result['notes'].append('Completion rewards are delegated to a shared helper/database table and are not fully shown here.')
    if not fields:result['notes'].append('No supported literal objectives or rewards were detected. This can be a system handler rather than a player-facing journal quest.')
    result['notes']=unique(result['notes'])
    return result
