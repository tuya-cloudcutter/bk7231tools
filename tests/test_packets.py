import unittest
from io import BytesIO

from bk7231tools.serial.base.packets import (
    BkFlashEraseBlockCmnd,
    BkFlashRead4KCmnd,
    BkLinkCheckCmnd,
    BkLinkCheckResp,
    BkSetBaudRateCmnd,
    EraseSize,
)
from bk7231tools.serial.protocol import BK7231SerialProtocol


class PacketEncodingTest(unittest.TestCase):
    def test_link_check_packet(self):
        self.assertEqual(
            bytes.fromhex("01 e0 fc 01 00"),
            BK7231SerialProtocol.encode(BkLinkCheckCmnd()),
        )

    def test_set_baudrate_packet(self):
        self.assertEqual(
            bytes.fromhex("01 e0 fc 06 0f 00 08 07 00 14"),
            BK7231SerialProtocol.encode(BkSetBaudRateCmnd(460800, 20)),
        )

    def test_sector_read_packet(self):
        self.assertEqual(
            bytes.fromhex("01 e0 fc ff f4 05 00 09 00 30 12 00"),
            BK7231SerialProtocol.encode(BkFlashRead4KCmnd(0x123000)),
        )

    def test_sector_erase_packet(self):
        self.assertEqual(
            bytes.fromhex("01 e0 fc ff f4 06 00 0f 20 00 30 12 00"),
            BK7231SerialProtocol.encode(
                BkFlashEraseBlockCmnd(EraseSize.SECTOR_4K, 0x123000)
            ),
        )


class PacketDecodingTest(unittest.TestCase):
    def test_link_check_response(self):
        class FakeSerial:
            def __init__(self):
                self.input = BytesIO(bytes.fromhex("04 0e 05 01 e0 fc 01 00"))
                self.output = bytearray()

            def read(self, count=1):
                return self.input.read(count)

            def read_until(self, expected):
                output = bytearray()
                while not output.endswith(expected):
                    value = self.input.read(1)
                    if not value:
                        break
                    output.extend(value)
                return bytes(output)

            def write(self, data):
                self.output.extend(data)

            def flush(self):
                pass

        protocol = BK7231SerialProtocol()
        protocol.serial = FakeSerial()
        protocol.protocol_type = None

        response = protocol.command(BkLinkCheckCmnd())

        self.assertEqual(BkLinkCheckResp(0), response)
        self.assertEqual(bytes.fromhex("01 e0 fc 01 00"), protocol.serial.output)


if __name__ == "__main__":
    unittest.main()
