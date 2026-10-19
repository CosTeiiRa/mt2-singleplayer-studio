"""Read-only economy observations. Persistent history belongs to Studio, not the game."""
from collections import Counter, defaultdict
from contextlib import contextmanager
import json
import math
import re
import sqlite3
import statistics
import subprocess
import threading
import time


POPULATIONS = ('regular', 'all', 'human', 'bot', 'gm', 'unknown')
STAGES = ('all', 'early', 'mid', 'late')
CAP = 20000


def options(values):
    result = {'population': str(values.get('population', 'regular')), 'stage': str(values.get('stage', 'all')), 'classification': 2}
    if result['population'] not in POPULATIONS or result['stage'] not in STAGES:
        raise ValueError('Unknown economy filter.')
    for key, default, allowed in (('days', 7, (1, 7, 28)), ('early', 39, range(1, 119)), ('mid', 74, range(2, 121))):
        try:
            result[key] = int(values.get(key, default))
        except (ValueError, TypeError):
            raise ValueError('Invalid economy period or stage boundary.') from None
        if result[key] not in allowed:
            raise ValueError('Invalid economy period or stage boundary.')
    if result['early'] >= result['mid']:
        raise ValueError('The early stage must end before the middle stage.')
    return result


def stage(level, config):
    return 'early' if level <= config['early'] else 'mid' if level <= config['mid'] else 'late'


def median(values):
    return statistics.median(values) if values else None


def change(current, previous):
    return (current / previous - 1) * 100 if previous else None


def comparable(item):
    return bool(set(item.get('catalogGroups', [])) & {'materials', 'potions', 'bonus', 'scrolls'}) and item.get('catalogKind') != 'blend'


def price_change(current, previous, catalog):
    """Matched, exact-ID commodity trades; never mix differently rolled equipment."""
    ratios = []
    for ident in current.keys() & previous.keys():
        item = catalog.get(str(ident), {})
        if not comparable(item):
            continue
        a, b = current[ident], previous[ident]
        if len(a) >= 5 and len(b) >= 5 and median(b) > 0:
            ratios.append(median(a) / median(b))
    return {'percent': (math.exp(sum(math.log(r) for r in ratios) / len(ratios)) - 1) * 100 if len(ratios) >= 3 else None,
            'matched': len(ratios), 'minimumSales': 5}


