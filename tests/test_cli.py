import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import Mock, mock_open, patch

from bk7231tools.__main__ import cli, connect_device, read_flash
from bk7231tools.serial.base import BkChipType, BkProtocolType


class SerialDefaultsTest(unittest.TestCase):
    def make_device(self):
        device = Mock()
        device.chip_info = "test"
        device.flash_id = b"\xc8\x40\x16"
        device.flash_size = 0x400000
        device.chip_type = BkChipType.BK7231N
        device.protocol_type = BkProtocolType.FULL
        return device

    @patch("bk7231tools.__main__.BK7231Serial")
    def test_bk7258_defaults(self, serial_cls):
        device = self.make_device()
        serial_cls.return_value = device

        result = connect_device("/dev/test", None, 10.0, False, chip="bk7258")

        serial_cls.assert_called_once_with(
            "/dev/test",
            460800,
            link_timeout=10.0,
            link_read_timeout=0.005,
            chip_type=BkChipType.BK7258,
            reset_mode="rts",
            reset_hold=0.1,
        )
        device.connect.assert_called_once_with(reset=True)
        self.assertIs(device, result)

    @patch("bk7231tools.__main__.BK7231Serial")
    def test_legacy_defaults_are_unchanged(self, serial_cls):
        device = self.make_device()
        serial_cls.return_value = device

        connect_device("/dev/test", None, 10.0, False)

        serial_cls.assert_called_once_with(
            "/dev/test",
            115200,
            link_timeout=10.0,
            link_read_timeout=0.005,
            chip_type=None,
            reset_mode="dtr-rts",
            reset_hold=0.1,
        )

    @patch("bk7231tools.__main__.connect_device", side_effect=TimeoutError("link"))
    @patch("bk7231tools.__main__.parse_args")
    def test_timeout_exits_with_failure(self, parse_args, connect_device):
        parse_args.return_value = Mock(
            device_required=True,
            device="/dev/test",
            baudrate=None,
            timeout=10.0,
            debug=False,
            link_read_timeout=5.0,
            chip="bk7258",
            reset_mode="rts",
            reset_hold=0.1,
        )

        with redirect_stderr(io.StringIO()), self.assertRaisesRegex(SystemExit, "1"):
            cli()

    def test_read_rejects_start_past_detected_flash(self):
        device = self.make_device()
        device.chip_type = BkChipType.BK7258
        args = Mock(
            deprecated_start=None,
            deprecated_count=None,
            file="unused.bin",
            length=None,
            no_verify_checksum=False,
            start=device.flash_size + 1,
        )

        with self.assertRaisesRegex(SystemExit, "1"):
            read_flash(device, args)

    @patch("builtins.open", new_callable=mock_open)
    def test_bk7258_read_defaults_to_detected_flash(self, open_file):
        device = self.make_device()
        device.chip_type = BkChipType.BK7258
        device.flash_read.return_value = []
        args = Mock(
            deprecated_start=None,
            deprecated_count=None,
            file="bk7258.bin",
            length=None,
            no_verify_checksum=False,
            start=0,
        )

        read_flash(device, args)

        device.flash_read.assert_called_once_with(0, 0x400000, True)
        open_file.assert_called_once_with("bk7258.bin", "wb")

    @patch("builtins.open", new_callable=mock_open)
    def test_legacy_read_default_remains_two_mib(self, open_file):
        device = self.make_device()
        device.flash_read.return_value = []
        args = Mock(
            deprecated_start=None,
            deprecated_count=None,
            file="bk7231.bin",
            length=None,
            no_verify_checksum=False,
            start=0,
        )

        read_flash(device, args)

        device.flash_read.assert_called_once_with(0, 0x200000, True)
        open_file.assert_called_once_with("bk7231.bin", "wb")


if __name__ == "__main__":
    unittest.main()
