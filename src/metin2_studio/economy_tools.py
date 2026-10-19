"""Aggregate history, bounded background capture and evidence-led balancing experiments."""
import json
import math
import threading
import time

from metin2_studio.economy import change, options


class EconomyTools:
    def __init__(self, economy):
        self.economy = economy
        self.studio = economy.studio
        self.stop = threading.Event()
        self.status = {'state': 'idle', 'lastSuccess': None, 'error': None}
        with economy.connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS experiments (id INTEGER PRIMARY KEY, at REAL, title TEXT, hypothesis TEXT, filters TEXT, items TEXT, changeset TEXT, baseline TEXT, finished REAL, outcome TEXT)')

    def schedule(self, values):
        minutes = int(values.get('minutes', 60))
        retention = int(values.get('retention', 180))
        if minutes not in (15, 30, 60, 180) or not 7 <= retention <= 730:
            raise ValueError('Choose a 15, 30, 60 or 180 minute interval and 7–730 days of history.')
        config = {'enabled': bool(values.get('enabled')), 'minutes': minutes, 'retention': retention, 'filters': options(values.get('filters', {}))}
        self.studio.workspace.set_preference('economySchedule', config)
        return config

    def start(self):
        threading.Thread(target=self.worker, daemon=True, name='studio-economy-history').start()

    def worker(self):
        next_at = 0
        while not self.stop.wait(15):
            schedule = self.studio.workspace.preference('economySchedule', {})
            if not schedule.get('enabled'):
                self.status['state'] = 'disabled'
                continue
            if time.time() < next_at:
                continue
            next_at = time.time() + schedule.get('minutes', 60) * 60
            try:
                self.status.update(state='collecting', error=None)
                self.economy.capture(schedule.get('filters', {}))
                with self.economy.connect() as conn:
                    conn.execute('DELETE FROM snapshots WHERE at < ?', (time.time() - schedule.get('retention', 180) * 86400,))
                self.status.update(state='waiting', lastSuccess=time.time(), next=next_at)
            except Exception as error:
                self.status.update(state='failed', error=str(error), next=next_at)

    @staticmethod
    def aggregate(data):
        return {'at': data['at'], 'metrics': data['metrics'], 'available': data['available'], 'bands': data['bands'], 'rarity': data.get('rarity', []),
                'items': [{key: row.get(key) for key in ('id', 'stock', 'equipped', 'listed', 'sales', 'unitsSold', 'unitPrice', 'priceChange', 'owners', 'topOwnerShare', 'grade', 'scriptIn', 'scriptOut')} for row in data['items']]}

    def augment(self, data):
        watched = self.studio.workspace.preference('economyWatchlist', [])
        scope = json.dumps(data['filters'], sort_keys=True)
        with self.economy.connect() as conn:
            rows = conn.execute('SELECT at,payload FROM snapshots WHERE scope=? ORDER BY at DESC LIMIT 2000', (scope,)).fetchall()
            experiments = conn.execute('SELECT id,at,title,hypothesis,filters,items,changeset,baseline,finished,outcome FROM experiments ORDER BY at DESC LIMIT 100').fetchall()
        points = [{'at': at, **json.loads(payload)} for at, payload in reversed(rows)]
        data['historySeries'] = [{'at': row['at'], 'metrics': row['metrics'], 'bands': row.get('bands', [])} for row in points]
        data['watchlist'] = [{'id': ident, 'name': self.studio.items.get(ident, {}).get('name', '#' + ident), 'current': next((row for row in data['items'] if row['id'] == ident), None),
                              'history': [{'at': point['at'], **row} for point in points for row in point['items'] if row['id'] == ident]} for ident in watched]
        data['collection'] = {'schedule': self.studio.workspace.preference('economySchedule', {}), 'status': self.status, 'runningRequirement': 'Studio must remain running. The browser can be closed. Only successful observations are saved; missed periods are not filled with zero.'}
        queue = []
        for row in data['items']:
            evidence = []
            if row.get('stockChange') is not None and row['stockChange'] > 0 and row['sales'] == 0:
                evidence.append('Held stock increased with no recorded shop sale. Transfers and cohort movement can explain the change.')
            if row.get('priceChange') is not None and abs(row['priceChange']) >= 25:
                evidence.append('Matched commodity median price moved at least 25%; inspect sample size and supply before adjusting drops.')
            if row.get('topOwnerShare') is not None and row.get('owners', 0) >= 5 and row['topOwnerShare'] >= 50:
                evidence.append('One account holds at least half of this item in the selected cohort.')
            if evidence:
                queue.append({'item': row['id'], 'name': row['name'], 'reasons': evidence, 'stock': row['stock'], 'sales': row['sales'], 'confidence': 'Review needed', 'at': data['at']})
        data['reviewQueue'] = queue[:200]
        data['experiments'] = []
        for row in experiments:
            ident, at, title, hypothesis, filters, ids, changeset, baseline, finished, outcome = row
            config = json.loads(filters)
            base = json.loads(baseline)
            data['experiments'].append({'id': ident, 'at': at, 'title': title, 'hypothesis': hypothesis, 'filters': config, 'items': json.loads(ids), 'changeset': changeset,
                                        'baseline': base, 'finished': finished, 'outcome': json.loads(outcome) if outcome else None,
                                        'scopeMatches': config == data['filters']})
        data['historyLimits'] = 'Newest 2,000 matching observations in this view; item tables show the latest 100. Export includes all retained matching snapshots. Matching population, stage, boundaries and log-window definitions only. Current-level cohorts can move over time. Stock changes are not creation/consumption. Rolling periods overlap; experiment finish requires a complete non-overlapping period.'
        return data

    def experiment(self, values):
        action = values.get('action', 'start')
        if action == 'finish':
            with self.economy.connect() as conn:
                row = conn.execute('SELECT * FROM experiments WHERE id=?', (int(values['id']),)).fetchone()
            if not row or row[8] is not None:
                raise ValueError('Choose an open experiment.')
            config = json.loads(row[4])
            if time.time() - row[1] < config['days'] * 86400:
                raise ValueError('Wait one complete log period after the baseline to avoid overlapping before/after windows.')
            data = self.economy.report(config, fresh=True)
            if not data['connected']:
                raise ValueError(data['error'])
            with self.economy.connect() as conn:
                conn.execute('UPDATE experiments SET finished=?,outcome=? WHERE id=?', (data['at'], json.dumps(self.aggregate(data)), int(values['id'])))
            return {'saved': True}
        title, hypothesis = str(values.get('title', '')).strip(), str(values.get('hypothesis', '')).strip()
        ids = [str(ident) for ident in values.get('items', [])]
        if not title or len(title) > 120 or not hypothesis or len(hypothesis) > 1500 or len(ids) > 30 or any(ident not in self.studio.items for ident in ids):
            raise ValueError('Enter a title, hypothesis and at most 30 known item IDs.')
        data = self.economy.report(values.get('filters', {}), fresh=True)
        if not data['connected']:
            raise ValueError(data['error'])
        changeset = str(values.get('changeset', ''))
        if changeset:
            self.studio.workspace.change_set(changeset)
        with self.economy.connect() as conn:
            cur = conn.execute('INSERT INTO experiments(at,title,hypothesis,filters,items,changeset,baseline) VALUES (?,?,?,?,?,?,?)', (data['at'], title, hypothesis, json.dumps(data['filters'], sort_keys=True), json.dumps(ids), changeset, json.dumps(self.aggregate(data))))
        return {'id': cur.lastrowid, 'saved': True}
