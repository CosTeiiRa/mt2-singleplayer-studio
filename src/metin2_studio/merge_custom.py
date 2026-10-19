"""Three-way byte-preserving merges. No file system or game writes."""
from dataclasses import dataclass
import difflib
import hashlib
import re


def edits(base, side):
    return [(a, b, side[c:d]) for tag, a, b, c, d in difflib.SequenceMatcher(None, base, side, autojunk=False).get_opcodes() if tag != 'equal']


def overlaps(a, b):
    x, y = a[:2], b[:2]
    if x[0] == x[1] or y[0] == y[1]:
        return max(x[0], y[0]) <= min(x[1], y[1])
    return max(x[0], y[0]) < min(x[1], y[1])


def render_region(base, start, end, changes):
    out, position = [], start
    for a, b, value in sorted(changes, key=lambda row: (row[0], row[1])):
        out += base[position:a] + value
        position = b
    return out + base[position:end]


@dataclass
class Choice:
    ident: str
    base: bytes | None
    custom: bytes | None
    incoming: bytes | None
    conflict: bool
    line: int
    context: str = ''


class Merge:
    def __init__(self, pieces):
        self.pieces = pieces

    @property
    def choices(self):
        return [piece for piece in self.pieces if isinstance(piece, Choice)]

    def resolve(self, decisions=None, require=True):
        decisions = decisions or {}
        if len(self.pieces) == 1 and isinstance(self.pieces[0], Choice):
            piece = self.pieces[0]
            decision = decisions.get(piece.ident, None if piece.conflict and require else 'keep')
            if decision not in ('keep', 'update'):
                raise ValueError('Choose Keep custom or Use update for every conflicting custom change.')
            return piece.custom if decision == 'keep' else piece.incoming
        out = []
        for piece in self.pieces:
            if isinstance(piece, Choice):
                decision = decisions.get(piece.ident, None if piece.conflict and require else 'keep')
                if decision not in ('keep', 'update'):
                    raise ValueError('Choose Keep custom or Use update for every conflicting custom change.')
                out.append((piece.custom if decision == 'keep' else piece.incoming) or b'')
            else:
                out.append(piece)
        return b''.join(out)


def choice_id(salt, index, base, custom, incoming):
    raw = b'\0'.join(value if value is not None else b'<missing>' for value in (base, custom, incoming))
    return hashlib.sha256(salt.encode() + str(index).encode() + raw).hexdigest()[:24]


def merge(base, custom, incoming, salt='', *, token=False, line_offset=0):
    """Only local modifications create choices. Unrelated incoming edits pass through.

    A line overlap is refined into tokens, allowing separate count/probability
    changes on the same reward row. Ambiguous structural edits remain conflicts.
    """
    if custom == incoming:
        return Merge([custom or b'']) if custom is not None else Merge([Choice(choice_id(salt, 0, base, custom, incoming), base, None, None, False, 1)])
    if custom == base:
        return Merge([incoming or b'']) if incoming is not None else Merge([Choice(choice_id(salt, 0, base, custom, incoming), base, None, None, False, 1)])
    if base is None or custom is None or incoming is None:
        piece = Choice(choice_id(salt, 0, base, custom, incoming), base, custom, incoming, incoming != base, 1)
        return Merge([piece])
    split = (lambda raw: re.findall(rb'\s+|[A-Za-z0-9_]+|[^\sA-Za-z0-9_]', raw)) if token else (lambda raw: raw.splitlines(keepends=True))
    original, ours, theirs = map(split, (base, custom, incoming))
    local = [(a, b, new, 'custom') for a, b, new in edits(original, ours)]
    remote = [(a, b, new, 'incoming') for a, b, new in edits(original, theirs)]
    clusters = []
    for edit in sorted(local + remote, key=lambda row: (row[0], row[1])):
        if clusters and any(overlaps(edit, previous) for previous in clusters[-1]):
            clusters[-1].append(edit)
        else:
            clusters.append([edit])
    pieces, position = [], 0
    for number, cluster in enumerate(clusters):
        start, end = min(row[0] for row in cluster), max(row[1] for row in cluster)
        pieces.append(b''.join(original[position:start]))
        our_changes = [row[:3] for row in cluster if row[3] == 'custom']
        their_changes = [row[:3] for row in cluster if row[3] == 'incoming']
        old = b''.join(original[start:end])
        our = b''.join(render_region(original, start, end, our_changes))
        their = b''.join(render_region(original, start, end, their_changes))
        line = line_offset + 1 + sum(value.count(b'\n') for value in original[:start])
        if not our_changes:
            pieces.append(their)
        elif our == their:
            pieces.append(our)
        elif not token and their_changes and len(old) + len(our) + len(their) <= 32000:
            nested = merge(old, our, their, salt + ':' + str(start), token=True, line_offset=line-1)
            for piece in nested.choices:
                piece.context = (old or our).decode('utf-8', 'replace').strip()[:500]
            pieces.extend(nested.pieces)
        else:
            context = b''.join(original[max(0, start-1):min(len(original), end+1)]) if not token else old
            pieces.append(Choice(choice_id(salt, (token, start, number), old, our, their), old, our, their, bool(their_changes), line, context.decode('utf-8', 'replace').strip()[:500]))
        position = end
    pieces.append(b''.join(original[position:]))
    return Merge(pieces)


def rebase_original(base, custom, incoming):
    """Remove known custom edits from the new observation, retaining new upstream work.

    If upstream now equals our desired value, retain the intent for later updates.
    An upstream value different from both sides becomes the new original.
    """
    reverse = merge(custom, base, incoming, 'rebase')
    return reverse.resolve({piece.ident: 'update' for piece in reverse.choices if piece.conflict})


def minimal_numeric_edit(original, changed):
    """Ignore drop-editor whitespace/comments/group-name rewrites when tracking intent.

    Non-structural numeric edits are applied to original byte spans. Structural
    edits retain the full renderer output and are merged conservatively.
    """
    if original is None or changed is None:
        return changed
    def tokens(raw):
        result = []
        offset = 0
        for line in raw.splitlines(keepends=True):
            code = line.split(b'#--#', 1)[0]
            if not code.lstrip().startswith(b'#'):
                matches = list(re.finditer(rb'[^\s{}]+|[{}]', code))
                if matches and matches[0].group().lower() == b'group':
                    matches = matches[:1]  # A display group name is not the logical key.
                result.extend((offset+m.start(), offset+m.end(), m.group()) for m in matches)
            offset += len(line)
        return result
    a, b = tokens(original), tokens(changed)
    numeric = re.compile(rb'[0-9]+(?:\.[0-9]+)?')
    if len(a) != len(b) or any(x[2].lower() != y[2].lower() and not (numeric.fullmatch(x[2]) and numeric.fullmatch(y[2])) for x, y in zip(a, b)):
        return changed
    out, position = [], 0
    for old, new in zip(a, b):
        if old[2] == new[2]:
            continue
        out += [original[position:old[0]], new[2]]
        position = old[1]
    return b''.join(out) + original[position:]
