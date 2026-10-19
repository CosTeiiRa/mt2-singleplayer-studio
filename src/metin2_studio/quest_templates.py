"""Templates use the quest API shipped by this installation; compilation remains mandatory."""
import base64
import json
import hashlib
import re


def metadata(body):
    allowed = {'id','title','intro','npc','target','reward','quantity','kills','level','yang','exp','template','cooldown','requiredItem','requiredCount','returnNpc'}
    clean = {key: value for key, value in body.items() if key in allowed}
    return '-- STUDIO-TEMPLATE ' + base64.b64encode(json.dumps(clean).encode()).decode() + '\n'


def template_values(raw):
    match = re.search(rb'(?m)^-- STUDIO-TEMPLATE ([A-Za-z0-9+/=]+)', raw)
    if match:
        try:
            value = json.loads(base64.b64decode(match[1]))
            return value if isinstance(value, dict) else None
        except (ValueError, TypeError):
            pass
    return None


def library(studio):
    result = []
    files = {file['id']: file for file in studio.inventory()}
    with studio.workspace.connect() as conn:
        staged = [row[0] for row in conn.execute("SELECT DISTINCT path FROM staged WHERE path LIKE '%.quest'")]
    for ident in staged:
        if ident not in files and studio.read(studio.root / ident) is not None:
            files[ident] = {'id': ident, 'name': (studio.root / ident).stem.replace('_', ' '), 'category': 'Custom quests', 'size': len(studio.read(studio.root / ident)), 'mode': 'Advanced text'}
    for file in files.values():
        if not file['id'].endswith('.quest'):
            continue
        raw = studio.read(studio.root / file['id'])
        if raw is None:
            continue
        values = template_values(raw)
        result.append({**file, 'hash': hashlib.sha256(raw).hexdigest(), 'template': values, 'title': str(values.get('title', file['name'])) if values else file['name']})
    from metin2_studio.quest_support import describe_library
    return describe_library(studio, result)


def generate(studio, body, validate):
    kind = body.get('template', 'hunt')
    cooldown = int(body.get('cooldown', 0))
    if not 0 <= cooldown <= 2592000:
        raise ValueError('Cooldown must be 0–2,592,000 seconds; 0 means once per character.')
    if kind not in ('hunt', 'collection', 'exchange'):
        raise ValueError('Choose Hunt, Collection / turn-in, or Exchange.')
    # All templates share validation, state names and the same player guidance.
    checked = dict(body)
    checked.setdefault('target', '8001')
    values = validate(checked)
    values.update(template=kind, cooldown=cooldown)
    if kind != 'hunt':
        item = str(body.get('requiredItem', ''))
        if item not in studio.items or item == '1':
            raise ValueError('Choose a required inventory item from the catalog.')
        count = int(body.get('requiredCount', 1))
        if not 1 <= count <= 200:
            raise ValueError('Turn-in quantity must be 1–200.')
        values.update(requiredItem=item, requiredCount=count)
    destination = str(body.get('returnNpc') or body.get('npc'))
    if destination not in studio.mobs or studio.mobs[destination]['category'] != 'npc':
        raise ValueError('Choose a return NPC from the catalog.')
    values['returnNpc'] = destination
    return values['id'], metadata(body) + render(values)


