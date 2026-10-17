"""Read runtime content after a build; check custom drops and quest access."""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import subprocess


def verify_quest_access(studio):
    # qc creates object/state with mode 0700. Test as the actual game account,
    # since a root read and the container's healthcheck cannot detect this.
    script = '''set -eu
root=/opt/metin2/share/locale/poland/quest
test -r "$root/object/state" && test -x "$root/object/state"
states=$(find "$root/object/state" -type f -print)
test -n "$states"
bad=$(find "$root" \\( -type d \\( ! -readable -o ! -executable \\) \\) -o \\( -type f ! -readable \\))
test -z "$bad"
for state in $states; do head -c 1 "$state" >/dev/null; done
printf 'Quest state files readable: %s\\n' "$(printf '%s\\n' "$states" | wc -l)"
'''
    try:
        run = subprocess.run(['docker', 'compose', 'exec', '-T', '--user', 'metin2', 'game', 'sh', '-c', script],
                             cwd=studio.compose, capture_output=True, text=True, timeout=30,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if run.returncode:
            return {'readable': False, 'issue': 'Quest files are not readable by the game account. Quest loading is unverified; inspect quest directory permissions.'}
        return {'readable': True, 'detail': run.stdout.strip()}
    except (OSError, subprocess.TimeoutExpired):
        return {'readable': False, 'issue': 'Quest file access could not be verified as the game account.'}


def numeric(value):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return str(value)


def entries(group):
    counts, result = defaultdict(int), {}
    if group is None:
        return result
    for entry in group.entries:
        counts[entry.item] += 1
        result[entry.item, counts[entry.item]] = tuple(numeric(getattr(entry, key)) for key in ('count', 'prob', 'rare'))
    return result


def compare_groups(dt, filename, original, custom, runtime):
    parsed = [{row.key: row for row in dt.logical_groups(filename, raw or b'')} for raw in (original, custom, runtime)]
    before, desired, observed = parsed
    issues, checked = [], 0
    for key in before.keys() | desired.keys():
        a, b, c = before.get(key), desired.get(key), observed.get(key)
        aa, bb, cc = entries(a), entries(b), entries(c)
        changed = {ident for ident in aa.keys() | bb.keys() if aa.get(ident) != bb.get(ident)}
        fields = {field for field in set(a.fields if a else {}) | set(b.fields if b else {}) if not field.endswith('comment') and (a.fields.get(field) if a else None) != (b.fields.get(field) if b else None)}
        if not changed and not fields:
            continue
        checked += len(changed) + len(fields)
        if b is not None and c is None:
            issues.append(key + ': customised group missing from runtime table')
            continue
        if b is None and c is not None:
            issues.append(key + ': deleted custom group is present at runtime')
            continue
        for ident in changed:
            if cc.get(ident) != bb.get(ident):
                issues.append(key + ': item ' + ident[0] + ' custom count/parameter differs at runtime')
        for field in fields:
            if b and c and numeric(b.fields.get(field)) != numeric(c.fields.get(field)):
                issues.append(key + ': customised ' + field + ' differs at runtime')
    return checked, issues


def verify(studio):
    quest_access = verify_quest_access(studio)
    result = {'checkedFields': 0, 'issues': [] if quest_access['readable'] else [quest_access['issue']], 'files': [], 'questAccess': quest_access, 'scope': 'Quest file access as the game account and customised drop fields in loaded container files. Final probabilities, rates, level penalties and engine behaviour are not inferred. Other configuration types retain source-fingerprint and build checks.'}
    sources = {path.relative_to(studio.root).as_posix(): filename for path, filename, _ in studio.sources.values()}
    runtime_cache = {}
    for record in studio.workspace.tracked():
        filename = sources.get(record['path'])
        if not filename:
            continue
        if filename not in runtime_cache:
            target = '/opt/metin2/share/locale/poland/' + filename
            try:
                run = subprocess.run(['docker','compose','exec','-T','game','cat',target], cwd=studio.compose, capture_output=True, timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if run.returncode or len(run.stdout) > 12000000:
                    raise ValueError('Runtime drop table could not be read.')
                runtime_cache[filename] = run.stdout
            except (OSError, subprocess.TimeoutExpired, ValueError):
                result['issues'].append(record['path'] + ': runtime verification unavailable')
                continue
        count, issues = compare_groups(studio.dt, filename, record['original'], record['custom'], runtime_cache[filename])
        result['checkedFields'] += count
        result['issues'].extend(issues)
        result['files'].append(record['path'])
    return result
