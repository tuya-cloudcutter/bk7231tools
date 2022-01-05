import argparse
import sys
from typing import List
import serial
import struct
import contextlib
import traceback

from serial.serialutil import SerialException, Timeout


class BK7231Serial(object):
    COMMON_COMMAND_PREAMBLE = b"\x01\xe0\xfc"
    LONG_COMMAND_MARKER = b"\xff\xf4"

    RESPONSE_PREAMBLE = b"\x04\x0e"
    RESPONSE_START_MARKER = COMMON_COMMAND_PREAMBLE
    LONG_RESPONSE_MARKER = b"\xf4"

    COMMAND_TYPE_CHIPINFO = 0x11
    COMMAND_TYPE_READFLASH4K = 0x09

    def __init__(self, device, baudrate, timeout=10.0):
        self.device = device
        self.baudrate = baudrate
        self.timeout = timeout
        if not self.__wait_for_link():
            raise TimeoutError("Timed out attempting to link with chip")

    def close(self):
        if self.serial and not self.serial.closed:
            self.serial.close()

    def read_flash_4k(self, start_addr, segment_count=1):
        if (start_addr & 0xFFF) != 0:
            raise ValueError(f"Starting address {start_addr:#x} is not 4K aligned")
        if start_addr < 0x10000:
            raise ValueError(
                f"Starting address {start_addr:#x} is smaller than 0x10000"
            )

        flash_data = bytearray()
        end_addr = start_addr + segment_count * 0x1000

        while start_addr < end_addr:
            flash_data += self.__read_flash_4k_operation(start_addr)
            start_addr += 0x1000

        return flash_data

    def __wait_for_link(self):
        timeout = Timeout(self.timeout)
        while not timeout.expired():
            try:
                self.serial = serial.Serial(
                    port=self.device, baudrate=self.baudrate, timeout=self.timeout
                )
                payload = self.__build_payload_preamble(self.COMMAND_TYPE_CHIPINFO)
                response_type, response_payload = self.__send_and_parse_response(
                    payload=payload
                )
                if response_type == self.COMMAND_TYPE_CHIPINFO:
                    self.chipinfo = response_payload
                    print(f"Connected! Chip info: {self.chipinfo}")
                    return True
            except ValueError:
                pass
        return False

    def __read_flash_4k_operation(self, start_addr):
        payload = struct.pack("<I", start_addr)

        wire_payload = self.__build_payload_preamble(
            self.COMMAND_TYPE_READFLASH4K, len(payload)
        )
        wire_payload += payload

        response_type, response_payload = self.__send_and_parse_response(
            payload=wire_payload
        )
        if response_type != self.COMMAND_TYPE_READFLASH4K:
            raise ValueError(f"Failed to read 4K of flash at address {start_addr:#x}")
        # TODO: the response payload is 0x1004 in size, first 4 bytes
        # might be addr - must parse and investigate
        return response_payload

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
            response_length -= 2
        else:
            response_type = self.serial.read(1)
            response_length -= 4

        response_payload = self.serial.read(response_length)
        return response_type, response_payload

    def __read_until_dropping(self, marker):
        self.serial.read_until(marker)
        self.serial.read(len(marker))

    def __build_payload_preamble(self, payload_type, payload_length=0):
        payload = self.COMMON_COMMAND_PREAMBLE
        payload_length += 1
        if payload_length >= 0xFF:
            payload += self.LONG_COMMAND_MARKER
            payload += struct.pack("<H", payload_length)
        else:
            payload += struct.pack("B", payload_length)
        payload += struct.pack("B", payload_type)


@contextlib.contextmanager
def connect_device(device, baudrate, timeout):
    device = BK7231Serial(device, baudrate, timeout)
    try:
        yield device
    finally:
        device.close()


def chipinfo(device: BK7231Serial, args: List[str]):
    print(device.chipinfo)


def read_flash(device: BK7231Serial, args: List[str]):
    with open(args.file, "wb") as fs:
        fs.write(device.read_flash_4k(args.start_address, args.count))


def parse_args():
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

    subparsers = parser.add_subparsers(help="subcommand to execute")

    parser_chip_info = subparsers.add_parser("chipinfo", help="Shows chip information")
    parser_chip_info.set_defaults(handler=chipinfo)

    parser_read_flash = subparsers.add_parser("read_flash", help="Read data from flash")
    parser_read_flash.add_argument(
        "file", help="File to store flash data"
    )
    parser_read_flash.add_argument(
        "-s",
        "--start-address",
        dest="start_address",
        type=lambda x: int(x, 16),
        default=0x11000,
        help="Starting address to read from [hex] (default: 0x11000)",
    )
    parser_read_flash.add_argument(
        "-c",
        "--count",
        type=int,
        default=16,
        help="Number of 4K segments to read from flash (default: 16 segments = 64K)",
    )
    parser_read_flash.set_defaults(handler=read_flash)

    return parser.parse_args()


def main():
    args = parse_args()

    try:
        with connect_device(args.device, args.baudrate, args.timeout) as device:
            args.handler(device, args)
    except TimeoutError:
        print(traceback.format_exc(), file=sys.stderr)


if __name__ == "__main__":
    main()
