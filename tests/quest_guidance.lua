-- Executes qc's actual output against a small quest-API test double.
-- Run in the disposable Lua QA image, never inside the running game.
local root, id, kind, cooldown = arg[1], arg[2], arg[3], tonumber(arg[4])
local S = {state='start', level=4, flags={}, items={}, markers={}, text={}, letters={},
           now=1000, choice=1, empty=5, gold=0, exp=0, logs={}}
local function check(ok, message) assert(ok, id .. ': ' .. message) end
local function read(path)
    local file=io.open(root .. '/' .. path, 'r')
    if not file then return nil end
    local text=file:read('*a'); file:close(); return text
end
local function contains(text)
    return string.find(table.concat(S.text, '\n'), text, 1, true) ~= nil
end
function say(text) table.insert(S.text, text) end
function say_title(text) table.insert(S.text, text) end
function send_letter(text) S.letters={text} end
function clear_letter() S.letters={} end
function get_time() return S.now end
function select() return S.choice end
function timer(name, wait) S.timer={name=name, wait=wait} end
function find_npc_by_vnum(vnum) return vnum+100000 end
function mob_name(vnum)
    return ({[101]='Wild Dog',[9001]='Weapon Shop Dealer',[9002]='Armour Shop Dealer'})[vnum] or 'Unknown mob'
end
function item_name(vnum) return vnum==71084 and 'Enchant Item' or 'Required material' end
function char_log(_, kind, value) table.insert(S.logs, kind .. ':' .. value) end
target={
    vid=function(name, vid, label) S.markers[name]={vid=vid,label=label} end,
    delete=function(name) S.markers[name]=nil end
}
pc={
    get_level=function() return S.level end,
    getqf=function(key) return S.flags[key] or 0 end,
    setqf=function(key,value) S.flags[key]=value end,
    count_item=function(id) return S.items[id] or 0 end,
    get_empty_inventory_count=function() return S.empty end,
    remove_item=function(id,count) S.items[id]=(S.items[id] or 0)-count end,
    give_item2=function(id,count) S.items[id]=(S.items[id] or 0)+count end,
    change_gold=function(value) S.gold=S.gold+value end,
    give_exp2=function(value) S.exp=S.exp+value end
}
local run
function set_state(state)
    S.state=state
    -- The game dispatches enter when a quest changes state.
    S.pending=state
end
run=function(path, conditional)
    if conditional then
        local when=read(path .. '.when')
        if when and #when>0 then
            local expression=assert(loadstring(when))
            if not expression() then return false end
        end
        path=path .. '.script'
    end
    local code=read(path)
    if not code then return false end
    assert(loadstring(code, path))()
    if S.pending then
        local state=S.pending; S.pending=nil
        run('notarget/enter/' .. id .. '.' .. state)
    end
    return true
end
local function event(event, state) return run('notarget/' .. event .. '/' .. id .. '.' .. (state or S.state)) end
local function offer() return run('9001/chat/' .. id .. '.start.0', true) end
local function claim() return run('9002/chat/' .. id .. '.reward.0', true) end

event('login')
check(next(S.markers)==nil and #S.letters==0, 'under-level character gets no quest indicator')
S.level=5; event('levelup')
check(S.markers.__STUDIO_GIVER__.vid==109001, 'available marker belongs to quest giver')
check(S.letters[1]=='Guidance test', 'available quest has a letter')
S.text={}; event('button')
check(contains('Weapon Shop Dealer'), 'available letter names the giver')
check(contains(kind=='hunt' and 'Wild Dog' or 'Required material'), 'available letter names the objective')

S.choice=2; S.flags.kills=7; offer()
check(S.state=='start' and S.flags.kills==7 and S.markers.__STUDIO_GIVER__, 'decline preserves marker and progress')
S.choice=1; run('notarget/target/' .. id .. '.start.0', true)
check(S.markers.__STUDIO_GIVER__==nil, 'accept removes available marker')
if kind=='hunt' then
    check(S.state=='hunting' and S.flags.kills==0, 'hunt starts after accepting')
    S.text={}; event('button')
    check(contains('Wild Dog') and contains('0 / 1'), 'hunt letter names target and progress')
    check(not run('102/kill/' .. id .. '.hunting'), 'unrelated monster has no kill handler')
    run('101/kill/' .. id .. '.hunting')
    check(S.state=='reward' and S.flags.kills==1, 'required target completes objective')
else
    check(S.state=='reward', 'turn-in enters inventory objective')
    S.items[30001]=2; claim()
    check(S.state=='reward' and S.items[30001]==2 and not S.items[71084], 'missing items cannot grant a reward')
    S.items[30001]=3
end
check(S.markers.__STUDIO_RETURN__.vid==109002, 'return marker uses separate return NPC')
check(string.find(S.letters[1], 'Return:', 1, true), 'completion/turn-in has a return letter')
S.text={}; event('info')
check(contains('Armour Shop Dealer') and contains('Enchant Item'), 'return letter names destination and reward')

S.empty=4; claim()
check(S.state=='reward' and S.markers.__STUDIO_RETURN__ and not S.items[71084], 'full inventory retains return marker and reward state')
S.empty=5; run('notarget/target/' .. id .. '.reward.0', true)
check(S.items[71084]==1 and S.gold==100 and S.exp==20, 'reward granted once with configured amounts')
check(S.markers.__STUDIO_RETURN__==nil and #S.letters==0, 'hand-in removes its marker and letter')
if kind~='hunt' then check(S.items[30001]==0, 'turn-in consumes exact quantity') end
if cooldown>0 then
    check(S.state=='start' and S.flags.next_available==1060, 'repeat preserves availability timestamp')
    check(S.timer.name=='studio_available' and S.timer.wait==60, 'availability timer scheduled')
    check(not offer(), 'cooldown prevents accepting early')
    S.now=1060
    run('studio_available/timer/' .. id .. '.start')
    check(S.markers.__STUDIO_GIVER__ and #S.letters==1, 'marker returns when cooldown expires')
else
    check(S.state=='complete', 'one-time quest retains completed state')
    event('login')
    check(next(S.markers)==nil and #S.letters==0, 'completed character gets no new quest marker')
end
print('PASS ' .. id .. ': eligibility, objective text, marker lifecycle, hand-in, progress and cooldown')
