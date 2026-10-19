"""One cancellable repository job at a time; network I/O never owns Studio locks."""
import copy
from datetime import datetime, timezone
import threading
from urllib.parse import urlsplit
import uuid

from .hubcore.manager import _atomic_json, _json
from .transport import PublicHTTPSFetcher

OPERATIONS = {
    'repositories/add': {'url', 'channel'},
    'repositories/refresh': {'repository_id'},
    'repositories/check-updates': set(),
    'releases/review': {'repository_id', 'addon_id', 'version'},
    'releases/download': {'review_id', 'accept_source_change'},
}
ACTIVE = {'queued', 'running'}
HISTORY_LIMIT = 20


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class JobCancelled(Exception):
    pass


class RepositoryJobs:
    def __init__(self, path, repositories, finish):
        self.path, self.repositories, self.on_finish = path, repositories, finish
        self.lock = threading.RLock()
        self.cancel_event = threading.Event()
        self.thread = None
        stored = _json(path, {'schema_version': 1, 'jobs': []})
        if stored.get('schema_version') != 1 or not isinstance(stored.get('jobs'), list) or len(stored['jobs']) > HISTORY_LIMIT:
            raise ValueError('Repository job history is invalid. Preserve the add-on state folder.')
        self.records = stored['jobs']
        interrupted = False
        for row in self.records:
            if not isinstance(row, dict) or row.get('operation') not in OPERATIONS or not isinstance(row.get('id'), str):
                raise ValueError('Repository job history is invalid. Preserve the add-on state folder.')
            if row.get('status') in ACTIVE:
                row.update(status='interrupted', phase='finished', finished_at=now(),
                           error='Studio stopped before this job completed. Check the source and review again.')
                interrupted = True
        if interrupted:
            self._save()

    def _save(self):
        records = [{key: value for key, value in row.items() if key != 'result'} for row in self.records]
        _atomic_json(self.path, {'schema_version': 1, 'jobs': records})

    def _public(self, row, detail=False):
        result = copy.deepcopy(row)
        review = result.get('result', {}).get('review') if isinstance(result.get('result'), dict) else None
        if review and review['id'] not in self.repositories.pending:
            result.pop('result', None)
        result['result_available'] = result.get('result') is not None
        if not detail:
            result.pop('result', None)
        return result

    def latest(self):
        with self.lock:
            return self._public(self.records[-1]) if self.records else None

    def list(self):
        with self.lock:
            return [self._public(row) for row in reversed(self.records)]

    def get(self, ident):
        with self.lock:
            for row in self.records:
                if row['id'] == ident:
                    return self._public(row, detail=True)
        raise ValueError('Unknown repository job.')

    def assert_idle(self):
        with self.lock:
            if self.records and self.records[-1]['status'] in ACTIVE:
                raise ValueError('A repository job is running. Wait for it to finish or cancel it before changing add-ons.')

    def start(self, operation, data):
        if not isinstance(operation, str) or operation not in OPERATIONS or not isinstance(data, dict) or set(data) - OPERATIONS[operation]:
            raise ValueError('Choose a supported repository job and its documented fields.')
        required = OPERATIONS[operation] - {'channel', 'accept_source_change'}
        if (not required.issubset(data) or any(not isinstance(value, str) or not 0 < len(value) <= 4096
                for key, value in data.items() if key != 'accept_source_change')
                or 'accept_source_change' in data and not isinstance(data['accept_source_change'], bool)):
            raise ValueError('Supply the required repository job fields as strings, with a boolean source-change acknowledgement.')
        with self.lock:
            self.assert_idle()
            working = self.repositories.fork()
            expected = self.repositories.fingerprint(working._state())
            if operation == 'releases/download':
                if data.get('review_id') not in working.pending:
                    raise ValueError('Download review expired. Review the release again.')
                working.pending = {data['review_id']: working.pending[data['review_id']]}
            else:
                working.pending.clear()
            row = {'id': uuid.uuid4().hex, 'operation': operation, 'status': 'queued', 'phase': 'queued',
                   'message': 'Waiting to start', 'created_at': now(), 'cancel_requested': False,
                   'progress': {'received_bytes': 0, 'total_bytes': None}, 'error': None}
            previous = self.records
            self.records = [*self.records, row][-HISTORY_LIMIT:]
            self.cancel_event = threading.Event()
            try:
                self._save()
            except OSError:
                self.records = previous
                raise
            self.repositories.pending.clear()
            self.thread = threading.Thread(target=self._run, args=(row, working, expected, copy.deepcopy(data)), daemon=True)
            self.thread.start()
            return self._public(row)

    def cancel(self, ident):
        with self.lock:
            if not self.records or self.records[-1]['id'] != ident or self.records[-1]['status'] not in ACTIVE:
                raise ValueError('This repository job is already finished or cannot be cancelled.')
            row = self.records[-1]
            row.update(cancel_requested=True, message='Cancellation requested; waiting for the current network read to return')
            self.cancel_event.set()
            self._save()
            return self._public(row)

    def _checkpoint(self):
        if self.cancel_event.is_set():
            raise JobCancelled()

    def _progress(self, row, phase, message, received=0, total=None):
        with self.lock:
            self._checkpoint()
            row.update(phase=phase, message=message, progress={'received_bytes': received, 'total_bytes': total})

    def _run(self, row, working, expected, data):
        result, error = None, None
        try:
            with self.lock:
                row.update(status='running', started_at=now())
                self._save()
            original_fetch = working.fetch
            def fetch(url, limit):
                archive = row['operation'] == 'releases/download'
                message = 'Downloading package source' if archive else 'Reading repository metadata'
                if urlsplit(url).hostname == 'raw.githubusercontent.com':
                    message = 'Reading pinned manifest or README'
                self._progress(row, 'fetching', message)
                def progress(received, total):
                    self._progress(row, 'fetching', message, received, total)
                raw = original_fetch(url, limit, progress=progress) if isinstance(original_fetch, PublicHTTPSFetcher) else original_fetch(url, limit)
                progress(len(raw), len(raw))
                self._progress(row, 'validating', 'Validating repository response and declared files', len(raw), len(raw))
                return raw
            working.fetch = fetch
            self._checkpoint()
            operation = row['operation']
            if operation == 'repositories/add':
                working.add(data['url'], data.get('channel', 'stable'))
                result = {'repositories': working.list()}
            elif operation == 'repositories/refresh':
                working.refresh(data['repository_id'])
                result = {'repositories': working.list()}
            elif operation == 'repositories/check-updates':
                sources = [source for source in working.list() if source['enabled']]
                if not sources:
                    raise ValueError('Add or enable a repository before checking for updates.')
                checked = []
                for source in sources:
                    self._checkpoint()
                    try:
                        working.refresh(source['id'])
                        checked.append({'repository_id': source['id'], 'status': 'succeeded'})
                    except (ValueError, OSError) as exc:
                        checked.append({'repository_id': source['id'], 'status': 'failed', 'error': str(exc)})
                result = {'checked_repositories': checked, 'check_errors': sum(row['status'] == 'failed' for row in checked)}
            elif operation == 'releases/review':
                result = {'review': working.review(data['repository_id'], data['addon_id'], data['version'])}
            else:
                result = working.download(data['review_id'], data.get('accept_source_change', False))
            self._checkpoint()
        except Exception as exc:
            error = exc
        self.on_finish(row, working, expected, result, error)

    def finish(self, row, working, expected, result, error):
        """Called with the Studio/service locks held; no network I/O occurs here."""
        with self.lock:
            if self.cancel_event.is_set() or isinstance(error, JobCancelled):
                row.update(status='cancelled', message='Cancelled; prepared repository selections were discarded', error=None)
            else:
                try:
                    self.repositories.publish(working, expected)
                except (ValueError, OSError) as exc:
                    error = exc
                if error is None:
                    row.update(status='succeeded', message='Repository operation completed', result=result, error=None)
                    if result.get('checked_repositories') is not None:
                        row['message'] = 'Checked %s repositories; %s checks need attention. No add-ons were downloaded or installed.' % (
                            len(result['checked_repositories']), result['check_errors'])
                else:
                    row.update(status='failed', message='Repository operation failed', error=str(error))
            row.update(phase='finished', finished_at=now())
            self._save()
