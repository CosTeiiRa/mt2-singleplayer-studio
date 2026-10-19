"""Configured item effects; no inventory rolls or game data are modified."""
import ast
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
import re
import subprocess

GRADES = ('GRADE_NORMAL','GRADE_BRILLIANT','GRADE_RARE','GRADE_ANCIENT','GRADE_LEGENDARY','GRADE_MYTH')
STEPS = ('STEP_LOWEST','STEP_LOW','STEP_MID','STEP_HIGH','STEP_HIGHEST')


def literal_mapping(path, name):
    try:
        tree = ast.parse(Path(path).read_text('utf-8-sig', errors='replace'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                result = ast.literal_eval(node.value)
                if isinstance(result, dict):
                    return result
    except (OSError, SyntaxError, ValueError, TypeError):
        pass
    return {}


def bonus_metadata(root):
    root = Path(root)
    try:
        engine = (root / 'linux-port/docker/ENGINE').read_text('utf-8').strip()
    except OSError:
        engine = ''
    texts = literal_mapping(root / 'files/admin_panel.py', 'APPLY_TEXTS')
    points = literal_mapping(root / 'linux-port/docker/seban-panel/app.py', 'POINT_TO_APPLY')
    return {'engine':engine, 'points':{str(key):value for key,value in points.items() if isinstance(key,int) and isinstance(value,int)},
            'formats':{str(key):{'kind':value[0], 'template':value[1]['en'][:400]} for key,value in texts.items()
                       if isinstance(key,int) and isinstance(value,(list,tuple)) and len(value)==2 and isinstance(value[1],dict) and isinstance(value[1].get('en'),str)}}


def parse_dragon_table(raw):
    """Parse group rows and column headers as data, never shell/Lua/Python."""
    if len(raw) > 256 * 1024:
        raise ValueError('Dragon Stone table exceeds the supported size')
    root = {'groups':{},'rows':{},'columns':[]}; stack = [root]; pending = None
    for line in raw.decode('utf-8', errors='replace').splitlines():
        line = line.strip()
        if line.startswith('#--#'):
            stack[-1]['columns'] = line.split()[1:]; continue
        line = line.split('#',1)[0].split('//',1)[0].strip()
        if not line:
            continue
        cells = line.split()
        if len(cells)==2 and cells[0].lower()=='group':
            pending = cells[1]
        elif line == '{':
            if pending is None or len(stack)>12:
                raise ValueError('Unsupported Dragon Stone group')
            group = {'groups':{},'rows':{},'columns':[]}
            stack[-1]['groups'][pending] = group; stack.append(group); pending = None
        elif line == '}':
            if len(stack)==1:
                raise ValueError('Unbalanced Dragon Stone table')
            stack.pop()
        else:
            stack[-1]['rows'][cells[0]] = cells[1:]
    if len(stack)!=1 or not all(name in root['groups'] for name in ('VnumMapper','BasicApplys','WeightTables','ApplyNumSettings')):
        raise ValueError('Incomplete Dragon Stone table')
    return root


def deployed_dragon_table(compose):
    result = subprocess.run(['docker','compose','exec','-T','game','cat','/opt/metin2/share/locale/poland/dragon_soul_table.txt'],
                            cwd=compose, capture_output=True, timeout=5,
                            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise ValueError('The deployed Dragon Stone table is unavailable')
    return parse_dragon_table(result.stdout)


def bonus_text(code, value, metadata, points=False):
    code = str(code)
    apply = str(metadata.get('points',{}).get(code,code)) if points else code
    entry = metadata.get('formats',{}).get(apply,{})
    try:
        return entry['template'] % int(value)
    except (KeyError, ValueError, TypeError):
        return f'Attribute #{code}: {int(value):+d}'


def group_values(title, values, note=''):
    return {'title':title,'values':values,'note':note}


def dragon_effects(item, table, metadata, terms):
    if not table:
        return [], [['Dragon Stone effects','No deployed balance snapshot available']], 'Start the world and refresh the catalogue to read its Dragon Stone balance.'
    try:
        ident = int(item['id']); family_id = ident//10000
        grade, step, strength = (ident//1000)%10, (ident//100)%10, (ident//10)%10
        family = next(cells[0] for cells in table['groups']['VnumMapper']['rows'].values() if int(cells[1])==family_id)
        def group(name):
            groups = table['groups'][name]['groups']
            return groups.get(family) or groups['Default']
        weights = group('WeightTables')['groups'][GRADES[grade]]['rows'][STEPS[step]]
        weight = Decimal(weights[strength])
        if weight<=0:
            raise ValueError('No active weight')
        settings = group('ApplyNumSettings')
        count_index = settings['columns'].index(GRADES[grade])
        fixed = int(settings['rows']['basis'][count_index])
        low, high = (int(settings['rows'][name][count_index]) for name in ('add_min','add_max'))
        point_mode = metadata.get('engine','').startswith('mt2009')
        def apply_rows(name, limit=None):
            rows = list(group(name)['rows'].values())
            values = []
            for row in rows[:limit]:
                value = int((Decimal(row[1])*weight/100).to_integral_value(rounding=ROUND_CEILING))
                values.append(bonus_text(row[0],value,metadata,points=point_mode))
            return values
        groups = [group_values('Calculated base effects',apply_rows('BasicApplys',fixed))]
        if high:
            groups.append(group_values('Possible bonus rolls',apply_rows('AdditionalApplys'),f'{low}–{high} additional bonuses; these are alternatives, not guaranteed together.'))
        quality = terms.get('DRAGON_SOUL_STEP_LEVEL'+str(step+1)) or 'Quality '+str(step+1)
        quality = re.sub(r'^Clarity:\s*','',quality,flags=re.I).rstrip(',; ').capitalize()
        facts = [['Quality / strength',quality+' · +'+str(strength)],['Bonus scaling',format(weight.normalize(),'f')+'%'],['Additional bonuses',str(low) if low==high else f'{low}–{high}']]
        return groups, facts, 'Calculated from the last successfully read deployed game table, rounded up to whole points. A particular stone’s rolled bonuses can differ.'
    except (KeyError, IndexError, ValueError, TypeError, StopIteration, ArithmeticError):
        return [], [['Dragon Stone effects','This variant has no supported balance entry']], 'No bonus values are guessed for an unsupported class, quality or strength.'


def enrich_description(item, row, metadata, dragon_table=None, terms=None):
    detail = item['description']; groups = []
    if not row or len(row)<36:
        return
    typ = int(row[3])
    if typ == 29:
        groups, facts, note = dragon_effects(item,dragon_table,metadata,terms or {})
        detail['facts'] = facts + detail['facts']; detail['note'] = note
        if groups: detail['source'] = 'configured'
    else:
        if typ == 1:
            values = list(map(int,row[30:36])); extra = values[5]
            attacks = [f'Attack value: {values[3]+extra}–{values[4]+extra}']
            if values[1] or values[2]:
                attacks.append(f'Magic attack value: {values[1]+extra}–{values[2]+extra}')
            groups.append(group_values('Weapon values',attacks))
        elif typ == 2:
            values = list(map(int,row[30:36])); armour = []
            if values[1]: armour.append(f'Defence: {values[1]+2*values[5]}')
            if values[0]: armour.append(f'Magic defence: {values[0]}')
            if armour: groups.append(group_values('Armour values',armour))
        applies = [bonus_text(row[index],row[index+1],metadata,points=metadata.get('engine','').startswith('mt2009'))
                   for index in (24,26,28) if int(row[index]) and int(row[index+1])]
        if applies:
            groups.append(group_values('Fixed item bonuses',applies))
        elif typ == 0:
            detail['note'] = 'No effect values are exposed by this server definition. Scripts or engine rules may still give the item a use.'
    detail['effects'] = groups