class Economy:
    def __init__(self, studio):
        self.studio = studio
        self.lock = threading.RLock()
        self.cached = None
        self.cache_time = 0
        self.db = studio.state / 'economy.sqlite'
        from metin2_studio.economy_tools import EconomyTools
        self.tools = EconomyTools(self) if hasattr(studio, 'workspace') else None

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db, timeout=10)
        try:
            conn.execute('CREATE TABLE IF NOT EXISTS snapshots (id INTEGER PRIMARY KEY, at REAL NOT NULL, scope TEXT NOT NULL, payload TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, at REAL NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL)')
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def query(self, statements):
        # The password is expanded inside the existing container and never appears
        # in command arguments, returned output, browser responses or Studio files.
        sql = "SET SESSION max_statement_time=8; SET time_zone='+00:00'; SET TRANSACTION READ ONLY; START TRANSACTION WITH CONSISTENT SNAPSHOT;\n"
        sql += '\n'.join(statements) + '\nROLLBACK;'
        try:
            run = subprocess.run(['docker', 'compose', 'exec', '-T', 'mariadb', 'sh', '-c',
                                  'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb -uroot --default-character-set=utf8mb4 -N -B --raw'],
                                 input=sql, cwd=self.studio.compose, capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=45,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError('The local database is unavailable or took too long. Start the world in its launcher, then refresh.') from None
        if run.returncode:
            diagnostic = (run.stderr or '').lower()
            if any(reason in diagnostic for reason in ('dockerdesktoplinuxengine', 'daemon is running', 'cannot connect to the docker daemon', 'failed to connect to the docker api')):
                raise ValueError('Docker’s engine is stopped or unreachable. Open Docker Desktop, start your world in the game launcher, then click Refresh. Studio does not start or restart the game automatically.')
            if 'not running' in diagnostic or 'no container found' in diagnostic:
                raise ValueError('The world database is stopped. Start your world in the game launcher, then click Refresh.')
            raise ValueError('The read-only database query could not complete. The database may be stopped or its schema may differ.')
        result = defaultdict(list)
        for line in run.stdout.splitlines():
            try:
                record = json.loads(line)
                result[record['set']].append(record['row'])
            except (ValueError, KeyError, TypeError):
                raise ValueError('The database returned an unsupported economy response.') from None
        return dict(result)

    def collect(self, days, fresh=False):
        with self.lock:
            if not fresh and self.cached is not None and self.cached['days'] == days and time.time() - self.cache_time < 60:
                return self.cached
            schema_rows = self.query(["SELECT JSON_OBJECT('set','schema','row',JSON_ARRAY(TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME)) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA IN ('player','log','account','common') AND TABLE_NAME IN ('player','item','account','gmlist','safebox','ikashop_safebox','ikashop_offlineshop','ikarusshop_log','refinelog','money_log','log');"])
            schema = defaultdict(set)
            for db, table, column in schema_rows.get('schema', []):
                schema[db + '.' + table].add(column)
            queries, missing = [], []

            def add(key, required, fields, tail):
                if any(not set(columns.split()) <= schema[table] for table, columns in required.items()):
                    missing.append(key)
                    return
                queries.append(f"SELECT JSON_OBJECT('set','{key}','row',JSON_ARRAY({fields})) {tail};")

            gm_known = 'mName' in schema['common.gmlist'] and {'account_id', 'name'} <= schema['player.player']

            def gm_join(account='a.id', alias='ga'):
                if not gm_known:
                    return ''
                return f' LEFT JOIN (SELECT DISTINCT gp.account_id FROM player.player gp JOIN common.gmlist g ON g.mName=gp.name) {alias} ON {alias}.account_id={account} '

            gm_test = 'ga.account_id IS NOT NULL' if gm_known else 'FALSE'
            # Classify accounts consistently, including storage and legacy bots.
            cohort = f"CASE WHEN {gm_test} THEN 'gm' WHEN a.id IS NULL THEN 'unknown' WHEN LEFT(a.login,10)='playerbot_' OR EXISTS (SELECT 1 FROM player.player lp WHERE lp.account_id=a.id AND lp.name LIKE 'bot%') THEN 'bot' ELSE 'human' END"
            joined = 'LEFT JOIN player.player p ON p.id={pid} LEFT JOIN account.account a ON a.id=p.account_id' + gm_join()
            identity = {'player.player': 'id account_id name level gold playtime last_play cheque', 'account.account': 'id login'}
            add('players', identity, f"p.id,p.account_id,p.level,{cohort},p.gold,p.cheque,p.playtime,UNIX_TIMESTAMP(p.last_play)", 'FROM player.player p LEFT JOIN account.account a ON a.id=p.account_id' + gm_join())
            add('stock', {**identity, 'player.item': 'owner_id window count vnum', 'player.ikashop_offlineshop': 'owner duration'},
                f"i.vnum,COALESCE(p.level,0),{cohort},SUM(i.count),COUNT(*),SUM(IF(i.window='EQUIPMENT',i.count,0)),SUM(IF(i.window='IKASHOP_OFFLINESHOP' AND sh.duration>0,i.count,0))",
                "FROM player.item i " + joined.format(pid="IF(i.window IN ('SAFEBOX','MALL'),NULL,i.owner_id)").replace('a.id=p.account_id', "a.id=IF(i.window IN ('SAFEBOX','MALL'),i.owner_id,p.account_id)") + " LEFT JOIN player.ikashop_offlineshop sh ON sh.owner=i.owner_id GROUP BY i.vnum,COALESCE(p.level,0)," + cohort)
            add('owners', {**identity, 'player.item': 'owner_id window count vnum'},
                f"i.vnum,COALESCE(p.level,0),{cohort},a.id,SUM(i.count)",
                "FROM player.item i " + joined.format(pid="IF(i.window IN ('SAFEBOX','MALL'),NULL,i.owner_id)").replace('a.id=p.account_id', "a.id=IF(i.window IN ('SAFEBOX','MALL'),i.owner_id,p.account_id)") + " WHERE a.id IS NOT NULL GROUP BY i.vnum,COALESCE(p.level,0)," + cohort + ",a.id LIMIT 50001")
            add('scriptFlows', {**identity, 'log.log': 'who time how hint'},
                f"CAST(l.hint AS CHAR),COALESCE(p.level,0),{cohort},COUNT(*)",
                'FROM log.log l ' + joined.format(pid='l.who') + f" WHERE l.time>=UTC_TIMESTAMP()-INTERVAL {days} DAY AND l.how='STUDIO_Q_ITEM' GROUP BY l.hint,COALESCE(p.level,0),{cohort}")
            for coverage_key, coverage_table in [('itemLog', 'log.log'), ('tradeLog', 'log.ikarusshop_log'), ('refineLog', 'log.refinelog'), ('moneyLog', 'log.money_log')]:
                add('coverage_' + coverage_key, {coverage_table: 'time'}, 'UNIX_TIMESTAMP(MIN(time)),UNIX_TIMESTAMP(MAX(time)),COUNT(*)', 'FROM ' + coverage_table)
            horizon = int(days) * 2
            add('sales', {**identity, 'log.ikarusshop_log': 'id time what who shop_owner vnum count yang cheque'},
                f"UNIX_TIMESTAMP(l.time),l.vnum,l.count,l.yang,l.cheque,l.who,l.shop_owner,COALESCE(p.level,0),{cohort}," + ('bga.account_id IS NOT NULL' if gm_known else 'FALSE') + ',COALESCE(bp.level,0)',
                'FROM log.ikarusshop_log l ' + joined.format(pid='l.shop_owner') + ' LEFT JOIN player.player bp ON bp.id=l.who ' + gm_join('bp.account_id', 'bga') + f" WHERE l.what='BUY_ITEM' AND l.time>=UTC_TIMESTAMP()-INTERVAL {horizon} DAY ORDER BY l.id DESC LIMIT {CAP + 1}")
            add('refines', {**identity, 'log.refinelog': 'pid time is_success setType'},
                f"DATE(r.time),COALESCE(p.level,0),{cohort},r.is_success,COALESCE(r.setType,''),COUNT(*)",
                'FROM log.refinelog r ' + joined.format(pid='r.pid') + f" WHERE r.time>=UTC_TIMESTAMP()-INTERVAL {days} DAY AND r.is_success IN (0,1) GROUP BY DATE(r.time),COALESCE(p.level,0),{cohort},r.is_success,r.setType")
            add('refineSteps', {**identity, 'log.refinelog': 'pid time item_name step is_success setType'},
                f"CONVERT(r.item_name USING utf8mb4) COLLATE utf8mb4_general_ci,CONVERT(r.step USING utf8mb4) COLLATE utf8mb4_general_ci,COALESCE(p.level,0),{cohort},r.is_success,CONVERT(COALESCE(r.setType,'') USING utf8mb4) COLLATE utf8mb4_general_ci,COUNT(*)",
                'FROM log.refinelog r ' + joined.format(pid='r.pid') + f" WHERE r.time>=UTC_TIMESTAMP()-INTERVAL {days} DAY AND r.is_success IN (0,1) GROUP BY r.item_name,r.step,COALESCE(p.level,0),{cohort},r.is_success,r.setType")
            add('money', {'log.money_log': 'time type gold'},
                "DATE(time),type,SUM(IF(gold>0,gold,0)),SUM(IF(gold<0,-gold,0)),COUNT(*)",
                f'FROM log.money_log WHERE time>=UTC_TIMESTAMP()-INTERVAL {days} DAY GROUP BY DATE(time),type')
            hows = "'GET','USE_ITEM','PLAYERBOT_SHOP_SELL','REMOVE (REFINE FAIL)','REMOVE (REFINE SUCCESS)','STONE_KILL','BOSS_KILL','READ_SUCCESS','READ_FAIL','PLAYERBOT_MATERIAL_EXCHANGE_IN','PLAYERBOT_FISH_EXCHANGE_IN'"
            target = "IF(l.how IN ('STONE_KILL','BOSS_KILL'),l.what,COALESCE(l.vnum,0))"
            add('actions', {**identity, 'log.log': 'who time how what vnum'},
                f"CAST(l.how AS CHAR),{target},COALESCE(p.level,0),{cohort},COUNT(*)",
                'FROM log.log l ' + joined.format(pid='l.who') + f" WHERE l.time>=UTC_TIMESTAMP()-INTERVAL {days} DAY AND l.how IN ({hows}) GROUP BY l.how,{target},COALESCE(p.level,0),{cohort}")
            add('active', {**identity, 'log.log': 'who time type'}, f"p.account_id,p.level,{cohort}",
                'FROM log.log l ' + joined.format(pid='l.who') + f" WHERE p.id IS NOT NULL AND l.type IN ('CHARACTER','ITEM') AND l.time>=UTC_TIMESTAMP()-INTERVAL {days} DAY GROUP BY p.account_id,p.level,{cohort}")
            # Banks share the account classification but have no stage attribution.
            add('banks', {**identity, 'player.safebox': 'account_id gold'}, f"'Account safebox Yang',COALESCE(SUM(s.gold),0),0,{cohort}",
                'FROM player.safebox s LEFT JOIN account.account a ON a.id=s.account_id ' + gm_join() + f' GROUP BY {cohort}')
            add('shopbanks', {**identity, 'player.ikashop_safebox': 'owner gold cheque'}, f"'Shop safebox Yang',COALESCE(SUM(s.gold),0),COALESCE(SUM(s.cheque),0),{cohort}",
                'FROM player.ikashop_safebox s ' + joined.format(pid='s.owner') + f' GROUP BY {cohort}')
            raw = self.query(queries) if queries else {}
            raw.update(days=days, at=time.time(), available=[query.split("'set','", 1)[1].split("'", 1)[0] for query in queries], missing=missing, gmSeparated=gm_known)
            raw['ownersTruncated'] = len(raw.get('owners', [])) > 50000
            raw['owners'] = raw.get('owners', [])[:50000]
            raw['truncated'] = len(raw.get('sales', [])) > CAP
            raw['sales'] = raw.get('sales', [])[:CAP]
            self.cached, self.cache_time = raw, time.time()
            return raw

    def report(self, values, fresh=False):
        config = options(values)
        try:
            raw = self.collect(config['days'], fresh)
            data = analyse(raw, config, self.studio.items)
            data['connected'] = True
        except ValueError as error:
            data = analyse({'at': time.time(), 'available': [], 'missing': [], 'days': config['days']}, config, self.studio.items)
            data.update(connected=False, error=str(error))
        with self.connect() as conn:
            scope = json.dumps(config, sort_keys=True)
            history = conn.execute('SELECT at,payload FROM snapshots WHERE scope=? ORDER BY at DESC LIMIT 90', (scope,)).fetchall()
            legacy_config = {key: value for key, value in config.items() if key != 'classification'}
            if legacy_config['population'] == 'regular':
                legacy_config['population'] = 'all'
            legacy = conn.execute('SELECT at,payload FROM snapshots WHERE scope=? ORDER BY at DESC LIMIT 90', (json.dumps(legacy_config, sort_keys=True),)).fetchall() if config['population'] != 'gm' else []
            notes = conn.execute('SELECT id,at,title,body FROM notes ORDER BY at DESC LIMIT 50').fetchall()
        data['history'] = [{'at': at, 'wallet': json.loads(payload)['metrics']['wallet']} for at, payload in reversed(history)]
        data['lastSaved'] = None
        if history:
            at, payload = history[0]
            saved = json.loads(payload)
            data['lastSaved'] = {'at': at, 'filters': config, 'metrics': saved.get('metrics', {}),
                                 'available': saved.get('available', []), 'bands': saved.get('bands', []),
                                 'items': [{**row, 'name': self.studio.items.get(str(row['id']), {}).get('name', '#' + str(row['id']))}
                                           for row in saved.get('items', [])]}
        data['legacyHistory'] = [{'at': at, 'wallet': json.loads(payload)['metrics']['wallet']} for at, payload in reversed(legacy)]
        baseline = next(((at, json.loads(payload)) for at, payload in reversed(history) if data['at'] - at >= 60), None)
        data['baseline'] = {'at': baseline[0], 'walletChange': change(data['metrics']['wallet'], baseline[1]['metrics']['wallet'])} if baseline and data['metrics']['wallet'] is not None else None
        if baseline and data['metrics']['stock'] is not None and baseline[1]['metrics']['stock'] is not None:
            previous = {row['id']: row['stock'] for row in baseline[1]['items']}
            current_ids = {row['id'] for row in data['items']}
            for ident in previous.keys() - current_ids:
                entry = self.studio.items.get(ident, {})
                data['items'].append({'id': ident, 'name': entry.get('name', '#' + ident), 'category': entry.get('catalogGroups', ['other'])[0],
                                      'stock': 0, 'equipped': 0, 'listed': 0, 'sales': 0, 'unitsSold': 0, 'turnover': 0,
                                      'acquisitions': 0, 'uses': 0, 'npcSales': 0, 'burns': 0, 'stockChange': None,
                                      'unitPrice': None, 'priceChange': None, 'owners': None, 'topOwnerShare': None, 'scriptIn': 0 if 'scriptFlows' in data['available'] else None, 'scriptOut': 0 if 'scriptFlows' in data['available'] else None})
                grade = re.search(r'\+(\d+)$', entry.get('name', ''))
                data['items'][-1]['grade'] = int(grade[1]) if grade and 'equipment' in entry.get('catalogGroups', []) else None
            for row in data['items']:
                if row['stock'] is not None and previous.get(row['id'], 0) is not None:
                    row['stockChange'] = row['stock'] - previous.get(row['id'], 0)
        data['notes'] = [dict(zip(('id', 'at', 'title', 'body'), row)) for row in notes]
        data['sources'] = configured_sources(self.studio)
        return self.tools.augment(data) if self.tools else data

    def capture(self, values):
        with self.lock:
            data = self.report(values, fresh=True)
            if not data['connected']:
                raise ValueError(data['error'])
            # Keep aggregate counts only: no character/account IDs or credentials.
            from metin2_studio.economy_tools import EconomyTools
            payload = EconomyTools.aggregate(data)
            with self.connect() as conn:
                conn.execute('INSERT INTO snapshots(at,scope,payload) VALUES (?,?,?)', (data['at'], json.dumps(data['filters'], sort_keys=True), json.dumps(payload)))
            return self.report(values)

    def export(self, values):
        """Export the selected report plus all matching saved history, without capturing."""
        data = self.report(values)
        scope = json.dumps(data['filters'], sort_keys=True)
        legacy = {key: value for key, value in data['filters'].items() if key != 'classification'}
        if legacy['population'] == 'regular':
            legacy['population'] = 'all'
        with self.connect() as conn:
            snapshots = conn.execute('SELECT id,at,scope,payload FROM snapshots WHERE scope=? ORDER BY at,id', (scope,)).fetchall()
            earlier = conn.execute('SELECT id,at,scope,payload FROM snapshots WHERE scope=? ORDER BY at,id', (json.dumps(legacy, sort_keys=True),)).fetchall() if data['filters']['population'] != 'gm' else []
            notes = conn.execute('SELECT id,at,title,body FROM notes ORDER BY at,id').fetchall()
        def unpack(rows):
            return [{'id': ident, 'at': at, 'filters': json.loads(saved_scope), **json.loads(payload)} for ident, at, saved_scope, payload in rows]
        data['snapshots'] = unpack(snapshots)
        data['legacySnapshots'] = unpack(earlier)
        data['notes'] = [dict(zip(('id', 'at', 'title', 'body'), row)) for row in notes]
        data['export'] = {'version': 1, 'at': time.time(), 'history': 'All saved snapshots matching the selected filters. Earlier mixed definitions are kept separately. Journal includes all saved notes, across filters.',
                          'observation': 'Latest available observation (up to 60 seconds cached); exporting does not save a snapshot.',
                          'missingValues': 'JSON null and blank CSV measurements mean unavailable or insufficient data, not zero.'}
        return data

    def note(self, values):
        title, body = str(values.get('title', '')).strip(), str(values.get('body', '')).strip()
        if not title or len(title) > 120 or len(body) > 1500:
            raise ValueError('Enter a title up to 120 characters and a note up to 1500 characters.')
        with self.lock, self.connect() as conn:
            conn.execute('INSERT INTO notes(at,title,body) VALUES (?,?,?)', (time.time(), title, body))
        return {'saved': True}


def analyse(raw, config, catalog):
    now, days = raw['at'], config['days']
    cutoff = now - days * 86400
    available = set(raw.get('available', []))
    if available and not raw.get('gmSeparated') and config['population'] != 'all':
        raise ValueError('GM classification is unavailable. Choose Everyone (including GMs) for unseparated data.')

    def matches(level, population, selected=True):
        population_match = population in ('human', 'bot') if config['population'] == 'regular' else config['population'] == 'all' or config['population'] == population
        return population_match and (not selected or config['stage'] == 'all' or (level > 0 and stage(level, config) == config['stage']))

    def sale_identity(sale):
        if config['population'] == 'gm' and sale[8] != 'gm' and len(sale) > 9 and sale[9]:
            return sale[10] if len(sale) > 10 else 0, 'gm'
        return sale[7], sale[8]

    def sale_matches(sale, selected=True):
        gm_trade = sale[8] == 'gm' or (len(sale) > 9 and sale[9])
        if config['population'] not in ('all', 'gm') and gm_trade:
            return False
        return matches(*sale_identity(sale), selected)

    players = [row for row in raw.get('players', []) if matches(row[2], row[3])]
    accounts = defaultdict(int)
    for row in players:
        accounts[row[1]] += row[4]
    wealth = sorted(accounts.values(), reverse=True)
    wallet = sum(wealth)
    metrics = {'wallet': wallet if 'players' in available else None,
               'accounts': len(accounts) if 'players' in available else None,
               'activeAccounts': len({row[0] for row in raw.get('active', []) if matches(row[1], row[2])}) if 'active' in available else None,
               'medianWallet': median(wealth), 'top10Share': sum(wealth[:max(1, math.ceil(len(wealth) * .1))]) / wallet * 100 if wallet else None,
               'won': sum(row[5] for row in players) if 'players' in available else None}
    items = {}

    def item(ident):
        ident = str(ident)
        if ident not in items:
            entry = catalog.get(ident, {})
            items[ident] = {'id': ident, 'name': entry.get('name', '#' + ident), 'category': entry.get('catalogGroups', ['other'])[0],
                            'stock': 0 if 'stock' in available else None, 'equipped': 0, 'listed': 0, 'sales': 0, 'unitsSold': 0,
                            'turnover': 0, 'acquisitions': 0, 'uses': 0, 'npcSales': 0, 'burns': 0, 'stockChange': None,
                            'unitPrice': None, 'priceChange': None, 'owners': None, 'topOwnerShare': None, 'scriptIn': 0 if 'scriptFlows' in available else None, 'scriptOut': 0 if 'scriptFlows' in available else None}
            grade = re.search(r'\+(\d+)$', entry.get('name', ''))
            items[ident]['grade'] = int(grade[1]) if grade and 'equipment' in entry.get('catalogGroups', []) else None
        return items[ident]

    for ident, level, population, units, stacks, equipped, listed in raw.get('stock', []):
        if matches(level, population):
            row = item(ident)
            row['stock'] += units
            row['equipped'] += equipped
            row['listed'] += listed
    ownership = defaultdict(lambda: defaultdict(int))
    for ident, level, population, account, units in raw.get('owners', []):
        if matches(level, population):
            ownership[str(ident)][account] += units
    for ident, owners in ownership.items():
        row = item(ident)
        row['owners'] = len(owners) if not raw.get('ownersTruncated') else None
        row['topOwnerShare'] = max(owners.values()) / row['stock'] * 100 if owners and row['stock'] and not raw.get('ownersTruncated') else None
    for hint, level, population, events in raw.get('scriptFlows', []):
        if not matches(level, population):
            continue
        match = re.fullmatch(r'v1:(IN|OUT):([1-9][0-9]{0,9}):([1-9][0-9]{0,9})', str(hint))
        if match:
            row = item(match[2])
            key = 'scriptIn' if match[1] == 'IN' else 'scriptOut'
            row[key] = (row.get(key) or 0) + int(match[3]) * events
    for row in items.values():
        row.setdefault('owners', None)
        row.setdefault('topOwnerShare', None)
        row.setdefault('scriptIn', 0 if 'scriptFlows' in available else None)
        row.setdefault('scriptOut', 0 if 'scriptFlows' in available else None)
    current, previous = defaultdict(list), defaultdict(list)
    sales = []
    mixed_currency = 0
    for sale in raw.get('sales', []):
        at, ident, units, yang, cheque, buyer, seller, level, population = sale[:9]
        if not sale_matches(sale) or units <= 0:
            continue
        if cheque:
            mixed_currency += 1
            continue  # Never pretend Won transactions have comparable Yang prices.
        if yang <= 0:
            continue
        (current if at >= cutoff else previous)[str(ident)].append(yang / units)
        if at < cutoff:
            continue
        sales.append(sale)
        row = item(ident)
        row['sales'] += 1
        row['unitsSold'] += units
        row['turnover'] += yang
    for ident, row in items.items():
        row['unitPrice'] = median(current.get(ident, []))
        row['priceChange'] = change(row['unitPrice'], median(previous[ident])) if comparable(catalog.get(ident, {})) and len(current.get(ident, [])) >= 5 and len(previous.get(ident, [])) >= 5 else None
    metrics.update(turnover=sum(row[3] for row in sales) if 'sales' in available else None,
                   trades=len(sales) if 'sales' in available else None,
                   buyers=len({row[5] for row in sales}) if 'sales' in available else None,
                   stock=sum(row['stock'] or 0 for row in items.values()) if 'stock' in available else None)
    successes = attempts = scrolls = 0
    methods = Counter()
    for date, level, population, success, method, count in raw.get('refines', []):
        if matches(level, population):
            attempts += count
            successes += count if success == 1 else 0
            methods[method or 'Unspecified'] += count
            scrolls += count if method in ('SCROLL', 'HYUNIRON', 'GOD_SCROLL', 'MUSIN_SCROLL') else 0
    metrics.update(attempts=attempts if 'refines' in available else None, successes=successes,
                   successRate=successes / attempts * 100 if attempts else None,
                   scrollAttempts=scrolls if 'refines' in available else None)
    activity = Counter()
    action_fields = {'GET': 'acquisitions', 'USE_ITEM': 'uses', 'PLAYERBOT_SHOP_SELL': 'npcSales', 'REMOVE (REFINE FAIL)': 'burns'}
    action_totals = Counter()
    for how, ident, level, population, count in raw.get('actions', []):
        if not matches(level, population):
            continue
        action_totals[how] += count
        if how in ('STONE_KILL', 'BOSS_KILL'):
            activity[str(ident)] += count
        elif how in action_fields and ident:
            item(ident)[action_fields[how]] += count
    metrics['burns'] = action_totals['REMOVE (REFINE FAIL)'] if 'actions' in available else None
    money, daily = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for date, typ, created, removed, count in raw.get('money', []):
        money[typ][0] += created
        money[typ][1] += removed
        daily[date][0] += created
        daily[date][1] += removed
    metrics['recordedIn'] = sum(row[0] for row in money.values()) if 'money' in available else None
    metrics['recordedOut'] = sum(row[1] for row in money.values()) if 'money' in available else None
    metrics['recordedNet'] = metrics['recordedIn'] - metrics['recordedOut'] if 'money' in available else None
    bands = []
    for key in ('early', 'mid', 'late'):
        scoped = [row for row in raw.get('players', []) if matches(row[2], row[3], False) and stage(row[2], config) == key]
        band_sales = [row for row in raw.get('sales', []) if row[0] >= cutoff and sale_matches(row, False) and sale_identity(row)[0] > 0 and stage(sale_identity(row)[0], config) == key and not row[4] and row[2] > 0 and row[3] > 0]
        bands.append({'key': key, 'accounts': len({row[1] for row in scoped}), 'characters': len(scoped),
                      'active': len({row[0] for row in raw.get('active', []) if matches(row[1], row[2], False) and stage(row[1], config) == key}),
                      'wallet': sum(row[4] for row in scoped), 'turnover': sum(row[3] for row in band_sales),
                      'attempts': sum(row[5] for row in raw.get('refines', []) if matches(row[1], row[2], False) and row[1] > 0 and stage(row[1], config) == key)})
    alerts = []
    if raw.get('truncated'):
        alerts.append('Trade results are limited to the newest 20,000 records. Price and volume figures are a sample.')
    if mixed_currency:
        alerts.append(f'{mixed_currency} Won-denominated trades were excluded from Yang price comparisons and turnover.')
    if 'players' in available and len(wealth) < 20:
        alerts.append('Fewer than 20 accounts in this view: wealth distribution and market comparisons can be noisy.')
    banks = defaultdict(lambda: [0, 0])
    for bank in raw.get('banks', []) + raw.get('shopbanks', []):
        population = bank[3] if len(bank) > 3 else 'unknown'
        if matches(0, population, False):
            banks[bank[0]][0] += bank[1]
            banks[bank[0]][1] += bank[2] if len(bank) > 2 else 0
    rarity = []
    active_owners = {row[0] for row in raw.get('active', []) if matches(row[1], row[2])}
    for label, low, high in (('+0 to +3', 0, 3), ('+4 to +6', 4, 6), ('+7 and above', 7, 99)):
        group = [row for row in items.values() if row.get('grade') is not None and low <= row['grade'] <= high]
        owners = set().union(*(set(ownership.get(row['id'], {})) for row in group)) if group else set()
        known = 'owners' in available and not raw.get('ownersTruncated')
        active_count = len(owners & active_owners) if known and 'active' in available else None
        rarity.append({'grade': label, 'units': sum(row['stock'] or 0 for row in group) if 'stock' in available else None, 'owners': len(owners) if known else None,
                       'activeOwners': active_count, 'activeAccounts': len(active_owners) if 'active' in available else None,
                       'activeAccessPercent': active_count / len(active_owners) * 100 if active_count is not None and active_owners else None})
    refine_steps = [{'itemName': row[0], 'rawStep': row[1], 'success': row[4], 'method': row[5], 'attempts': row[6]} for row in raw.get('refineSteps', []) if matches(row[2], row[3])]
    gm_players = [row for row in raw.get('players', []) if row[3] == 'gm']
    return {'at': now, 'filters': config, 'metrics': metrics, 'bands': bands,
            'items': sorted(items.values(), key=lambda row: (-(row['stock'] or 0), int(row['id']))),
            'logCoverage': {key.removeprefix('coverage_'): {'earliest': rows[0][0], 'latest': rows[0][1], 'records': rows[0][2]} for key, rows in raw.items() if key.startswith('coverage_') and rows},
            'ownershipTruncated': bool(raw.get('ownersTruncated')), 'rarity': rarity, 'refineSteps': refine_steps,
            'prices': price_change(current, previous, catalog),
            'money': [{'type': key, 'created': value[0], 'removed': value[1]} for key, value in money.items()],
            'daily': [{'date': key, 'created': value[0], 'removed': value[1]} for key, value in sorted(daily.items())],
            'methods': dict(methods), 'activity': dict(activity), 'actionTotals': dict(action_totals),
            'banks': [[name, value[0], value[1]] for name, value in banks.items()], 'available': sorted(available), 'alerts': alerts,
            'gm': {'identified': bool(raw.get('gmSeparated')), 'accounts': len({row[1] for row in gm_players}), 'wallet': sum(row[4] for row in gm_players),
                   'involvedTrades': sum(1 for row in raw.get('sales', []) if row[0] >= cutoff and (row[8] == 'gm' or (len(row) > 9 and row[9])))},
            'coverage': [
                ['GM separation', 'Account registry' if raw.get('gmSeparated') else 'Unavailable', 'Any account with a character registered in common.gmlist is classified as GM, including its other characters and storage. Regular economy includes humans and bots only. Unattributed ownership is separate. Historical GM gifts already held by regular accounts cannot be reliably traced.'],
                ['Wallet balances & item stock', 'Observed' if {'players', 'stock'} <= available else 'Unavailable', 'Current database snapshot. Stage uses the owner’s current level. Safebox/mall stock is classified by account, has no stage, and appears only with All levels. Yang excludes Won; banks are separate, population-filtered and across all levels. Active accounts means retained CHARACTER/ITEM log activity.'],
                ['Currency sources & sinks', 'Mixed global logs' if 'money' in available else 'Unavailable', 'money_log has no actor identity. This panel includes possible GM activity in every population view and cannot be separated reliably. Log coverage is partial; it is not a complete money-supply reconciliation.'],
                ['Completed market trades', 'Observed' if 'sales' in available else 'Unavailable', 'Regular, human and bot views exclude trades involving a GM buyer or seller, including price comparisons. GM view includes either GM party and uses the seller’s stage if GM, otherwise the GM buyer’s stage. Everyone includes all. Historical bonuses and direct trades are unavailable.'],
                ['Price movement', 'Comparable goods only', 'Adjacent equal-length periods, exact commodity IDs, at least 5 sales per item in each period and 3 matched items. Books, equipment, stones and variable blends are excluded. Equal-weight geometric change; not a fixed-basket inflation index.'],
                ['Upgrades & destruction', 'Observed' if {'refines', 'actions'} <= available else 'Partial / unavailable', 'Attempts include only success flags 0/1; downgrade detail rows are excluded. Scroll method is not proof of protection. REMOVE (REFINE SUCCESS) is a conversion, not a destruction.'],
                ['Studio quest item flows', 'Limited instrumentation' if 'scriptFlows' in available else 'Unavailable', 'STUDIO_Q_ITEM v1 events measure exact inventory count changes around newly generated quest rewards and turn-ins. They exclude ordinary loot, crafting, upgrades and other quests. No records means no observed instrumented activity, not no server production.'],
                ['Creation, consumption & farming profit', 'Partial quest coverage only', 'GET may include transfers; use and NPC-sale logs do not prove quantities. Exact consumption, stock coverage days, net profit/hour and hours-to-upgrade require further instrumentation. No estimates are substituted.'],
                ['Configured drop sources', 'Saved definitions', 'Explicit shared pools are followed. Source counts are not production shares, drop probabilities or proof that a target was farmed.'],
            ]}


def configured_sources(studio):
    raw = {source: studio.source_raw(source) for source in studio.sources}
    signature = tuple(raw.items())
    cache = getattr(studio, '_economy_sources', None)
    if cache and cache[0] == signature:
        return cache[1]
    metadata = {(row['source'], row['key']): row for row in studio.groups(raw)}
    pools, mobs = defaultdict(list), {}
    for source, (_, filename, _) in studio.sources.items():
        for group in studio.dt.logical_groups(filename, raw[source]):
            meta = metadata.get((source, group.key))
            if not meta or not str(meta['id']).isdigit():
                continue
            if source.startswith('chest'):
                pools[meta['id']].append(group)
            else:
                target = mobs.setdefault(meta['id'], {'id': meta['id'], 'name': meta['name'], 'level': meta['level'], 'kind': meta['category'], 'groups': [], 'entries': []})
                target['groups'].append({'source': source, 'key': group.key})
                target['entries'].extend(group.entries)
    result = []
    for target in mobs.values():
        pending, visited, items = list(target.pop('entries')), set(), set()
        while pending:
            entry = pending.pop()
            if entry.item.startswith('s'):
                ident = entry.item[1:]
                if ident not in visited:
                    visited.add(ident)
                    for group in pools.get(ident, []):
                        pending.extend(group.entries)
            else:
                items.add(entry.item)
        target.update(items=len(items), pools=len(visited))
        result.append(target)
    result.sort(key=lambda row: (row['level'] or 0, int(row['id'])))
    studio._economy_sources = signature, result
    return result
