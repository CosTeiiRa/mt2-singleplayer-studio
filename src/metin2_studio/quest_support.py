"""Quest-library source selection and reviewed compilation of edited game quests."""
import json
import re

MARKER = b'# SERVER-STUDIO CUSTOM QUESTS'
SOURCE_LIST = 'studio-source-list.txt'


def quest_name(raw):
    match = re.search(rb'(?m)^[ \t]*quest\s+([A-Za-z_][A-Za-z0-9_]*)\s+begin\b', raw or b'')
    return match[1].decode('ascii') if match else None


def registered_sources(studio):
    raw = studio.read(studio.game / 'custom-quests' / SOURCE_LIST) or b''
    paths = []
    for line in raw.decode('ascii').splitlines():
        if not line or line.startswith('#'):
            continue
        if not re.fullmatch(r'(?:quest/|share/locale/poland/quest/quest/)[A-Za-z0-9_./-]+\.quest', line) or '..' in line.split('/'):
            raise ValueError('The edited quest source list contains an unsupported path. Review ' + SOURCE_LIST + '.')
        paths.append(line)
    return sorted(set(paths))


def build_changes(studio, sources=None):
    """The hook compiles generated quests and exact, registered native source files."""
    sources = registered_sources(studio) if sources is None else sorted(set(sources))
    dockerfile, ignore = studio.game / 'Dockerfile', studio.game / '.dockerignore'
    raw = studio.read(dockerfile)
    stage = re.search(rb'(?m)^FROM [^\r\n]+ AS runtime\r?$', raw)
    if not stage or b'/tmp/qc-work' not in raw or b'/out-quest/poland/quest' not in raw:
        raise ValueError('The installed quest build changed. Inspect its compiler stage before saving quest integration.')
    identities = {path: quest_name(studio.read(studio.game / path)) for path in sources}
    if None in identities.values() or len(set(identities.values())) != len(identities):
        raise ValueError('Each registered source must have one distinct, valid quest identity.')
    copies = ''.join('COPY ' + json.dumps([path, '/studio-edited/' + identities[path] + '.quest']) + '\n' for path in sources)
    hook = '# SERVER-STUDIO CUSTOM QUESTS\n# Studio quest integration v2\nCOPY custom-quests/ /studio-quests/\n' + copies + r'''RUN set -eu; cd /tmp/qc-work; \
    compile_studio_quest() { \
      src="$1"; name=$(basename "$src"); sed 's/\r$//' "$src" > "$name"; \
      quest_name="${name%.quest}"; \
      test -n "$quest_name"; \
      find object -type f \( -name "$quest_name.*" -o -path "object/state/$quest_name" \) -delete; \
      /usr/local/bin/qc "$name"; \
      test -s "object/state/$quest_name"; cp "$name" /out-quest/poland/quest/; \
    }; \
    for src in /studio-quests/studio_*.quest /studio-edited/*.quest; do \
      [ -f "$src" ] || continue; compile_studio_quest "$src"; \
    done; \
    cp -a object /out-quest/poland/quest/; \
    chmod -R a+rX /out-quest/poland/quest

'''
    if 'mounts_legacy' in identities.values():
        compile_line = '      /usr/local/bin/qc "$name"; \\\n'
        mount_functions = '''      if [ "$quest_name" = "mounts_legacy" ]; then cp quest_functions quest_functions.studio-mount-before; grep -qx 'pc.get_point' quest_functions || printf '%s\\n' 'pc.get_point' >> quest_functions; fi; \\
'''
        restore_functions = '''      if [ "$quest_name" = "mounts_legacy" ]; then mv quest_functions.studio-mount-before quest_functions; fi; \\
'''
        hook = hook.replace(compile_line, mount_functions + compile_line + restore_functions, 1)
    start = raw.index(MARKER) if MARKER in raw else stage.start()
    if start > stage.start():
        raise ValueError('The Studio quest hook is outside the compiler stage. Review the Dockerfile first.')
    runtime = raw[stage.start():]
    runtime = re.sub(rb'(?ms)^# SERVER-STUDIO EDITED QUEST CLEANUP\r?\n.*?^# END SERVER-STUDIO EDITED QUEST CLEANUP\r?\n', b'', runtime)
    if sources:
        copy_marker = b'COPY --from=quests /out-quest/ /opt/metin2/share/locale/'
        if copy_marker not in runtime:
            raise ValueError('The runtime quest installation step changed. Inspect the package build before editing native quests.')
        cleanup = '# SERVER-STUDIO EDITED QUEST CLEANUP\nRUN set -eu; '
        cleanup += '; '.join('find /opt/metin2/share/locale/poland/quest/object -type f \\( -name "' + identity + '.*" -o -path "*/state/' + identity + '" \\) -delete' for identity in sorted(identities.values()))
        cleanup += '\n# END SERVER-STUDIO EDITED QUEST CLEANUP\n'
        runtime = runtime.replace(copy_marker, cleanup.encode('ascii') + copy_marker, 1)
    changes = {dockerfile: raw[:start] + hook.encode('ascii') + runtime}
    ignore_raw = studio.read(ignore) or b''
    required = ['!custom-quests', '!custom-quests/**']
    # Protected packages use an explicit context allowlist. Include each parent and selected source only.
    for path in sources:
        parts = path.split('/')
        required += ['!' + '/'.join(parts[:index]) for index in range(1, len(parts) + 1)]
    present = set(ignore_raw.decode('utf-8', 'replace').splitlines())
    missing = list(dict.fromkeys(line for line in required if line not in present))
    if missing:
        changes[ignore] = ignore_raw + b'\n# Server Studio quests\n' + ('\n'.join(missing) + '\n').encode('ascii')
    return changes


