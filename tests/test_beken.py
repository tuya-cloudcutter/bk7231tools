import unittest

from bk7231tools.analysis.beken import (
    BK7258_FLASH_BASE,
    add_crc,
    crc_packed_size,
    logical_to_physical,
    physical_to_logical,
)


class BekenCrcTest(unittest.TestCase):
    def test_add_crc_matches_beken_sdk_vector(self):
        data = bytes(range(32))

        self.assertEqual(data + b"\x25\x9d", add_crc(data))

    def test_add_crc_pads_last_block(self):
        packed = add_crc(b"123456789")

        self.assertEqual(34, len(packed))
        self.assertEqual(b"123456789" + b"\xff" * 23 + b"\x00\xb9", packed)

    def test_crc_packed_size(self):
        self.assertEqual(0, crc_packed_size(0))
        self.assertEqual(34, crc_packed_size(1))
        self.assertEqual(34, crc_packed_size(32))
        self.assertEqual(68, crc_packed_size(33))


class BekenAddressTest(unittest.TestCase):
    def test_logical_to_physical(self):
        self.assertEqual(0, logical_to_physical(BK7258_FLASH_BASE))
        self.assertEqual(0x11000, logical_to_physical(BK7258_FLASH_BASE + 0x10000))

    def test_physical_to_logical(self):
        self.assertEqual(BK7258_FLASH_BASE, physical_to_logical(0))
        self.assertEqual(BK7258_FLASH_BASE + 0x10000, physical_to_logical(0x11000))

    def test_address_alignment_is_required(self):
        with self.assertRaises(ValueError):
            logical_to_physical(BK7258_FLASH_BASE + 1)
        with self.assertRaises(ValueError):
            physical_to_logical(1)


if __name__ == "__main__":
    unittest.main()
