"""Bounded read-only transactions against the world's existing database."""
from collections import defaultdict
import json
import subprocess


def query(compose, statements, timeout=45):
    sql = "SET SESSION max_statement_time=8; SET time_zone='+00:00'; SET TRANSACTION READ ONLY; START TRANSACTION WITH CONSISTENT SNAPSHOT;\n"
    sql += '\n'.join(statements) + '\nROLLBACK;'
    try:
        run = subprocess.run(['docker', 'compose', 'exec', '-T', 'mariadb', 'sh', '-c',
                              'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb -uroot --default-character-set=utf8mb4 -N -B --raw'],
                             input=sql, cwd=compose, capture_output=True, text=True,
                             encoding='utf-8', errors='replace', timeout=timeout,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError('The local database is unavailable or took too long.') from None
    if run.returncode:
        diagnostic = (run.stderr or '').lower()
        if any(reason in diagnostic for reason in ('dockerdesktoplinuxengine', 'daemon is running', 'cannot connect to the docker daemon', 'failed to connect to the docker api')):
            raise ValueError('Docker’s engine is stopped or unreachable. Open Docker Desktop and start your world in the game launcher.')
        raise ValueError('The read-only database query could not complete. The database may be stopped or its schema may differ.')
    result = defaultdict(list)
    for line in run.stdout.splitlines():
        try:
            record = json.loads(line)
            result[record['set']].append(record['row'])
        except (ValueError, KeyError, TypeError):
            raise ValueError('The database returned an unsupported response.') from None
    return dict(result)
