"""Guided edits of literal values in existing quests; never evaluate game Lua.

Offsets refer to Latin-1 decoded bytes, so applying a field preserves all other
bytes, comments, encodings and newlines. Re-analyse on preview and require hashes
of every dependency. Dynamic expressions stay in the advanced source editor.
"""
from dataclasses import dataclass
import ast
import hashlib
import re

from quest_support import quest_name, source_changes


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@dataclass
class Token:
    value: str
    start: int
    end: int
    kind: str


def tokens(text):
    pattern = re.compile(r'--\[(=*)\[.*?\]\1\]|--[^\r\n]*|\[(=*)\[.*?\]\2\]|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\d+(?:\.\d+)?|[A-Za-z_]\w*|>=|<=|==|~=|.', re.S)
    result = []
    for m in pattern.finditer(text):
        v = m[0]
        if v.isspace() or v.startswith('--'):
            continue
        kind = 'string' if v[0] in '"\'' else 'longstring' if v.startswith('[') and len(v) > 1 else 'number' if v[0].isdigit() else 'name' if v[0].isalpha() or v[0] == '_' else 'symbol'
        result.append(Token(v, m.start(), m.end(), kind))
    return result


def literal(arg):
    if len(arg) != 1:
        return None
    t = arg[0]
    if t.kind == 'number' and t.value.isdigit():
        return t.value, t.start, t.end
    if t.kind == 'string' and t.value[1:-1].isdigit():
        return t.value[1:-1], t.start + 1, t.end - 1
    return None


def calls(ts):
    for i, t in enumerate(ts):
        if t.kind != 'name' or i and ts[i-1].value in ('.', ':'):
            continue
        j, name = i + 1, t.value
        while j+1 < len(ts) and ts[j].value == '.' and ts[j+1].kind == 'name':
            name += '.' + ts[j+1].value
            j += 2
        if j >= len(ts) or ts[j].value != '(':
            continue
        args, arg, depth, k = [], [], 0, j+1
        while k < len(ts):
            v = ts[k].value
            if v == ')' and depth == 0:
                if arg or args:
                    args.append(arg)
                yield name, args, i, k
                break
            if v == ',' and depth == 0:
                args.append(arg); arg = []
            else:
                arg.append(ts[k])
                if v in ('(', '{', '['): depth += 1
                if v in (')', '}', ']'): depth -= 1
            k += 1


class Model:
    def __init__(self, studio, ident):
        self.studio, self.ident = studio, ident
        self.docs, self.fields, self.notes = {}, [], []

    def document(self, path):
        path = self.studio.safe(path)
        raw = self.studio.read(path)
        if raw is None:
            raise ValueError('A quest dependency is missing: ' + path.name)
        rel = path.relative_to(self.studio.root).as_posix()
        self.docs[rel] = raw
        return rel, raw.decode('latin1')

    def add(self, doc, key, label, group, value, edits, kind='number', low=0, high=1000000000, detail='', choices=None, disabled=False):
        field = dict(key=doc+':'+key, label=label, group=group, value=str(value), kind=kind,
                     min=low, max=high, detail=detail, disabled=disabled, edits=edits, document=doc)
        if choices: field['choices'] = choices
        self.fields.append(field)
        return field

    def public(self):
        return {'id': self.ident, 'questName': quest_name(self.docs[self.ident]),
                'hashes': {path: sha(raw) for path, raw in self.docs.items()},
                'fields': [{k: v for k, v in f.items() if k not in ('edits', 'document')} for f in self.fields],
                'notes': self.notes,
                'sources': list(self.docs)}


def edit(span, delta=0):
    return {'start': span[1], 'end': span[2], 'delta': delta}