def render(values):
    """Use stock quest targets/letters; do not add states or reset player flags."""
    ident, npc, destination = (values[key] for key in ('id', 'npc', 'returnNpc'))
    title, intro = (json.dumps(values[key], ensure_ascii=True) for key in ('title', 'intro'))
    count, target, level = (values[key] for key in ('kills', 'target', 'level'))
    reward, qty, yang, exp = (values[key] for key in ('reward', 'quantity', 'yang', 'exp'))
    hunt, cooldown = values['template'] == 'hunt', values['cooldown']
    item, required = values.get('requiredItem'), values.get('requiredCount')
    objective = f'say("Defeat {count} x " .. mob_name({target}) .. ".")' if hunt else f'say("Bring {required} x " .. item_name({item}) .. ".")'
    progress = f'say("Target: " .. mob_name({target}))\n            say("Defeated: " .. pc.getqf("kills") .. " / {count}")' if hunt else f'{objective}\n            say("In your inventory: " .. pc.count_item({item}) .. " / {required}")'
    availability = f'pc.get_level() >= {level}'
    if cooldown:
        availability = 'get_time() >= pc.getqf("next_available") and ' + availability
    events = 'enter or login or levelup or letter' + (' or studio_available.timer' if cooldown else '')
    wait = f'''            if get_time() < pc.getqf("next_available") then
                timer("studio_available", pc.getqf("next_available") - get_time())
                return
            end
''' if cooldown else ''
    hunting = f'''    state hunting begin
        when enter or login or letter begin
            if pc.getqf("kills") >= {count} then
                set_state(reward)
                return
            end
            send_letter({title})
        end
        when button or info begin
            say_title({title})
            {progress}
            say("Then return to " .. mob_name({destination}) .. ".")
        end
        when {target}.kill begin
            local total = pc.getqf("kills") + 1
            pc.setqf("kills", total)
            if total >= {count} then
                set_state(reward)
            end
        end
    end
''' if hunt else ''
    turnin_guard = f'''            if pc.count_item({item}) < {required} then
                say_title({title})
                {objective}
                say("In your inventory: " .. pc.count_item({item}) .. " / {required}")
                return
            end
''' if not hunt else ''
    turnin = f'''            -- Inventory checked before the turn-in.
            local before_turnin = pc.count_item({item})
            pc.remove_item({item}, {required})
            local spent = before_turnin - pc.count_item({item})
            if spent > 0 then
                char_log(0, "STUDIO_Q_ITEM", "v1:OUT:{item}:" .. spent)
            end
''' if not hunt else ''
    finish = f'pc.setqf("next_available", get_time() + {cooldown})\n            set_state(start)' if cooldown else 'set_state(complete)'
    reward_progress = f'say("Completed: {count} x " .. mob_name({target}) .. ".")' if hunt else progress
    return f'''-- Created by Metin2 Server Studio. {'Repeatable with cooldown.' if cooldown else 'One completion per character.'}
-- Studio quest guidance v2: native NPC targets, named objectives and letters.
quest {ident} begin
    state start begin
        when {events} begin
            if pc.get_level() < {level} then
                return
            end
{wait}            send_letter({title})
            local v = find_npc_by_vnum({npc})
            if v != 0 then
                target.vid("__STUDIO_GIVER__", v, {title})
            end
        end
        when button or info with {availability} begin
            say_title({title})
            say("Speak with " .. mob_name({npc}) .. " to accept this quest.")
            {objective}
            say("Return to " .. mob_name({destination}) .. " when ready.")
        end
        when __STUDIO_GIVER__.target.click or {npc}.chat.{title} with {availability} begin
            say_title({title})
            say({intro})
            {objective}
            say("Return to " .. mob_name({destination}) .. " when ready.")
            say("Reward: {qty} x " .. item_name({reward}))
            say("{yang} Yang | {exp} EXP")
            if select("Accept", "Later") == 1 then
                target.delete("__STUDIO_GIVER__")
                clear_letter()
                pc.setqf("kills", 0)
                set_state({'hunting' if hunt else 'reward'})
            end
        end
    end
{hunting}    state reward begin
        when enter or login or letter begin
            send_letter("Return: " .. {title})
            local v = find_npc_by_vnum({destination})
            if v != 0 then
                target.vid("__STUDIO_RETURN__", v, "Return to " .. mob_name({destination}))
            end
        end
        when button or info begin
            say_title({title})
            {reward_progress}
            say("Speak with " .. mob_name({destination}) .. " to claim your reward.")
            say("Reward: {qty} x " .. item_name({reward}))
            say("{yang} Yang | {exp} EXP")
        end
        when __STUDIO_RETURN__.target.click or {destination}.chat."Claim your reward" begin
{turnin_guard}            if pc.get_empty_inventory_count() < 5 then
                say("Please free five inventory slots first.")
                return
            end
{turnin}            target.delete("__STUDIO_RETURN__")
            clear_letter()
            -- Move out of this state before granting a reward.
            {finish}
            local before_reward = pc.count_item({reward})
            pc.give_item2({reward}, {qty})
            local gained = pc.count_item({reward}) - before_reward
            if gained > 0 then
                char_log(0, "STUDIO_Q_ITEM", "v1:IN:{reward}:" .. gained)
            end
            pc.change_gold({yang})
            pc.give_exp2({exp})
            say_title({title})
            say("Thank you. Here is your reward!")
        end
    end
    state complete begin
        when enter or login begin
            target.delete("__STUDIO_GIVER__")
            target.delete("__STUDIO_RETURN__")
            clear_letter()
        end
    end
end
'''
