"""Synthetic pack tests; installed game files are never modified."""
import copy
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from metin2_studio.addons import client_pack, mounts_client as mounts


@unittest.skipUnless(client_pack.lzokay is not None, 'lzokay is required')
class MountClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.client = self.root / 'Klient'
        (self.client / 'pack').mkdir(parents=True)
        names = ['vnum', 'name', 'locale_name', *mounts.ITEM_INVARIANTS, *mounts.ITEM_FIXES, 'padding']
        self.codec = {'PACK_INDEX_KEY': [1, 2, 3, 4], 'PACK_DATA_KEY': [5, 6, 7, 8],
                      'ITEM_PROTO_KEY': [9, 10, 11, 12], 'ITEM_NAMES': names,
                      'ITEM_STRUCT': struct.Struct('<I16s16s' + 'I' * 14 + '92s')}
        self.config = mounts._pack_config(self.codec)
        self.row = {name: 0 for name in names}
        self.row.update(vnum=71128, name=b'legacy\xff', locale_name=b'seal\x80', padding=b'\xa7' * 92)
        self.row.update(mounts.ITEM_INVARIANTS)
        self.row.update({name: before for name, (before, _) in mounts.ITEM_FIXES.items()})
        other = dict(self.row, vnum=42, name=b'unrelated')
        self.logical = {mounts.NPC_MEMBER: b'# preserve comments\r\n0\tdisabled\r\n0\talso_disabled\r\n' +
                        b''.join(('%d\t%s \r\n' % (ident, names[0])).encode() for ident, names in mounts.NPC_FIXES.items()) +
                        b'20119\tchristmas_2016_mammoth_01\r\n',
                        mounts.ITEM_MEMBER: mounts._write_rows([self.row, other], self.codec),
                        'gamedata/mob_proto': bytes(range(256)) * 3,
                        'gamedata/unrelated.txt': b'unchanged object\r\n'}
        self.write_pack('gamedata', self.logical)
        self.assets = {}
        for _, appearance in mounts.NPC_FIXES.values():
            folder = 'd:/ymir work/npc/' + appearance + '/'
            self.assets[folder + appearance + '.msm'] = ('BaseModelFileName "' + appearance + '.gr2"\n').encode()
            self.assets[folder + appearance + '.gr2'] = b'synthetic mesh'
            self.assets[folder + 'motlist.txt'] = b''.join(('GENERAL %s %s.msa 100\n' % (kind, kind.lower())).encode()
                                                         for kind in ('WAIT', 'WALK', 'RUN', 'COMBO_ATTACK'))
            for kind in ('wait', 'walk', 'run', 'combo_attack'):
                self.assets[folder + kind + '.msa'] = ('MotionFileName "' + kind + '.gr2"\n').encode()
                self.assets[folder + kind + '.gr2'] = b'synthetic animation'
        self.write_pack('npc', self.assets)
        self.write_pack('root', {'root/unchanged.py': b'print("untouched")\n'})
        (self.client / 'metin2client.exe').write_bytes(b'executable must remain unchanged')
        (self.client / 'pack/Index').write_bytes(b'PACK\n*\nroot\n*\ngamedata\n*\nnpc\n')

    def write_pack(self, name, logical):
        seed = client_pack.EterPack(struct.pack('<4sII', b'EPKD', 2, 0), b'', self.config)
        index, data = seed.build(logical)
        (self.client / ('pack/' + name + '.index')).write_bytes(index)
        (self.client / ('pack/' + name + '.data')).write_bytes(data)

    def snapshot(self):
        return {p.relative_to(self.client).as_posix(): p.read_bytes() for p in self.client.rglob('*') if p.is_file()}

    def plan(self, *args, **kwargs):
        before = self.snapshot()
        result = mounts.plan_client_fixes(self.client, *args, codec=self.codec, **kwargs)
        self.assertEqual(before, self.snapshot(), 'Planning wrote to the selected client')
        return result

    def decoded(self, outputs):
        return client_pack.EterPack(*(outputs[name] for name in mounts.PACK_FILES), self.config).files()

    def install(self, outputs):
        for name, raw in outputs.items():
            (self.client / name).write_bytes(raw)

    def test_only_reviewed_records_and_two_members_change(self):
        result = self.plan(model_requests=[20110, 20111, 20112, 20119])
        self.assertTrue(result['can_apply'], result['conflicts'])
        self.assertEqual(len(result['changes']), 8)
        self.assertEqual(set(result['outputs']), set(mounts.PACK_FILES))
        logical = self.decoded(result['outputs'])
        self.assertEqual({key for key in logical if logical[key] != self.logical[key]}, {mounts.NPC_MEMBER, mounts.ITEM_MEMBER})
        rows = mounts._item_rows(logical[mounts.ITEM_MEMBER], self.codec)
        original = mounts._item_rows(self.logical[mounts.ITEM_MEMBER], self.codec)
        self.assertEqual(rows[1], original[1])
        self.assertEqual({key for key in rows[0] if rows[0][key] != original[0][key]}, set(mounts.ITEM_FIXES))
        self.assertEqual(result['asset_availability'], {20110: True, 20111: True, 20112: True, 20119: False})
        self.assertEqual(logical[mounts.NPC_MEMBER].splitlines(keepends=True)[:3], self.logical[mounts.NPC_MEMBER].splitlines(keepends=True)[:3])
        before_pack = client_pack.EterPack(*(self.snapshot()[name] for name in mounts.PACK_FILES), self.config)
        after_pack = client_pack.EterPack(*(result['outputs'][name] for name in mounts.PACK_FILES), self.config)
        for key in ('gamedata/mob_proto', 'gamedata/unrelated.txt'):
            a, b = before_pack.entries[key], after_pack.entries[key]
            self.assertEqual(before_pack.data_bytes[a['position']:a['position'] + a['size']],
                             after_pack.data_bytes[b['position']:b['position'] + b['size']])

    def test_already_correct_has_no_outputs_and_owns_nothing(self):
        self.install(self.plan()['outputs'])
        result = self.plan()
        self.assertTrue(result['can_apply'])
        self.assertEqual(result['status'], 'already-provided')
        self.assertEqual(result['outputs'], {})
        self.assertEqual(result['ownership']['mappings'], [])
        self.assertEqual(result['ownership']['item_fields'], [])

    def test_individual_game_provided_fields_are_not_owned(self):
        rows = mounts._item_rows(self.logical[mounts.ITEM_MEMBER], self.codec)
        rows[0]['subtype'] = 2
        self.logical[mounts.ITEM_MEMBER] = mounts._write_rows(rows, self.codec)
        self.write_pack('gamedata', self.logical)
        result = self.plan()
        self.assertTrue(result['can_apply'])
        self.assertNotIn('subtype', {row['field'] for row in result['ownership']['item_fields']})

    def test_unknown_item_field_blocks_entire_plan(self):
        rows = mounts._item_rows(self.logical[mounts.ITEM_MEMBER], self.codec)
        rows[0]['value5'] = 999
        self.logical[mounts.ITEM_MEMBER] = mounts._write_rows(rows, self.codec)
        self.write_pack('gamedata', self.logical)
        result = self.plan()
        self.assertFalse(result['can_apply'])
        self.assertIn('value5', ' '.join(result['conflicts']))
        self.assertEqual(result['outputs'], {})
        self.assertEqual(result['changes'], [])

    def test_unknown_or_duplicate_relevant_mapping_is_a_conflict(self):
        for tail in (b'20110\tboar\r\n', b''):
            with self.subTest(duplicate=bool(tail)):
                data = self.logical[mounts.NPC_MEMBER] + tail if tail else self.logical[mounts.NPC_MEMBER].replace(b'horse2_king_normal', b'custom_model')
                self.write_pack('gamedata', dict(self.logical, **{mounts.NPC_MEMBER: data}))
                result = self.plan()
                self.assertFalse(result['can_apply'])
                self.assertEqual(result['outputs'], {})

    def test_missing_intended_motion_does_not_substitute_model(self):
        del self.assets['d:/ymir work/npc/boar/run.gr2']
        self.write_pack('npc', self.assets)
        result = self.plan()
        self.assertFalse(result['can_apply'])
        self.assertFalse(result['asset_availability'][20110])
        self.assertIn('run.gr2', result['assets']['20110']['reason'])
        self.assertEqual(result['outputs'], {})

    def test_ambiguous_asset_definition_is_not_selected(self):
        conflicting = dict(self.assets)
        conflicting['d:/ymir work/npc/boar/boar.msm'] += b'# conflicting definition\n'
        self.write_pack('patch', conflicting)
        result = self.plan()
        self.assertFalse(result['can_apply'])
        self.assertIn('Ambiguous', result['assets']['20110']['reason'])

    def test_exact_baseline_rollback_and_unchanged_reapply_ownership(self):
        before = {name: self.snapshot()[name] for name in mounts.PACK_FILES}
        applied = self.plan()
        self.install(applied['outputs'])
        again = self.plan('reapply', ownership=applied['ownership'])
        self.assertEqual(again['ownership'], applied['ownership'])
        reverted = self.plan('remove', ownership=applied['ownership'], baseline=before)
        self.assertTrue(reverted['can_apply'], reverted['conflicts'])
        self.assertEqual(reverted['outputs'], before)

    def test_disable_enable_uses_restored_pair_as_new_baseline(self):
        baseline = {name: self.snapshot()[name] for name in mounts.PACK_FILES}
        applied = self.plan()
        self.install(applied['outputs'])
        disabled = self.plan('disable', ownership=applied['ownership'], baseline=baseline)
        self.assertTrue(disabled['can_apply'], disabled['conflicts'])
        self.install(disabled['outputs'])
        enabled = self.plan('enable', ownership=disabled['ownership'], baseline=applied['outputs'])
        self.assertTrue(enabled['can_apply'], enabled['conflicts'])
        self.assertEqual(enabled['ownership']['before_sha256'], {name: mounts.sha(raw) for name, raw in baseline.items()})
        self.install(enabled['outputs'])
        removed = self.plan('remove', ownership=enabled['ownership'], baseline=baseline)
        self.assertTrue(removed['can_apply'], removed['conflicts'])
        self.assertEqual(removed['outputs'], baseline)

    def test_exact_rollback_preserves_original_inner_proto_encoding(self):
        rows = mounts._item_rows(self.logical[mounts.ITEM_MEMBER], self.codec)
        raw = b''.join(self.codec['ITEM_STRUCT'].pack(*(row[name] for name in self.codec['ITEM_NAMES'])) for row in rows)
        encoded = client_pack.encode_object(raw, self.codec['ITEM_PROTO_KEY'], encrypt=False) + bytes(4)
        alternative = struct.pack('<4sIIII', b'MIPX', 1, 184, len(rows), len(encoded)) + encoded
        self.assertNotEqual(alternative, self.logical[mounts.ITEM_MEMBER])
        self.logical[mounts.ITEM_MEMBER] = alternative
        self.write_pack('gamedata', self.logical)
        baseline = {name: self.snapshot()[name] for name in mounts.PACK_FILES}
        applied = self.plan()
        self.assertTrue(applied['can_apply'], applied['conflicts'])
        self.install(applied['outputs'])
        removed = self.plan('remove', ownership=applied['ownership'], baseline=baseline)
        self.assertTrue(removed['can_apply'], removed['conflicts'])
        self.assertEqual(removed['outputs'], baseline)

    def test_inverse_removal_preserves_new_game_and_unrelated_changes(self):
        before = {name: self.snapshot()[name] for name in mounts.PACK_FILES}
        applied = self.plan()
        newer = self.decoded(applied['outputs'])
        newer['gamedata/unrelated.txt'] = b'updated game and user change\n'
        newer['gamedata/new.txt'] = b'new upstream object'
        self.write_pack('gamedata', newer)
        reverted = self.plan('remove', ownership=applied['ownership'], baseline=before)
        self.assertTrue(reverted['can_apply'], reverted['conflicts'])
        final = self.decoded(reverted['outputs'])
        self.assertEqual(final['gamedata/new.txt'], b'new upstream object')
        self.assertEqual(final['gamedata/unrelated.txt'], newer['gamedata/unrelated.txt'])
        self.assertEqual(final[mounts.NPC_MEMBER], self.logical[mounts.NPC_MEMBER])
        self.assertEqual(mounts._item_rows(final[mounts.ITEM_MEMBER], self.codec), mounts._item_rows(self.logical[mounts.ITEM_MEMBER], self.codec))

    def test_updated_game_correct_fields_become_game_owned_on_reapply(self):
        applied = self.plan()
        newer = self.decoded(applied['outputs'])
        newer['gamedata/unrelated.txt'] = b'updated game release'
        self.write_pack('gamedata', newer)
        result = self.plan('reapply', ownership=applied['ownership'])
        self.assertTrue(result['can_apply'])
        self.assertEqual(result['ownership']['mappings'], [])
        self.assertEqual(result['ownership']['item_fields'], [])
        self.assertEqual(self.plan('remove', ownership=result['ownership'])['outputs'], {})

    def test_removal_refuses_to_overwrite_changed_owned_field(self):
        applied = self.plan()
        logical = self.decoded(applied['outputs'])
        rows = mounts._item_rows(logical[mounts.ITEM_MEMBER], self.codec)
        rows[0]['value0'] = 555
        logical[mounts.ITEM_MEMBER] = mounts._write_rows(rows, self.codec)
        self.write_pack('gamedata', logical)
        result = self.plan('remove', ownership=applied['ownership'])
        self.assertFalse(result['can_apply'])
        self.assertEqual(result['outputs'], {})

    def test_receipt_cannot_choose_arbitrary_records_or_values(self):
        receipt = self.plan()['ownership']
        for mutation in ('id', 'field', 'value', 'duplicate', 'extra'):
            bad = copy.deepcopy(receipt)
            if mutation == 'id': bad['mappings'][0]['vnum'] = 20119
            if mutation == 'field': bad['item_fields'][0]['field'] = 'wearflag'
            if mutation == 'value': bad['item_fields'][1]['after'] = True
            if mutation == 'duplicate': bad['mappings'].append(bad['mappings'][0])
            if mutation == 'extra': bad['mappings'][0]['path'] = '../../outside'
            with self.subTest(mutation=mutation):
                self.assertFalse(self.plan('remove', ownership=bad)['can_apply'])

    def test_guards_detect_pack_change_and_new_asset_index(self):
        plan = self.plan()
        mounts.verify_client_guards(self.client, plan)
        self.write_pack('newpatch', {})
        with self.assertRaisesRegex(ValueError, 'inventory changed'):
            mounts.verify_client_guards(self.client, plan)
        (self.client / 'pack/newpatch.index').unlink()
        (self.client / 'pack/newpatch.data').unlink()
        (self.client / 'pack/npc.data').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'changed since review'):
            mounts.verify_client_guards(self.client, plan)

    def test_unreviewed_installed_python_is_never_executed(self):
        server = self.root / 'Serwer/files'
        server.mkdir(parents=True)
        marker = self.root / 'executed'
        (server / 'client_protos.py').write_text('from pathlib import Path\nPath(%r).touch()\n' % str(marker))
        result = mounts.inspect_client_fixes(self.client)
        self.assertFalse(result['can_apply'])
        self.assertIn('unreviewed', ' '.join(result['conflicts']))
        self.assertFalse(marker.exists())

    def test_reviewed_codec_reads_only_literals_without_execution(self):
        server = self.root / 'Serwer/files'
        server.mkdir(parents=True)
        marker = self.root / 'executed'
        fields = [('vnum', 'I'), ('name', '16s'), ('locale_name', '16s')]
        fields += [(name, 'I') for name in [*mounts.ITEM_INVARIANTS, *mounts.ITEM_FIXES]]
        fields += [('padding', '92s')]
        raw = ''.join('%s = %r\n' % (key, self.codec[key]) for key in ('PACK_INDEX_KEY', 'PACK_DATA_KEY', 'ITEM_PROTO_KEY'))
        raw += 'ITEM_FIELDS = %r\n' % fields
        raw += 'from pathlib import Path\nPath(%r).touch()\n' % str(marker)
        path = server / 'client_protos.py'
        path.write_bytes(raw.encode())
        with patch.object(mounts, 'CODEC_SHA256', {mounts.sha(path.read_bytes())}):
            result = mounts.inspect_client_fixes(self.client)
        self.assertTrue(result['can_apply'], result['conflicts'])
        self.assertFalse(marker.exists())
        self.assertEqual(result['external_guards'][0]['path'], str(path))

    def test_stored_gamedata_crc_failure_prevents_output(self):
        path = self.client / 'pack/gamedata.data'
        original = path.read_bytes()
        path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
        result = self.plan()
        self.assertFalse(result['can_apply'])
        self.assertIn('CRC', ' '.join(result['conflicts']))
        self.assertEqual(result['outputs'], {})

    def test_parent_traversal_guard_is_rejected(self):
        with self.assertRaises(ValueError):
            mounts._regular(self.client / 'pack/../pack/gamedata.index', self.client)


if __name__ == '__main__':
    unittest.main()