def generic(model, doc, text, group_prefix=''):
    ts = tokens(text)
    # State names are context labels, never editable identities.
    states = [(ts[i+1].start, ts[i+1].value) for i,t in enumerate(ts[:-2]) if t.value == 'state' and ts[i+2].value == 'begin']
    def context(pos):
        state = next((name for start,name in reversed(states) if start < pos), '')
        line = text.count('\n', 0, pos)+1
        return group_prefix or ('Stage: ' + state if state else 'Quest values'), f'Line {line}'
    all_calls = list(calls(ts))
    item_calls, consumed, checks, dynamic = {}, {}, {}, set()
    names = {'pc.give_item2': 0, 'pc.give_item': 0, 'pc.remove_item': 0, 'pc.count_item': 0,
             'say_item_vnum': 0, 'item_name': 0, 'say_item': 1}
    for name,args,i,k in all_calls:
        group, line = context(ts[i].start)
        argidx = names.get(name)
        if argidx is not None and len(args) > argidx:
            span = literal(args[argidx])
            if span:
                item_calls.setdefault(span[0], []).append((span, name, group, line))
                if name == 'pc.remove_item' and len(args) >= 2 and (quantity := literal(args[1])):
                    consumed.setdefault((group, span[0], quantity[0]), []).append(edit(quantity))
                if name == 'pc.count_item' and k+2 < len(ts) and ts[k+1].value in ('<','>=','>','<=') and ts[k+2].kind == 'number' and ts[k+2].value.isdigit():
                    # Only a complete literal threshold, never the prefix of an expression.
                    after = ts[k+3].value if k+3 < len(ts) else ''
                    if after not in ('+', '-', '*', '/', '%', '^', '..'):
                        n = ts[k+2]
                        offset=1 if ts[k+1].value in ('>','<=') else 0
                        checks.setdefault((group, span[0], str(int(n.value)+offset)), []).append({'start':n.start,'end':n.end,'delta':-offset})
            elif name.startswith('pc.'):
                dynamic.add('Some item operations compute their IDs or quantities at runtime.')
        if name in ('pc.give_item2','pc.give_item') and args and literal(args[0]):
            ident = literal(args[0])[0]
            if len(args) == 1:
                model.add(doc,f'qty:{ts[i].start}',f'Granted quantity · #{ident}',group,1,[{'start':ts[k].start,'end':ts[k].start,'prefix':', '}],low=1,high=200,detail=line)
            elif (span := literal(args[1])):
                model.add(doc,f'qty:{ts[i].start}',f'Granted quantity · #{ident}',group,span[0],[edit(span)],low=1,high=200,detail=line)
        if name in ('pc.change_money','pc.change_gold','pc.give_exp2','pc.give_exp') and len(args) == 1:
            span = literal(args[0])
            if span:
                label = 'Yang reward' if 'change_' in name else 'EXP reward'
                model.add(doc,f'reward:{ts[i].start}',label,group,span[0],[edit(span)],detail=line)
            else:
                dynamic.add('Calculated currency or EXP rewards remain in the advanced editor.')
        if name == 'collect_data.take_chance' and len(args) == 1 and (span := literal(args[0])):
            model.add(doc,f'chance:{ts[i].start}','Submission success (%)',group,span[0],[edit(span)],high=100,detail=line)
        # A constant duration following get_time() is supported only inside a saved flag.
        if name in ('pc.setqf','pc.setf') and args:
            duration = args[-1]
            vals = [t.value for t in duration]
            if vals[:4] == ['get_time','(',')','+'] and len(duration) > 4:
                expr = duration[4:]
                try:
                    seconds = constant_seconds(expr)
                except ValueError:
                    dynamic.add('Random or calculated cooldowns remain in the advanced editor.')
                else:
                    model.add(doc,f'cooldown:{ts[i].start}','Cooldown (seconds)',group,seconds,[{'start':expr[0].start,'end':expr[-1].end}],high=31536000,detail=line+' · used when this flag is next set')
    for ident,uses in item_calls.items():
        functional = [u for u in uses if u[1].startswith('pc.')]
        if not functional: continue
        required = any(u[1] in ('pc.count_item','pc.remove_item') for u in uses)
        label = 'Required / quest-drop item' if required else 'Granted item'
        model.add(doc,'item:'+ident,label,group_prefix or 'Items',ident,[edit(u[0]) for u in uses],kind='item',detail=f'{len(uses)} linked uses; includes recognised checks, removals, grants and item-name displays.')
    for key,edits in consumed.items():
        group, ident, value = key
        model.add(doc,'required:'+str(edits[0]['start']),f'Required & consumed quantity · #{ident}',group,value,edits+checks.pop(key,[]),low=1,high=100000,detail='Linked literal inventory checks and removals in this stage.')
    for (group,ident,value),edits in checks.items():
        if int(value) > 0:
            model.add(doc,'check:'+str(edits[0]['start']),f'Inventory threshold · #{ident}',group,value,edits,low=1,high=100000,detail='Changes the inventory check only; the consumed quantity may have its own field.')
    # Literal kill targets and level gates; strings/comments never match.
    mobs = {}
    for i,t in enumerate(ts[:-2]):
        if t.kind == 'number' and t.value.isdigit() and ts[i+1].value == '.' and ts[i+2].value == 'kill':
            mobs.setdefault(t.value, []).append({'start':t.start,'end':t.end})
    for ident,edits in mobs.items():
        model.add(doc,'mob:'+ident,'Kill target',group_prefix or 'Targets',ident,edits,kind='mob',detail=f'{len(edits)} linked kill handlers. Quest-item drop rules stay attached to this target.')
    for name,args,i,k in all_calls:
        group,line = context(ts[i].start)
        if name == 'pc.get_level' and not args and k+2 < len(ts) and ts[k+1].value == '>=' and (span:=literal([ts[k+2]])) and (k+3==len(ts) or ts[k+3].value not in ('+','-','*','/')):
            model.add(doc,'level:'+str(ts[i].start),'Minimum level',group,span[0],[edit(span)],low=1,high=255,detail=line)
        if name == 'pc.getqf' and len(args)==1 and len(args[0])==1 and args[0][0].kind=='string' and k+2 < len(ts):
            flag=args[0][0].value[1:-1]
            op,n=ts[k+1],ts[k+2]
            if re.search(r'kill|hunt.*count',flag,re.I) and op.value in ('>=','>','<','<=','==') and n.kind=='number' and n.value.isdigit() and int(n.value)>0 and (k+3 == len(ts) or ts[k+3].value not in ('+','-','*','/')):
                model.add(doc,'kills:'+str(n.start),f'Kill counter threshold · {flag} {op.value}',group,n.value,[{'start':n.start,'end':n.end}],low=1,high=100000,detail=line)
        if name == 'pc.setqf' and len(args)==2 and len(args[0])==1 and re.search(r'kill|hunt.*count',args[0][0].value,re.I) and (span:=literal(args[1])) and int(span[0])>0:
            model.add(doc,'killstart:'+str(ts[i].start),'Starting kill count · '+args[0][0].value.strip('"\''),group,span[0],[edit(span)],low=1,high=100000,detail=line+' · countdown initial value')
        if name == 'give_reward':
            dynamic.add('Some rewards use the game’s database reward table. Those rewards are not exposed as file fields; direct item, Yang and EXP rewards are editable below.')
    for i,t in enumerate(ts[:-4]):
        if [x.value for x in ts[i:i+4]] == ['pc','.','level','>='] and (span:=literal([ts[i+4]])) and (i+5==len(ts) or ts[i+5].value not in ('+','-','*','/')):
            group,line=context(t.start)
            model.add(doc,'level:'+str(t.start),'Minimum level',group,span[0],[edit(span)],low=1,high=255,detail=line)
    model.notes.extend(sorted(dynamic))


