import unittest
from unittest.mock import Mock, patch

from bk7231tools.serial.main import BK7231Serial
from bk7231tools.serial.protocol import BK7231SerialProtocol


class ResetSequenceTest(unittest.TestCase):
    def setUp(self):
        self.protocol = BK7231SerialProtocol()
        self.protocol.reset_hold = 0.1

    def test_rts_only_sequence(self):
        self.protocol.reset_mode = "rts"

        self.assertEqual(
            [(0.0, True, None), (0.1, False, None)],
            self.protocol.hw_reset_steps(),
        )

    def test_legacy_dtr_rts_sequence(self):
        self.protocol.reset_mode = "dtr-rts"

        self.assertEqual(
            [
                (0.0, True, True),
                (0.1, None, False),
                (0.2, False, None),
            ],
            self.protocol.hw_reset_steps(),
        )

    def test_no_reset_sequence(self):
        self.protocol.reset_mode = "none"

        self.assertEqual([], self.protocol.hw_reset_steps())

    def test_rts_only_release_does_not_change_dtr(self):
        calls = []
        self.protocol.reset_mode = "rts"
        self.protocol.hw_reset_apply = lambda rts, dtr: calls.append((rts, dtr))

        self.protocol.hw_reset_release()

        self.assertEqual([(False, None)], calls)


class SerialOpenTest(unittest.TestCase):
    @patch("bk7231tools.serial.main.Serial")
    def test_rts_mode_releases_control_lines_before_open(self, serial_class):
        serial = Mock()
        serial_class.return_value = serial

        def check_open_state():
            self.assertIs(serial.rts, False)
            self.assertIs(serial.dtr, False)
            self.assertEqual("COM7", serial.port)

        serial.open.side_effect = check_open_state

        BK7231Serial("COM7", reset_mode="rts")

        serial_class.assert_called_once_with(
            port=None,
            baudrate=115200,
            timeout=1.0,
        )
        serial.open.assert_called_once_with()

    @patch("bk7231tools.serial.main.Serial")
    def test_legacy_mode_opens_port_directly(self, serial_class):
        serial = Mock()
        serial_class.return_value = serial

        BK7231Serial("COM7", reset_mode="dtr-rts")

        serial_class.assert_called_once_with(
            port="COM7",
            baudrate=115200,
            timeout=1.0,
        )
        serial.open.assert_not_called()

    @patch("bk7231tools.serial.main.Serial")
    def test_no_reset_mode_releases_control_lines_before_open(self, serial_class):
        serial = Mock()
        serial_class.return_value = serial

        BK7231Serial("COM7", reset_mode="none")

        serial_class.assert_called_once_with(
            port=None,
            baudrate=115200,
            timeout=1.0,
        )
        self.assertIs(serial.rts, False)
        self.assertIs(serial.dtr, False)
        serial.open.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
