import argparse
import serial
import struct

from serial.serialutil import Timeout


class BK7231Serial(object):
    COMMON_COMMAND_PREAMBLE = b"\x01\xe0\xfc"
    LONG_COMMAND_MARKER = b"\xff\xf4"

    RESPONSE_PREAMBLE = b"\x04\x0e"
    RESPONSE_START_MARKER = COMMON_COMMAND_PREAMBLE
    LONG_RESPONSE_MARKER = b"\xf4"

    COMMAND_TYPE_CHIPINFO = 0x11

    def __init__(self, device, baudrate, timeout=10.0):
        self.device = device
        self.baudrate = baudrate
        self.timeout = timeout
        self.__wait_for_link()

    def __wait_for_link(self):
        timeout = Timeout(self.timeout)
        while not timeout.expired():
            try:
                self.serial = serial.Serial(
                    port=self.device, baudrate=self.baudrate, timeout=self.timeout
                )
                payload = self.__build_payload_preamble(self.COMMAND_TYPE_CHIPINFO, 1)
                response_type, response_payload = self.__send_and_parse_response(
                    payload=payload
                )
                if response_type == self.COMMAND_TYPE_CHIPINFO:
                    self.chipinfo = response_payload
                    print(f"Connected! Chip info: {self.chipinfo}")
                    return True
            except:
                pass
        return False

    def __send_and_parse_response(self, payload):
        self.serial.write(payload)
        received_preamble = self.serial.read(2)

        if received_preamble != self.RESPONSE_PREAMBLE:
            raise ValueError(
                f"Failed to read response header, received preamble: {received_preamble.hex()}"
            )

        response_length = self.serial.read(1)
        response_type = 0
        long_command = response_length == 0xFF

        self.__read_until_dropping(self.RESPONSE_START_MARKER)
        if long_command:
            self.__read_until_dropping(self.LONG_RESPONSE_MARKER)
            response_length, response_type = struct.unpack("<HH", self.serial.read(2))
        else:
            response_type = self.serial.read(1)

        response_payload = self.serial.read(response_length)
        return response_type, response_payload

    def __read_until_dropping(self, marker):
        self.serial.read_until(marker)
        self.serial.read(len(marker))

    def __build_payload_preamble(self, payload_type, payload_length):
        payload = self.COMMON_COMMAND_PREAMBLE[::]
        if payload_length >= 0xFF:
            payload += self.LONG_COMMAND_MARKER
            payload += struct.pack("<H", payload_length)
        payload += struct.pack("B", payload_type)


def main():
    parser = argparse.ArgumentParser(
        prog="bk7231tools",
        description="Utility to interact with BK7231 chips over serial",
    )
    parser.add_argument("-d", "--device", required=True, help="Serial device path")
    parser.add_argument(
        "-b",
        "--baudrate",
        default=115200,
        help="Serial device baudrate (default: 115200)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Timeout for operations in seconds (default: 10.0)",
    )
    args = parser.parse_args()

    device = BK7231Serial(args.device, args.baudrate, args.timeout)
    print(device.chipinfo)


if __name__ == "__main__":
    main()