def constant_seconds(ts):
    expression=''.join(t.value for t in ts)
    if not re.fullmatch(r'[\d+*() \-]+',expression):
        raise ValueError('Dynamic expression')
    def calc(node):
        if isinstance(node,ast.Constant) and type(node.value) is int: return node.value
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult)):
            a,b=calc(node.left),calc(node.right)
            if abs(a)>31536000 or abs(b)>31536000: raise ValueError('Too large')
            return a+b if isinstance(node.op,ast.Add) else a-b if isinstance(node.op,ast.Sub) else a*b
        raise ValueError('Dynamic expression')
    try:
        n=calc(ast.parse(expression,mode='eval').body)
    except (SyntaxError,RecursionError):
        raise ValueError('Unsupported duration') from None
    if not 0<=n<=31536000: raise ValueError('Unsupported duration')
    return n


def biologist(model,doc,text,identity):
    ts=tokens(text)
    # Hand-ins increment before completion: < N-1, with N-count displays.
    targets,remaining=[],[]
    for name,args,i,k in calls(ts):
        if name=='pc.getqf' and len(args)==1 and len(args[0])==1 and args[0][0].value in ('"collect_count"',"'collect_count'"):
            if k+2<len(ts) and ts[k+1].value=='<' and (span:=literal([ts[k+2]])):
                targets.append(span)
            if i>=2 and ts[i-1].value=='-' and (span:=literal([ts[i-2]])):
                remaining.append(span)
    if len(targets)==1:
        total=int(targets[0][0])+1
        linked=[span for span in remaining if int(span[0])==total]
        if linked:
            model.add(doc,'collection-total','Successful submissions required','Research requirements',total,[edit(targets[0],-1)]+[edit(s) for s in linked],low=1,high=100000,detail='Updates the completion target and recognised remaining-count expressions together. Existing player progress is retained.')
    for i,t in enumerate(ts[:-2]):
        if t.value=='pass_percent' and ts[i+1].value=='=' and (span:=literal([ts[i+2]])) and (i+3==len(ts) or ts[i+3].value not in ('+','-','*','/')):
            model.add(doc,'pass:'+str(t.start),'Submission success (%)','Research requirements',span[0],[edit(span)],high=100)
    helper=model.studio.game/'quest/m2_biologist.lua'
    if helper.exists() and 'm2_biologist.reward' in text:
        hdoc,htext=model.document(helper)
        # Native helper entries have explicit function boundaries. Work only in
        # the matching entry; another quest with the same reward ID is untouched.
        match=re.search(r'\["'+re.escape(identity)+r'"\]\s*=\s*function\(companion\)(.*?)(?=\n    end,)',htext,re.S)
        if match:
            start,end=match.span(1)
            segment=re.sub(r'[^\r\n]',' ',htext[:start])+htext[start:end]
            generic(model,hdoc,segment,'Completion rewards · shared with companion')
            hts=tokens(segment)
            for name,args,i,k in calls(hts):
                if name=='affect.add_collect' and len(args)>=2 and (span:=literal(args[1])):
                    stat=''.join(t.value for t in args[0])
                    model.add(hdoc,'bonus:'+str(span[1]),'Permanent bonus · '+stat,'Completion rewards · shared with companion',span[0],[edit(span)],high=100000,detail='Only newly granted bonuses use this value. Existing character bonuses are not rewritten.')
    if identity.startswith('collect_quest_lv') and 'collect_data.' in text:
        settings=model.studio.settings()
        row=next((r for r in settings['settings'] if r['key']=='M2_BIOLOGIST_WAIT_HOURS'),None)
        if row:
            edoc,env=model.document(model.studio.compose/'.env')
            difficulty=next((r['value'] for r in settings['settings'] if r['key']=='M2_DIFFICULTY'),'easy')
            model.add(edoc,'setting:M2_BIOLOGIST_WAIT_HOURS','Biologist wait (hours) · shared','Shared cooldown',row['value'],[],high=1000000,disabled=difficulty!='custom',detail='Shared by research quests, not a per-quest timer. Active only with World settings → difficulty = custom. Current difficulty: '+difficulty)