def source_changes(studio, path, raw):
    old = studio.read(path)
    if old == raw:
        raise ValueError('There are no changes to save.')
    identity = quest_name(old)
    if not identity or quest_name(raw) != identity:
        raise ValueError('Keep the existing quest name to preserve character progress. Use New quest for a different quest.')
    changes = {path: raw}
    if path.parent != studio.game / 'custom-quests':
        rel = path.relative_to(studio.game).as_posix()
        if not (path.parent == studio.game / 'quest' or path.is_relative_to(studio.locale / 'quest/quest')):
            raise ValueError('This quest source is outside the supported native quest folders.')
        if not re.fullmatch(r'[A-Za-z0-9_./-]+\.quest', rel):
            raise ValueError('This quest filename cannot be registered by the current compiler integration.')
        sources = registered_sources(studio)
        for existing in sources:
            if existing != rel and quest_name(studio.read(studio.game / existing)) == identity:
                raise ValueError('This quest already has an edited source. Open ' + existing + ' from the quest menu.')
        sources = sorted(set(sources + [rel]))
        manifest = studio.game / 'custom-quests' / SOURCE_LIST
        changes[manifest] = ('# Existing quest sources compiled after package quests.\n' + '\n'.join(sources) + '\n').encode('ascii')
        changes.update(build_changes(studio, sources))
    else:
        changes.update(build_changes(studio))
    return changes


def source_plan(studio, path, raw):
    changes = source_changes(studio, path, raw)
    return studio.plan('Update quest: ' + quest_name(raw), changes,
                       'The original quest identity and progress are retained. Review the source and compiler integration. Apply compiles the edited quest after package quests; a failed build does not restart the game.')


def describe_library(studio, rows):
    registered = set(registered_sources(studio))
    groups = {}
    for row in rows:
        path = studio.root / row['id']
        identity = quest_name(studio.read(path)) or path.stem
        rel = path.relative_to(studio.game).as_posix()
        rank = 0 if rel in registered else 1 if path.parent == studio.game / 'custom-quests' else 2 if path.parent == studio.game / 'quest' else 3
        row.update(questName=identity, origin='studio' if path.parent == studio.game / 'custom-quests' else 'game',
                   editMode='builder' if row['template'] else 'source', compileRegistered=rel in registered,
                   staged=not path.exists() or path.read_bytes() != studio.read(path), sourceLabel='Package quest' if path.parent == studio.game / 'quest' else 'Game source')
        if not row['template']:
            research = re.fullmatch(r'collect_quest_lv(\d+)', identity)
            herbs = re.fullmatch(r'(?:collect|make)_herb_lv(\d+)', identity)
            story = re.fullmatch(r'main_quest_lv(\d+)', identity)
            if research:
                row['title'] = 'Biologist research · Level ' + research[1]
            elif herbs:
                row['title'] = 'Biologist herbs · Level ' + herbs[1]
            elif story:
                row['title'] = 'Main story · Level ' + story[1]
            elif identity == 'hunting':
                row['title'] = 'Hunting quests'
        groups.setdefault(identity, []).append((rank, row))
    result = []
    for copies in groups.values():
        copies.sort(key=lambda pair: (pair[0], pair[1]['id']))
        row = copies[0][1]
        row['otherSources'] = [copy['id'] for _, copy in copies[1:]]
        result.append(row)
    def order(row):
        adventure = row['questName'].startswith(('collect_', 'make_herb_', 'main_quest_', 'subquest_', 'horse_', 'pony_')) or row['questName'] == 'hunting'
        return (0 if row['origin']=='studio' else 1 if adventure else 2,
                [int(part) if part.isdigit() else part.casefold() for part in re.split(r'(\d+)', row['title'])], row['id'])
    return sorted(result, key=order)
