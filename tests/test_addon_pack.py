import json
import struct
import unittest
import zlib

from metin2_studio.addons import client_pack as codec


@unittest.skipIf(codec.lzokay is None, 'Install optional add-on dependencies to exercise client pack checks.')
class PackTests(unittest.TestCase):
    def test_xtea_known_zero_vector(self):
        self.assertEqual(codec.xtea(b'\0' * 8, [0, 0, 0, 0]).hex(), 'd8d4e9ded91e13f7')

    def test_vectorized_and_scalar_paths_agree(self):
        raw = bytes(range(256)) * 2
        key = [1, 0xffffffff, 7, 9001]
        fast = codec.xtea(raw, key)
        old = codec.np
        try:
            codec.np = None
            scalar = codec.xtea(raw, key)
        finally:
            codec.np = old
        self.assertEqual(fast, scalar)
        self.assertEqual(codec.xtea(fast, key, decrypt=True), raw)

    def test_object_rejects_wrong_key_and_truncation(self):
        raw = b'hello pack' * 1000
        encoded = codec.encode_object(raw, [1, 2, 3, 4])
        self.assertEqual(codec.decode_object(encoded, [1, 2, 3, 4]), raw)
        with self.assertRaises(ValueError):
            codec.decode_object(encoded, [4, 3, 2, 1])
        with self.assertRaises(ValueError):
            codec.decode_object(encoded[:-8], [1, 2, 3, 4])

    def test_empty_namespace_initializer_round_trip(self):
        encoded = codec.encode_object(b'', [1, 2, 3, 4])
        self.assertEqual(codec.decode_object(encoded, [1, 2, 3, 4]), b'')

    def test_crc_and_entry_round_trip_with_virtual_asset(self):
        config = {'eter_pack_index_key': [1, 2, 3, 4], 'eter_pack_data_key': [8, 7, 6, 5]}
        empty = codec.EterPack(codec.encode_object(struct.pack('<4sII', b'EPKD', 2, 0), config['eter_pack_index_key']), b'', config)
        source = {'d:/ymir work/ui/example.tga': b'original synthetic asset', 'uiminimap.py': b'class AtlasWindow: pass\n'}
        index, data = empty.build(source)
        self.assertEqual(codec.EterPack(index, data, config).files(), source)
        broken = bytearray(data)
        broken[0] ^= 1
        with self.assertRaisesRegex(ValueError, 'CRC'):
            codec.EterPack(index, bytes(broken), config).files()

    def test_traversal_and_unsupported_version_rejected(self):
        for name in ('../../outside', '/absolute', 'd:/../escape', 'a//b', 'a:stream'):
            with self.assertRaises(ValueError):
                codec.logical_name(name)
        with self.assertRaises(ValueError):
            codec.EterPack(struct.pack('<4sII', b'EPKD', 999, 0), b'', {'eter_pack_index_key': [1]*4, 'eter_pack_data_key': [2]*4})
