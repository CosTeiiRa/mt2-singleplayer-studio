"""Shortcuts to the installed dashboard and read-only legacy Studio history."""
from contextlib import closing
import io
import ipaddress
from pathlib import Path
import re
import sqlite3
import tempfile
import zipfile


def dashboard_info(studio):
    path = studio.compose / '.env'
    values = {}
    if path.is_file():
        # Read only the three public connection settings, never return credentials.
        for line in path.read_text('utf-8-sig', errors='replace').splitlines():
            match = re.fullmatch(r'\s*(?:export\s+)?(M2_SEBAN_PANEL_PORT|M2_PANEL_BIND_ADDRESS|M2_HOST_BIND_ADDRESS)\s*=\s*(.*?)\s*', line)
            if match:
                value = match[2]
                if value.startswith(('"', "'")):
                    quote = value[0]
                    value = value[1:].split(quote, 1)[0]
                else:
                    value = value.split('#', 1)[0].strip()
                values[match[1]] = value
    result = {'economyUrl': None, 'archiveAvailable': (studio.state / 'economy.sqlite').is_file()}
    try:
        port = values.get('M2_SEBAN_PANEL_PORT') or '7790'
        if not re.fullmatch(r'\d{1,5}', port) or not 1 <= int(port) <= 65535:
            raise ValueError()
        address = values.get('M2_PANEL_BIND_ADDRESS') or values.get('M2_HOST_BIND_ADDRESS') or '127.0.0.1'
        host = ipaddress.ip_address(address.strip('[]'))
        if host.is_unspecified:
            host = ipaddress.ip_address('127.0.0.1' if host.version == 4 else '::1')
        host = '[' + str(host) + ']' if host.version == 6 else str(host)
        result['economyUrl'] = f'http://{host}:{int(port)}/economy'
    except ValueError:
        result['error'] = 'Check the game dashboard port and bind address in the installed Docker configuration.'
    return result


def retire_collection(workspace):
    """Disable an old schedule once, preserving its settings and all history."""
    schedule = workspace.preference('economySchedule', None)
    if isinstance(schedule, dict) and schedule.get('enabled'):
        workspace.set_preference('economySchedule', {**schedule, 'enabled': False})


def history_archive(state):
    """SQLite online backup includes saved WAL data without modifying the source."""
    state = Path(state)
    source = state / 'economy.sqlite'
    if not source.is_file():
        raise ValueError('No previous Studio economy history exists for this world.')
    with tempfile.TemporaryDirectory(prefix='economy-archive-', dir=state) as folder:
        target = Path(folder) / 'economy.sqlite'
        try:
            with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)) as original:
                with closing(sqlite3.connect(target)) as backup:
                    original.backup(backup)
            result = io.BytesIO()
            with zipfile.ZipFile(result, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.write(target, 'economy.sqlite')
                archive.writestr('README.txt', 'Previous Studio economy history\n\n'
                    'This SQLite database preserves Studio snapshots, journal notes and experiments.\n'
                    'It is an archive, separate from the game dashboard, and contains no new observations.\n'
                    'Open it with a SQLite viewer. The original database remains in Studio\'s world state folder.\n')
            return result.getvalue()
        except sqlite3.Error:
            raise ValueError('The saved economy database could not be archived. Its original file is preserved.') from None
