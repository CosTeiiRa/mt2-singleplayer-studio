"""Studio-owned drafts, change sets, customisation originals and deployment history."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import base64
import difflib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time

from merge_custom import Choice, Merge, choice_id, merge, minimal_numeric_edit, rebase_original

SOURCE_VIEW = ContextVar('studio_source_view', default=None)


def sha(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def env_values(raw):
    return dict(re.findall(rb'(?m)^([A-Z][A-Z0-9_]*)=([^\r\n]*)', (raw or b'').removeprefix(b'\xef\xbb\xbf')))


class EnvMerge:
    """Only allowlisted gameplay keys can appear in a settings merge or report."""
    def __init__(self, base, custom, incoming, allowed, salt):
        self.incoming = incoming
        before, ours, theirs = map(env_values, (base, custom, incoming))
        self.choices, self.keys = [], {}
        for key in sorted(allowed):
            token = key.encode('ascii')
            old, our, their = before.get(token), ours.get(token), theirs.get(token)
            if our != old and our != their:
                ident = choice_id(salt, key, old, our, their)
                piece = Choice(ident, old, our, their, their != old, 1, key)
                self.choices.append(piece)
                self.keys[ident] = token

    def resolve(self, decisions=None, require=True):
        result = self.incoming or b''
        newline = b'\r\n' if b'\r\n' in result else b'\n'
        for piece in self.choices:
            decision = (decisions or {}).get(piece.ident, None if piece.conflict and require else 'keep')
            if decision not in ('keep', 'update'):
                raise ValueError('Choose Keep custom or Use update for every conflicting custom setting.')
            if decision == 'update':
                continue
            key = self.keys[piece.ident]
            pattern = rb'(?m)^' + re.escape(key) + rb'=[^\r\n]*(?:\r?\n|$)'
            replacement = key + b'=' + piece.custom + newline if piece.custom is not None else b''
            bom = b'\xef\xbb\xbf' if result.startswith(b'\xef\xbb\xbf') else b''
            body = result[len(bom):]
            if re.search(pattern, body):
                body = re.sub(pattern, lambda _: replacement, body, count=1)
            elif replacement:
                body += (newline if body and not body.endswith(b'\n') else b'') + replacement
            result = bom + body
        return result


class Workspace:
    def __init__(self, studio):
        self.studio = studio
        self.db = studio.state / 'workspace.sqlite'
        self.reports = {}
        with self.connect() as conn:
            conn.executescript('''
              CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS tracked (path TEXT PRIMARY KEY, original BLOB, custom BLOB, expected BLOB, updated REAL NOT NULL, version TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS drafts (id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, payload TEXT NOT NULL, updated REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS changesets (id TEXT PRIMARY KEY, name TEXT NOT NULL, note TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS staged (changeset TEXT NOT NULL, path TEXT NOT NULL, original BLOB, content BLOB, title TEXT NOT NULL, PRIMARY KEY(changeset,path));
              CREATE TABLE IF NOT EXISTS deployments (id TEXT PRIMARY KEY, status TEXT NOT NULL, started REAL NOT NULL, finished REAL, payload TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, payload TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS source_cache (path TEXT, hash TEXT, raw BLOB, at REAL, PRIMARY KEY(path,hash));
            ''')
            row = conn.execute("SELECT value FROM meta WHERE key='installation'").fetchone()
            if row and row['value'] != str(studio.root):
                raise ValueError('This Studio data folder belongs to another installation. Use a separate --state folder.')
            conn.execute("INSERT OR IGNORE INTO meta VALUES ('installation',?)", (str(studio.root),))

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def version(self):
        path = self.studio.root / 'VERSION'
        return path.read_text('utf-8').strip() if path.exists() else 'unknown'

    def event(self, kind, title, payload=None, conn=None):
        if conn is None:
            with self.connect() as target:
                return self.event(kind, title, payload, target)
        conn.execute('INSERT INTO activity(at,kind,title,payload) VALUES (?,?,?,?)', (time.time(), kind, title, json.dumps(payload or {})))

    def preference(self, key, default=None):
        with self.connect() as conn:
            row = conn.execute('SELECT payload FROM preferences WHERE key=?', (key,)).fetchone()
        return json.loads(row['payload']) if row else default

    def set_preference(self, key, value):
        with self.connect() as conn:
            conn.execute('INSERT OR REPLACE INTO preferences VALUES (?,?)', (key, json.dumps(value)))
        return value

    def save_draft(self, values):
        ident, kind = str(values.get('id', '')), str(values.get('kind', ''))
        if not 1 <= len(ident) <= 400 or kind not in ('drops', 'quests', 'crafting', 'settings', 'files'):
            raise ValueError('Invalid draft identity or editor.')
        title = str(values.get('title', kind))[:160]
        payload = json.dumps(values.get('payload', {}), ensure_ascii=True)
        if len(payload) > 10000000:
            raise ValueError('Draft is too large.')
        with self.connect() as conn:
            conn.execute('INSERT OR REPLACE INTO drafts VALUES (?,?,?,?,?)', (ident, kind, title, payload, time.time()))
        return {'saved': True}

    def drafts(self, ident=None):
        with self.connect() as conn:
            if ident is not None:
                row = conn.execute('SELECT * FROM drafts WHERE id=?', (ident,)).fetchone()
                return {**dict(row), 'payload': json.loads(row['payload'])} if row else None
            return [dict(row) for row in conn.execute('SELECT id,kind,title,updated FROM drafts ORDER BY updated DESC')]

    def remove_draft(self, ident):
        with self.connect() as conn:
            conn.execute('DELETE FROM drafts WHERE id=?', (str(ident),))
        return {'deleted': True}

    def create_set(self, values):
        name, note = str(values.get('name', '')).strip(), str(values.get('note', '')).strip()
        if not 1 <= len(name) <= 120 or len(note) > 1500:
            raise ValueError('Use a change-set name up to 120 characters and notes up to 1,500 characters.')
        ident, at = secrets.token_hex(12), time.time()
        with self.connect() as conn:
            conn.execute('INSERT INTO changesets VALUES (?,?,?,?,?,?)', (ident, name, note, 'draft', at, at))
            self.event('changeset', 'Created ' + name, {'changeset': ident}, conn)
        return {'id': ident, 'name': name}

    def change_sets(self):
        with self.connect() as conn:
            return [dict(row) for row in conn.execute('SELECT c.*,COUNT(s.path) AS files FROM changesets c LEFT JOIN staged s ON s.changeset=c.id GROUP BY c.id ORDER BY c.updated DESC')]

    def change_set(self, ident):
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM changesets WHERE id=?', (ident,)).fetchone()
            files = [dict(item) for item in conn.execute('SELECT path,title FROM staged WHERE changeset=? ORDER BY path', (ident,))]
        if not row:
            raise ValueError('Change set not found.')
        return {**dict(row), 'files': files}

    def read(self, path, changeset):
        rel = self.studio.safe(path).relative_to(self.studio.root).as_posix()
        if SOURCE_VIEW.get() is not None and rel in SOURCE_VIEW.get():
            return SOURCE_VIEW.get()[rel]
        if changeset:
            with self.connect() as conn:
                row = conn.execute("SELECT s.content FROM staged s JOIN changesets c ON c.id=s.changeset WHERE c.id=? AND c.status='draft' AND s.path=?", (changeset, rel)).fetchone()
            if row:
                self.cache_source(rel, row['content'])
                return row['content']
        raw = path.read_bytes() if path.exists() else None
        self.cache_source(rel, raw)
        return raw

    def cache_source(self, rel, raw):
        if raw is not None and len(raw) <= 2000000:
            with self.connect() as conn:
                conn.execute('INSERT OR IGNORE INTO source_cache VALUES (?,?,?,?)', (rel, sha(raw), raw, time.time()))
                conn.execute('DELETE FROM source_cache WHERE path=? AND hash NOT IN (SELECT hash FROM source_cache WHERE path=? ORDER BY at DESC LIMIT 20)', (rel, rel))
        return raw

    def draft_to_set(self, ident):
        draft = self.drafts(ident)
        if not draft:
            raise ValueError('Draft no longer exists.')
        payload, kind = draft['payload'], draft['kind']
        value = payload.get({'drops': 'group', 'crafting': 'recipe', 'settings': 'settings', 'files': 'file', 'quests': 'quest'}[kind], {})
        view = {}
        if kind == 'quests' and value.get('native'):
            with self.connect() as conn:
                for rel, expected in value['model']['hashes'].items():
                    self.studio.safe(self.studio.root / rel)
                    cached = conn.execute('SELECT raw FROM source_cache WHERE path=? AND hash=?', (rel, expected)).fetchone()
                    if not cached:
                        raise ValueError('An original quest dependency is no longer cached. The draft is preserved; reopen it and compare with current sources.')
                    view[rel] = cached['raw']
        if kind != 'quests':
            rel = value.get('file') if kind in ('drops', 'crafting') else value.get('id') if kind == 'files' else 'linux-port/docker/.env'
            rel = str(rel).replace('\\', '/')
            with self.connect() as conn:
                cached = conn.execute('SELECT raw FROM source_cache WHERE path=? AND hash=?', (rel, value.get('hash'))).fetchone()
            if not cached:
                raise ValueError('The original source for this draft is unavailable. Its draft is preserved; inspect it against the current editor before saving.')
            view[rel] = cached['raw']
        created = self.create_set({'name': 'Recovered draft: ' + draft['title'][:90]})
        ACTIVE_CHANGESET = self.studio.active_context
        source_token = SOURCE_VIEW.set(view)
        set_token = ACTIVE_CHANGESET.set(created['id'])
        try:
            if kind == 'settings':
                value = {'hash': value['hash'], 'values': {row['key']: row['draft'] for row in value['settings'] if 'draft' in row and row['draft'] != row['value']}}
            if kind == 'quests' and value.get('native'):
                from quest_fields import plan as quest_fields_plan
                plan = quest_fields_plan(self.studio, {**value['model'], 'values': value['values']})
            elif kind == 'files' and value.get('tableEdits'):
                from studio_features import table_plan
                edits = [{'line': int(key.split(':')[0]), 'column': int(key.split(':')[1]), 'value': content} for key, content in value['tableEdits'].items()]
                plan = table_plan(self.studio, {**value, 'edits': edits})
            else:
                plan = {'drops': self.studio.drop_plan, 'crafting': self.studio.recipe_plan, 'settings': self.studio.settings_plan, 'files': self.studio.file_plan, 'quests': self.studio.quest_plan}[kind](value)
            with self.connect() as conn:
                for path, old, new in self.studio.plans.pop(plan['id'])['files']:
                    conn.execute('INSERT OR REPLACE INTO staged VALUES (?,?,?,?,?)', (created['id'], path.relative_to(self.studio.root).as_posix(), old, new, draft['title']))
        except Exception:
            with self.connect() as conn:
                conn.execute('DELETE FROM changesets WHERE id=?', (created['id'],))
            raise
        finally:
            SOURCE_VIEW.reset(source_token)
            ACTIVE_CHANGESET.reset(set_token)
        return created

    def review_set(self, ident):
        if self.change_set(ident)['status'] != 'draft':
            raise ValueError('Only an open change set can be rebased.')
        with self.connect() as conn:
            records = [{'path': row['path'], 'original': row['original'], 'custom': row['content'], 'expected': row['original'], 'version': 'staged base'} for row in conn.execute('SELECT * FROM staged WHERE changeset=?', (ident,))]
        result = self.scan(kind='changeset', records=records)
        self.reports[result['id']]['changeset'] = ident
        return result

    def rebase_set(self, values):
        report, _, rebased = self.reconciliation(values)
        if report['kind'] != 'changeset':
            raise ValueError('Review an open change set first.')
        ident = report['changeset']
        if self.change_set(ident)['status'] != 'draft':
            raise ValueError('This change set has already been saved.')
        with self.connect() as conn:
            for row in report['files']:
                record = row['record']
                old = conn.execute('SELECT original,content FROM staged WHERE changeset=? AND path=?', (ident, record['path'])).fetchone()
                if not old or old['original'] != record['original'] or old['content'] != record['custom']:
                    raise ValueError('This change set changed since review. Review it again.')
            for row in report['files']:
                rel = row['record']['path']
                merged = rebased[rel][2]
                if merged == row['current']:
                    conn.execute('DELETE FROM staged WHERE changeset=? AND path=?', (ident, rel))
                else:
                    conn.execute('UPDATE staged SET original=?,content=? WHERE changeset=? AND path=?', (row['current'], merged, ident, rel))
        return {'saved': True, 'id': ident}

    def stage(self, plan):
        ident = plan['changeset']
        for path, expected in plan.get('metadata', {}).get('guards', []):
            if self.read(path, ident) != expected:
                raise ValueError('A quest dependency changed since review. Reopen the editor.')
        with self.connect() as conn:
            row = conn.execute('SELECT name,status FROM changesets WHERE id=?', (ident,)).fetchone()
            if not row or row['status'] != 'draft':
                raise ValueError('Choose an open change set before staging changes.')
            for path, old, new in plan['files']:
                rel = path.relative_to(self.studio.root).as_posix()
                previous = conn.execute('SELECT original,content FROM staged WHERE changeset=? AND path=?', (ident, rel)).fetchone()
                current = previous['content'] if previous else (path.read_bytes() if path.exists() else None)
                if current != old:
                    raise ValueError('This change set changed since review. Reopen the editor.')
                original = previous['original'] if previous else current
                if original == new:
                    conn.execute('DELETE FROM staged WHERE changeset=? AND path=?', (ident, rel))
                else:
                    conn.execute('INSERT OR REPLACE INTO staged VALUES (?,?,?,?,?)', (ident, rel, original, new, plan['title']))
            conn.execute('UPDATE changesets SET updated=? WHERE id=?', (time.time(), ident))
            self.event('staged', plan['title'], {'changeset': ident}, conn)
        return {'id': ident, 'title': plan['title'], 'hint': 'Staged in ' + row['name'] + '. Game files are unchanged.', 'staged': True}

    def publish_plan(self, ident):
        info = self.change_set(ident)
        if info['status'] != 'draft':
            raise ValueError('This change set has already been saved.')
        if self.scan()['affectedFiles']:
            raise ValueError('Resolve affected saved customisations in Update protection before publishing staged work. Then review this set against the reconciled files.')
        with self.connect() as conn:
            rows = [dict(row) for row in conn.execute('SELECT * FROM staged WHERE changeset=?', (ident,))]
        if not rows:
            raise ValueError('Add reviewed changes to this change set first.')
        changes = {}
        for row in rows:
            path = self.studio.safe(self.studio.root / row['path'])
            current = path.read_bytes() if path.exists() else None
            if current != row['original']:
                raise ValueError(row['path'] + ' changed outside this change set. Review update protection before saving.')
            changes[path] = row['content']
        return self.studio.plan('Save change set: ' + info['name'], changes, 'All files are saved together with a backup. Apply them separately when ready.', from_disk=True, metadata={'publishSet': ident})

    def record_commit(self, files, title, ident, metadata=None):
        metadata = metadata or {}
        with self.connect() as conn:
            for rel, original, custom, expected in metadata.get('adopt', []):
                if conn.execute('SELECT 1 FROM tracked WHERE path=?', (rel,)).fetchone():
                    raise ValueError('This file is already tracked. Review its existing customisation instead.')
                conn.execute('INSERT INTO tracked VALUES (?,?,?,?,?,?)', (rel, original, custom, expected, time.time(), self.version()))
            reconciled = metadata.get('reconciled', {})
            for path, old, new in files:
                rel = path.relative_to(self.studio.root).as_posix()
                if rel in reconciled:
                    continue
                row = conn.execute('SELECT * FROM tracked WHERE path=?', (rel,)).fetchone()
                original = row['original'] if row else old
                previous = row['custom'] if row else old
                if row and old != row['expected']:
                    if path.name == '.env':
                        reverse = EnvMerge(row['custom'], row['original'], old, self.studio.settings_schema, 'saved-original')
                        original = reverse.resolve({piece.ident: 'update' for piece in reverse.choices if piece.conflict})
                    else:
                        original = rebase_original(row['original'], row['custom'], old)
                    previous = old
                custom = minimal_numeric_edit(previous, new) if path.name in ('mob_drop_item.txt', 'special_item_group.txt') or any(part in path.name for part in ('mob_drop_item.', 'special_item_group.')) else new
                if custom == original:
                    conn.execute('DELETE FROM tracked WHERE path=?', (rel,))
                else:
                    conn.execute('INSERT OR REPLACE INTO tracked VALUES (?,?,?,?,?,?)', (rel, original, custom, new, time.time(), self.version()))
            for rel, values in reconciled.items():
                original, custom, expected = values
                if original == custom:
                    conn.execute('DELETE FROM tracked WHERE path=?', (rel,))
                else:
                    conn.execute('UPDATE tracked SET original=?,custom=?,expected=?,updated=?,version=? WHERE path=?', (original, custom, expected, time.time(), self.version(), rel))
            if metadata.get('publishSet'):
                conn.execute("UPDATE changesets SET status='saved',updated=? WHERE id=?", (time.time(), metadata['publishSet']))
            self.event('saved', title, {'backup': ident, 'files': [path.relative_to(self.studio.root).as_posix() for path, _, _ in files]}, conn)

    def adoption_sources(self):
        paths = {row['id'].replace('\\', '/') for row in self.studio.inventory()}
        paths.update(path.relative_to(self.studio.root).as_posix() for path, _, _ in self.studio.sources.values())
        paths.update(path.relative_to(self.studio.root).as_posix() for path in (self.studio.compose / '.env', self.studio.game / 'Dockerfile', self.studio.game / '.dockerignore'))
        tracked = {row['path'] for row in self.tracked()}
        return sorted(paths - tracked)

    def adopt_plan(self, values):
        rel = str(values.get('path', ''))
        if rel not in self.adoption_sources():
            raise ValueError('Choose an untracked editable configuration file.')
        try:
            original = base64.b64decode(str(values.get('original', '')), validate=True)
        except ValueError:
            raise ValueError('Choose the original backup file.') from None
        if not original or len(original) > 2000000:
            raise ValueError('Import an original backup under 2 MB.')
        path = self.studio.safe(self.studio.root / rel)
        current = path.read_bytes() if path.exists() else None
        if current is None or current == original:
            raise ValueError('The current file is missing or identical to this backup.')
        if path.name == '.env':
            # Adopt only gameplay keys. Credentials and native updater fields remain outside custom intent.
            combined = EnvMerge(original, current, original, self.studio.settings_schema, 'adopt')
            custom = combined.resolve({piece.ident: 'keep' for piece in combined.choices})
        else:
            custom = current
        if custom == original:
            raise ValueError('No editable custom differences were found in that backup.')
        plan = self.studio.plan('Track existing custom edits: ' + path.name, {}, 'This records the difference between your original backup and current file for future update reviews. It does not rewrite game files. Confirm the backup belongs to this exact configuration.', from_disk=True, metadata={'adopt': [(rel, original, custom, current)], 'guards': [(path, current)]})
        a, b = (value.decode('utf-8', 'replace') for value in (original, custom))
        if path.name == '.env':
            a = '\n'.join(line for line in a.splitlines() if line.split('=', 1)[0] in self.studio.settings_schema)
            b = '\n'.join(line for line in b.splitlines() if line.split('=', 1)[0] in self.studio.settings_schema)
        plan['files'] = [{'path': rel, 'diff': '\n'.join(difflib.unified_diff(a.splitlines(), b.splitlines(), fromfile='original backup', tofile='your current file', lineterm=''))[:120000]}]
        return plan

    def signature(self):
        return [(row['path'], sha((row['original'] or b'') + b'\0' + (row['custom'] or b'') + b'\0' + (row['expected'] or b''))) for row in self.tracked()]

    def tracked(self):
        with self.connect() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM tracked ORDER BY path')]

    def compare(self, record, incoming):
        if record['path'] == 'linux-port/docker/.env':
            return EnvMerge(record['original'], record['custom'], incoming, self.studio.settings_schema, record['path'])
        return merge(record['original'], record['custom'], incoming, record['path'])

    def scan(self, incoming_files=None, kind='installed', package=None, records=None):
        rows, state, conflicts = [], [], 0
        for record in self.tracked() if records is None else records:
            path = self.studio.safe(self.studio.root / record['path'])
            current = path.read_bytes() if path.exists() else None
            incoming = incoming_files.get(record['path'], current) if incoming_files is not None else current
            if incoming == record['expected']:
                continue
            combined = self.compare(record, incoming)
            if not combined.choices:
                if kind == 'changeset':
                    state.append({'record': record, 'incoming': incoming, 'current': current, 'merge': combined})
                continue  # No custom area was affected; unrelated changes need no approval.
            choices = []
            for piece in combined.choices:
                def display(raw):
                    return None if raw is None else raw.decode('utf-8', 'replace')[:6000]
                context = piece.context
                if record['path'].endswith('/.env'):
                    context = self.compare(record, incoming).keys.get(piece.ident, b'').decode()
                choices.append({'id': piece.ident, 'original': display(piece.base), 'custom': display(piece.custom), 'incoming': display(piece.incoming), 'conflict': piece.conflict, 'line': piece.line, 'context': context})
                conflicts += int(piece.conflict)
            rows.append({'path': record['path'], 'choices': choices, 'originalVersion': record['version']})
            state.append({'record': record, 'incoming': incoming, 'current': current, 'merge': combined})
        ident = secrets.token_urlsafe(18)
        self.reports = {key: value for key, value in self.reports.items() if time.time()-value['at'] < 3600}
        self.reports[ident] = {'at': time.time(), 'files': state, 'kind': kind, 'package': package}
        return {'id': ident, 'kind': kind, 'at': time.time(), 'version': self.version(), 'trackedFiles': len(self.tracked()), 'affectedFiles': len(rows), 'conflicts': conflicts, 'files': rows,
                'scope': 'Only entries changed through Studio are reviewed. Unrelated incoming changes are retained automatically. External launcher updates bypass pre-install review; use the protected package workflow to review before the next build.'}

    def reconciliation(self, values):
        report = self.reports.get(str(values.get('id', '')))
        if not report or time.time()-report['at'] >= 3600:
            raise ValueError('This update review expired. Scan again.')
        decisions = values.get('decisions', {})
        known = {piece.ident for row in report['files'] for piece in row['merge'].choices}
        if not isinstance(decisions, dict) or set(decisions) - known or any(value not in ('keep', 'update') for value in decisions.values()):
            raise ValueError('Invalid customisation choices. Scan again.')
        changes, rebased = {}, {}
        for row in report['files']:
            record = row['record']
            path = self.studio.safe(self.studio.root / record['path'])
            current = path.read_bytes() if path.exists() else None
            if current != row['current']:
                raise ValueError(record['path'] + ' changed since this review. Scan again.')
            merged = row['merge'].resolve(decisions)
            if record['path'].endswith('/.env'):
                reverse = EnvMerge(record['custom'], record['original'], row['incoming'], self.studio.settings_schema, 'reverse')
                original = reverse.resolve({piece.ident: 'update' for piece in reverse.choices if piece.conflict})
            else:
                original = rebase_original(record['original'], record['custom'], row['incoming'])
            custom = minimal_numeric_edit(original, merged) if any(name in path.name for name in ('mob_drop_item', 'special_item_group')) else merged
            rebased[record['path']] = (original, custom, merged)
            if merged != current:
                changes[path] = merged
        return report, changes, rebased

    def reconcile_plan(self, values):
        report, changes, rebased = self.reconciliation(values)
        if report['kind'] != 'installed':
            raise ValueError('Use the package installation review for a staged game update.')
        if not rebased:
            raise ValueError('No custom changes need reconciliation.')
        guards = [(self.studio.root / row['record']['path'], row['current']) for row in report['files']]
        return self.studio.plan('Reconcile custom changes after update', changes, 'Your selected custom entries are merged; unrelated update content is retained. Rebuild separately when ready.', from_disk=True, metadata={'reconciled': rebased, 'guards': guards, 'tracking': self.signature()})

    def pending_saved_paths(self):
        # A rollback can remove its custom-diff tracking (it equals the package
        # original again) while the running image still holds the previous edit.
        with self.connect() as conn:
            last = conn.execute("SELECT started FROM deployments WHERE status='succeeded' ORDER BY started DESC LIMIT 1").fetchone()
            rows = conn.execute("SELECT payload FROM activity WHERE kind='saved' AND at>?", (last['started'] if last else 0,)).fetchall()
        return {rel for row in rows for rel in json.loads(row['payload']).get('files', [])}

    def summary(self):
        tracked = self.tracked()
        pending = []
        with self.connect() as conn:
            deployment = conn.execute("SELECT * FROM deployments WHERE status='succeeded' ORDER BY started DESC LIMIT 1").fetchone()
            recent = [dict(row) for row in conn.execute('SELECT id,at,kind,title,payload FROM activity ORDER BY at DESC LIMIT 12')]
            preferences = {row['key']: json.loads(row['payload']) for row in conn.execute('SELECT * FROM preferences')}
        if not preferences.get('nativeUpdatePending') and (self.studio.root / '.m2launcher-rebuild-pending').is_file():
            preferences['nativeUpdatePending'] = {'ready': True, 'external': True}
        deployed = json.loads(deployment['payload']).get('files', {}) if deployment else {}
        records = {row['path']: row for row in tracked}
        for rel in sorted(set(records) | self.pending_saved_paths()):
            row = records.get(rel)
            path = self.studio.safe(self.studio.root / rel)
            current = path.read_bytes() if path.exists() else None
            fingerprint = self.studio.build_fingerprints().get(rel) if path == self.studio.compose / '.env' else sha(current)
            if fingerprint != deployed.get(rel):
                pending.append({'path': rel, 'changedOutsideStudio': bool(row and current != row['expected'])})
        return {'drafts': self.drafts(), 'changesets': self.change_sets(), 'tracked': [{'path': row['path'], 'version': row['version'], 'updated': row['updated']} for row in tracked],
                'pending': pending, 'lastDeployment': {**dict(deployment), 'payload': json.loads(deployment['payload'])} if deployment else None,
                'recent': [{**row, 'payload': json.loads(row['payload'])} for row in recent], 'preferences': preferences,
                'deploymentKnown': bool(deployment), 'version': self.version()}

    def deployment(self, ident, status, payload):
        with self.connect() as conn:
            previous = conn.execute('SELECT started FROM deployments WHERE id=?', (ident,)).fetchone()
            conn.execute('INSERT OR REPLACE INTO deployments VALUES (?,?,?,?,?)', (ident, status, previous['started'] if previous else time.time(), time.time() if status != 'running' else None, json.dumps(payload)))
            if status != 'running':
                self.event('deployment', 'Server apply ' + status, {'deployment': ident}, conn)
