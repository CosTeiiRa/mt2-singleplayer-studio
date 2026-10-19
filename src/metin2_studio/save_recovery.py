"""Durable save receipts and reviewed recovery of interrupted file transactions."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time


def fingerprint(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def durable_bytes(path, raw):
    path = Path(path)
    with path.open('wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def manifest_write(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp-' + secrets.token_hex(5))
    try:
        durable_bytes(temporary, (json.dumps(value, indent=2) + '\n').encode('utf-8'))
        os.replace(temporary, path)
        if os.name != 'nt':
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def read_receipt(path):
    try:
        record = json.loads(path.read_text('utf-8'))
        if (not isinstance(record, dict) or record.get('id') != path.parent.name
                or not isinstance(record.get('title'), str)
                or record.get('status') not in ('saving', 'recovering', 'saved', 'rolled-back')
                or not isinstance(record.get('files'), list)):
            raise ValueError('Invalid save receipt.')
        for file in record['files']:
            if (not isinstance(file, dict) or not isinstance(file.get('path'), str)
                    or type(file.get('existed')) is not bool or 'after' not in file):
                raise ValueError('Invalid save file receipt.')
            for key in ('before', 'after'):
                value = file.get(key)
                if value is not None and (not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value)):
                    raise ValueError('Invalid save checksum.')
        return record
    except (OSError, ValueError):
        return {'id': path.parent.name, 'title': 'Unreadable save receipt', 'status': 'unreadable',
                'files': [], 'error': 'A backup receipt is unreadable. Retain Studio data and restore the receipt from your Studio backup before saving or applying.'}


class SaveRecovery:
    def __init__(self, studio):
        self.studio = studio
        self.finalize_receipts()

    def receipts(self):
        for path in sorted((self.studio.state / 'backups').glob('*/manifest.json')):
            record = read_receipt(path)
            if record.get('error') or record['status'] in ('saving', 'recovering'):
                yield path, record

    def rows(self, path, record):
        if record.get('error'):
            raise ValueError(record['error'])
        result = []
        for index, file in enumerate(record['files']):
            target = self.studio.safe(self.studio.root / file['path'])
            before_path, after_path = path.parent / ('%s.before' % index), path.parent / ('%s.after' % index)
            before = before_path.read_bytes() if file['existed'] else None
            after = after_path.read_bytes() if file['after'] is not None else None
            if fingerprint(after) != file['after'] or 'before' in file and fingerprint(before) != file['before']:
                raise ValueError('An interrupted-save backup failed its checksum. Retain Studio data and restore the backup before recovery.')
            current = target.read_bytes() if target.exists() else None
            result.append((target, before, after, current))
        return result

    def committed(self):
        with self.studio.workspace.connect() as connection:
            rows = connection.execute("SELECT payload FROM activity WHERE kind='saved'").fetchall()
        return {json.loads(row['payload']).get('backup') for row in rows}

    def finalize_receipts(self):
        committed = self.committed()
        for path, record in self.receipts():
            if record.get('error'):
                continue
            if record['id'] in committed:
                # SQLite committed the save; only its final receipt was interrupted.
                # Later game updates are left entirely untouched.
                record['status'] = 'saved'
                manifest_write(path, record)
                continue
            try:
                rows = self.rows(path, record)
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if all(current == before for _, before, _, current in rows):
                record.update(status='rolled-back', recovery='No attempted file changes remain.', recovered=time.time())
                manifest_write(path, record)

    def pending(self):
        result = []
        for path, record in self.receipts():
            error = record.get('error')
            paths = [file['path'] for file in record.get('files', [])]
            changed = paths
            try:
                rows = self.rows(path, record)
                changed = [target.relative_to(self.studio.root).as_posix() for target, before, _, current in rows if current != before]
            except (OSError, ValueError, KeyError, TypeError) as failure:
                error = str(failure)
            result.append({'id': record['id'], 'title': record['title'], 'paths': paths, 'changed': changed,
                           'canRecover': not error, 'error': error})
        return result

    def require_clear(self):
        if self.pending():
            raise ValueError('An interrupted save requires recovery. Open Drafts & changes and Review recovery before saving or applying.')

    def preview(self, ident):
        if not re.fullmatch(r'\d{8}T\d{6}-[a-f0-9]{8}', str(ident)):
            raise ValueError('Invalid interrupted-save ID.')
        path = self.studio.state / 'backups' / ident / 'manifest.json'
        record = json.loads(path.read_text('utf-8'))
        if record.get('status') not in ('saving', 'recovering') or ident in self.committed():
            raise ValueError('This save no longer requires recovery. Refresh Studio.')
        rows = self.rows(path, record)
        changes = {target: before for target, before, after, current in rows if current == after and current != before}
        kept = [target.relative_to(self.studio.root).as_posix() for target, before, after, current in rows if current not in (before, after)]
        plan = self.studio.plan('Restore interrupted save: ' + record['title'], changes,
            'Restore only files still matching the interrupted writes. Files changed since then are kept as current game values. All before/after backups remain available. This does not build or restart the game.',
            from_disk=True, metadata={'saveRecovery': ident, 'guards': [(target, current) for target, _, _, current in rows], 'keptGameFiles': kept})
        plan['confirmLabel'] = 'Restore interrupted save'
        plan['keptGameFiles'] = kept
        return plan

    def commit(self, key, plan):
        ident = plan['metadata']['saveRecovery']
        path = self.studio.state / 'backups' / ident / 'manifest.json'
        record = json.loads(path.read_text('utf-8'))
        if record.get('status') not in ('saving', 'recovering') or ident in self.committed():
            raise ValueError('Recovery changed since review. Review recovery again.')
        self.rows(path, record)  # Validate every backup before replacing anything.
        for target, expected in plan['metadata']['guards']:
            observed = target.read_bytes() if target.exists() else None
            if observed != expected:
                raise ValueError('A file changed since recovery review. Review recovery again; newer game values will be kept.')
        record['status'] = 'recovering'
        manifest_write(path, record)
        for target, _, before in plan['files']:
            self.studio.write(target, before)
        record.update(status='rolled-back', recovered=time.time(), recovery='Interrupted file writes restored; newer game files retained.',
                      keptGameFiles=plan['metadata']['keptGameFiles'])
        manifest_write(path, record)
        self.studio.workspace.event('recovery', 'Restored interrupted save', {'backup': ident, 'keptGameFiles': record['keptGameFiles']})
        del self.studio.plans[key]
        return {'id': ident, 'recovered': True, 'hint': record['recovery'] + ' No build or restart was performed.'}
