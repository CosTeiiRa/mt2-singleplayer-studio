"""Observed deployment stages. Step counts are not time estimates."""
import time


def prepare(job, *, validation=False, native_update=False, crafting=False):
    stages = [('build', 'Build & compile', 'Building game files and compiling quests.')]
    if not validation:
        stages += ([('launcher', 'Update & restart', 'The game launcher is building and restarting the updated services.')]
                   if native_update else [
                       ('database', 'Check database', 'Waiting for the database to be ready.'),
                       ('stop', 'Stop game', 'Stopping the game before applying saved settings.'),
                       ('migration', 'Apply settings', 'Running and checking the settings migration.'),
                       *([('crafting', 'Apply crafting', 'Verifying saved crafting recipes in a guarded transaction.')] if crafting else []),
                       ('restart', 'Restart game', 'Starting the game with the saved configuration.')])
        if native_update:
            stages = stages[1:]
    stages += [('sources', 'Verify saved files', 'Checking that saved sources still match this build.')]
    if not validation:
        stages += [('health', 'Check game health', 'Waiting for the game to report healthy.'),
                   ('content', 'Verify game content', 'Checking deployed custom changes and quest access.')]
    job['progress'] = {'current': None, 'steps': [
        {'id': key, 'label': label, 'detail': detail, 'status': 'pending'}
        for key, label, detail in stages]}


def command_stage(command):
    if command[:1] == ['powershell.exe']:
        return 'launcher'
    if command == ['studio', 'native-crafting']:
        return 'crafting'
    if command[2:4] == ['build', 'game']:
        return 'build'
    if command[2:4] == ['stop', 'game']:
        return 'stop'
    if 'playerbot-migrate' in command:
        return 'migration'
    return 'database' if command[-1] == 'mariadb' else 'restart'


def enter(job, key):
    progress = job.get('progress', {})
    if progress.get('current') == key:
        return
    for step in progress.get('steps', []):
        if step['status'] == 'running':
            step['status'] = 'complete'
        if step['id'] == key:
            step['status'] = 'running'
    progress['current'] = key


def finish(job):
    job['finished'] = time.time()
    for step in job.get('progress', {}).get('steps', []):
        if step['status'] == 'running':
            step['status'] = {'failed': 'failed', 'unverified': 'warning'}.get(job['status'], 'complete')
        elif step['status'] == 'pending':
            step['status'] = 'blocked'