def hunting(model):
    doc,text=model.document(model.studio.locale/'quest/libs/other/hunting_data.lua')
    ts=tokens(text)
    start=next((i+2 for i,t in enumerate(ts[:-2]) if t.value=='HUNTING_QUEST_DATA' and ts[i+1].value=='=' and ts[i+2].value=='{'),None)
    if start is None: raise ValueError('The hunting data format changed; use the advanced editor.')
    def table(pos):
        if ts[pos].value!='{': raise ValueError('Unsupported hunting table')
        pos+=1; result={}; idx=1
        while pos<len(ts) and ts[pos].value!='}':
            key=idx
            if pos+1<len(ts) and ts[pos+1].value=='=':
                key=ts[pos].value;pos+=2
            else: idx+=1
            if ts[pos].value=='{': value,pos=table(pos)
            elif ts[pos].kind in ('number','string'):
                value=ts[pos];pos+=1
            else: raise ValueError('Calculated hunting data is not supported by guided fields.')
            if key in result: raise ValueError('Duplicate hunting data key')
            result[key]=value
            if ts[pos].value in (',',';'): pos+=1
            elif ts[pos].value!='}': raise ValueError('Calculated hunting data is not supported by guided fields.')
        if pos>=len(ts): raise ValueError('Incomplete hunting table')
        return result,pos+1
    data,_=table(start)
    for idx,row in data.items():
        if isinstance(row,dict) and set(row)=={'reqLvl'} and idx==len(data) and literal([row['reqLvl']]) and int(row['reqLvl'].value)>255:
            continue  # Native end-of-list sentinel, not an editable hunt.
        if not isinstance(row,dict) or not {'reqLvl','mobData','gold','xp','item'}<=row.keys():
            raise ValueError('A hunting stage uses an unsupported format.')
        level=literal([row['reqLvl']])
        group=f'Hunt {idx} · Level {level[0]}'
        for key,label,high in [('gold','Yang reward',1000000000),('xp','EXP reward (% of stage level)',100)]:
            span=literal([row[key]])
            if not span: raise ValueError('Calculated hunting rewards are unsupported.')
            model.add(doc,f'hunt:{idx}:{key}',label,group,span[0],[edit(span)],high=high)
        for option,pair in row['mobData'].items():
            for j,label,kind,high in [(1,f'Target option {option}','mob',99999999),(2,f'Kills · option {option}','number',100000)]:
                span=literal([pair[j]])
                if not span: raise ValueError('Calculated hunting targets are unsupported.')
                model.add(doc,f'hunt:{idx}:mob:{option}:{j}',label,group,span[0],[edit(span)],kind=kind,low=1,high=high,detail='Players choose one target option when starting this stage. Existing accepted targets/counts stay in character flags.')
        items=row['item']
        if len(items)%2: raise ValueError('Unpaired hunting reward item')
        for j in range(1,len(items)+1,2):
            t=items[j];span=literal([t]);value=span[0] if span else t.value[1:-1]
            if not span and value not in ('primary_armor','primary_helmet'):
                raise ValueError('Unknown symbolic hunting reward')
            model.add(doc,f'hunt:{idx}:item:{j}',f'Reward item {(j+1)//2}',group,value,[{'start':t.start,'end':t.end,'luaItem':True}],kind='item',choices=['primary_armor','primary_helmet'])
            qty=literal([items[j+1]])
            if not qty: raise ValueError('Calculated reward quantities are unsupported.')
            model.add(doc,f'hunt:{idx}:item:{j}:qty','Reward quantity',group,qty[0],[edit(qty)],low=1,high=200)
    model.notes.append('Hunting EXP is a percentage of the stage level. Target options are alternatives, not a list of targets all players must kill. Stage order and existing progress are preserved.')


