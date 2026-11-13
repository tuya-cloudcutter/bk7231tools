import unittest
from io import BytesIO

from bk7231tools.serial.base import BkChipType, BkProtocolType
from bk7231tools.serial.cmd_hl_flash import BK7231SerialCmdHLFlash


class FlashProtectionTest(unittest.TestCase):
    def test_unprotect_returns_original_state(self):
        device = BK7231SerialCmdHLFlash()
        writes = []
        device.flash_read_id = lambda: {"id": b"\x0b\x40\x16"}
        device.flash_read_sr = lambda size: 0x427C
        device.flash_write_sr = lambda sr, size, mask: writes.append((sr, size, mask))

        state = device.flash_unprotect()

        self.assertEqual((2, 0x427C, 0x407C), state)
        self.assertEqual([(0x0200, 2, 0x407C)], writes)

    def test_restore_changes_only_protection_bits(self):
        device = BK7231SerialCmdHLFlash()
        writes = []
        device.flash_read_sr = lambda size: 0x0200
        device.flash_write_sr = lambda sr, size, mask: writes.append((sr, size, mask))

        device.flash_restore_protection((2, 0x427C, 0x407C))

        self.assertEqual([(0x427C, 2, 0x407C)], writes)

    def test_programming_error_still_restores_protection(self):
        class FailingDevice(BK7231SerialCmdHLFlash):
            protocol_type = BkProtocolType.FULL
            chip_type = BkChipType.BK7258

            def __init__(self):
                self.restored = None

            def flash_unprotect(self, mask=0x407C):
                return (2, 0x427C, mask)

            def flash_restore_protection(self, state):
                self.restored = state

            def _program_flash_unprotected(self, *args, **kwargs):
                raise ValueError("write failed")
                yield 0

        device = FailingDevice()

        with self.assertRaisesRegex(ValueError, "write failed"):
            list(device.program_flash(BytesIO(b"data"), 4, 0))

        self.assertEqual((2, 0x427C, 0x407C), device.restored)


if __name__ == "__main__":
    unittest.main()
