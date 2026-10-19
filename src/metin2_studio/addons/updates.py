"""Read-only update notices and cached changelogs; never fetch, select or apply code."""
from .versions import Version

NO_NOTES = 'No changelog provided for this release.'


def update_notices(installed, offers, catalog):
    current = {item['id']: item for item in installed}
    selected = {item['id']: item for item in catalog}
    result = []
    for offer in offers:
        if not offer['update_available']:
            continue
        record, release = current[offer['id']], offer['latest']
        package = selected.get(offer['id'], {})
        development = release.get('kind') == 'development'
        source = package.get('distribution') or {}
        ready = bool(package.get('update_available') and source.get('repository_id') == offer['repository_id'] and
                     (package.get('package_digest') == release.get('manifest_digest') if development
                      else package.get('version') == release['version']))
        changes = []
        for entry in offer['releases']:
            if development:
                include = entry.get('kind') == 'development'
            else:
                try:
                    include = Version(record['version']) < Version(entry['version']) <= Version(release['version'])
                except ValueError:
                    include = False
            if include:
                changes.append({'version': entry.get('package_version', entry['version']),
                                'release_notes': entry.get('release_notes') or NO_NOTES,
                                'withdrawn': entry.get('withdrawn', False), 'reason': entry.get('reason', '')})
        result.append({'id': record['id'], 'name': record['name'], 'kind': 'repository',
                       'installed_version': record['version'], 'installed_commit': (record.get('distribution') or {}).get('commit'),
                       'available_version': release.get('package_version', release['version']),
                       'available_commit': release.get('commit'), 'selection': release['version'],
                       'development': development, 'repository_id': offer['repository_id'],
                       'repository_name': offer['repository_name'], 'repository_url': offer['repository_url'],
                       'checked_at': offer.get('checked_at'), 'check_error': offer.get('error'),
                       'download_ready': ready, 'can_download': not offer['blocked'] and (not offer.get('error') or release['cached']),
                       'changes': changes})
    offered = {row['id'] for row in result}
    for ident, package in selected.items():
        if ident in offered or ident not in current or not package.get('update_available') or package.get('error'):
            continue
        record = current[ident]
        source = package.get('distribution') or {}
        result.append({'id': ident, 'name': record['name'], 'kind': 'selected',
                       'installed_version': record['version'], 'installed_commit': (record.get('distribution') or {}).get('commit'),
                       'available_version': package['version'], 'available_commit': source.get('commit'),
                       'repository_url': source.get('repository_url'), 'download_ready': True,
                       'can_download': False, 'check_error': None, 'checked_at': None,
                       'changes': [{'version': package['version'], 'release_notes': package.get('release_notes') or NO_NOTES}]})
    return sorted(result, key=lambda row: (row['name'].casefold(), row['id']))