def analyse(studio,ident):
    path=studio.safe(studio.root/str(ident))
    supported = path.parent in (studio.game/'quest', studio.game/'custom-quests') or path.is_relative_to(studio.locale/'quest/quest')
    if path.suffix!='.quest' or not supported or not path.is_file() or any(p in ('object','pre_qc','_unused') for p in path.parts) or path.stat().st_size>1200000 or path.relative_to(studio.root).as_posix()!=ident:
        raise ValueError('Choose an existing quest from the quest library.')
    model=Model(studio,ident)
    doc,text=model.document(path)
    identity=quest_name(model.docs[doc])
    if not identity: raise ValueError('The source has no recognised quest identity.')
    if identity=='hunting':
        hunting(model)
    else:
        generic(model,doc,text)
        if re.fullmatch(r'(?:collect_quest|make_herb)_lv\d+',identity):
            biologist(model,doc,text,identity)
    model.notes.insert(0,'Only recognised literal values are exposed. State names, branching and dynamic expressions stay intact. Translated dialogue may contain fixed text that needs a separate text edit after changing objectives or rewards.')
    if not model.fields: model.notes.append('This quest has no values that the guided editor can safely expose. Use Advanced source for its custom logic.')
    # Hashes used for draft recovery reference original bytes in source_cache.
    for rel,raw in model.docs.items():
        studio.workspace.cache_source(rel,raw)
    return model


def plan(studio,body):
    model=analyse(studio,body['id'])
    expected=body.get('hashes',{})
    if expected!={rel:sha(raw) for rel,raw in model.docs.items()}:
        raise ValueError('Quest sources or a shared dependency changed. Reopen this quest before reviewing.')
    changes=body.get('values',{})
    fields={f['key']:f for f in model.fields}
    if not isinstance(changes,dict) or any(k not in fields for k in changes):
        raise ValueError('Unknown quest field. Reopen the guided editor.')
    patches={};settings={}
    for key,value in changes.items():
        f=fields[key];value=str(value)
        if value==f['value']: continue
        if f['disabled']: raise ValueError('This shared cooldown requires custom difficulty in World settings.')
        if f['kind'] in ('item','mob'):
            valid=value in (studio.items if f['kind']=='item' else studio.mobs) or value in f.get('choices',[])
            if not valid or value=='1' and f['kind']=='item': raise ValueError('Choose a known '+f['kind']+' from the catalog.')
            if f['kind']=='mob' and studio.mobs[value]['category']=='npc': raise ValueError('Choose a monster, boss or Metin kill target.')
        elif not re.fullmatch(r'\d+(?:\.\d+)?' if ':setting:' in key else r'\d+',value) or not f['min']<=float(value)<=f['max']:
            raise ValueError(f['label']+f" must be between {f['min']} and {f['max']}.")
        if ':setting:' in key:
            settings[key.rsplit(':',1)[1]]=value
        for e in f['edits']:
            out='"'+value+'"' if e.get('luaItem') and not value.isdigit() else value
            if e.get('delta'): out=str(int(value)+e['delta'])
            out=e.get('prefix','')+out
            patches.setdefault(f['document'],[]).append((e['start'],e['end'],out))
    result={}
    for rel,edits in patches.items():
        raw=model.docs[rel]
        previous=len(raw)+1
        for start,end,value in sorted(set(edits),reverse=True):
            if end>previous: raise ValueError('These fields overlap. Reopen the quest and edit one field at a time.')
            raw=raw[:start]+value.encode('ascii')+raw[end:];previous=start
        if raw!=model.docs[rel]: result[studio.root/rel]=raw
    if settings:
        setting_plan=studio.settings_plan({'hash':sha(model.docs[(studio.compose/'.env').relative_to(studio.root).as_posix()]),'values':settings})
        result.update({path:new for path,_,new in studio.plans.pop(setting_plan['id'])['files']})
    source=studio.root/model.ident
    if source in result:
        result.update(source_changes(studio,source,result[source]))
    guards = [(studio.root/rel,raw) for rel,raw in model.docs.items() if studio.root/rel not in result]
    return studio.plan('Update quest fields: '+quest_name(model.docs[model.ident]),result,
                       'Only selected values change. Shared reward helpers also affect companion rewards. Review every diff before saving. Apply builds/restarts the game; current character flags and previously granted rewards are not migrated.',
                       metadata={'guards':guards})
