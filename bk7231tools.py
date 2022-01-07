import argparse
import sys
from dataclasses import dataclass
from enum import Enum
from typing import List
import serial
import struct
import traceback

from serial.serialutil import Timeout


@dataclass
class CommandType:
    code: int = 0x00
    is_long: bool = True


COMMAND_LINKCHECK = CommandType(code=0x00, is_long=False)
COMMAND_READCHIPINFO = CommandType(code=0x11, is_long=False)
COMMAND_READFLASH4K = CommandType(code=0x09, is_long=True)
COMMAND_REBOOT = CommandType(code=0x0E, is_long=False)


class BK7231Serial(object):
    COMMON_COMMAND_PREAMBLE = b"\x01\xe0\xfc"
    LONG_COMMAND_MARKER = b"\xff\xf4"

    RESPONSE_PREAMBLE = b"\x04\x0e"
    RESPONSE_DATA_MARKER = COMMON_COMMAND_PREAMBLE
    LONG_RESPONSE_MARKER = b"\xf4"

    def __init__(self, device, baudrate, timeout=10.0):
        self.device = device
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial = serial.Serial(
            port=self.device, baudrate=self.baudrate, timeout=timeout
        )
        if not self.__wait_for_link():
            raise TimeoutError("Timed out attempting to link with chip")

    def close(self):
        if self.serial and not self.serial.closed:
            self.serial.close()

    def reboot_chip(self):
        command_type = COMMAND_REBOOT.code
        payload = self.__build_payload_preamble(command_type, payload_length=1)
        payload += b"\xA5"
        self.serial.write(payload)
        self.serial.flush()

    def read_chip_info(self):
        command_type = COMMAND_READCHIPINFO.code
        payload = self.__build_payload_preamble(command_type)
        response_type, response_payload = self.__send_and_parse_response(
            payload=payload,
            request_type=COMMAND_READCHIPINFO
        )
        if response_type == command_type:
            return response_payload.decode("utf8")
        else:
            raise ValueError("Invalid chip_info response")

    def read_flash_4k(self, start_addr, segment_count=1):
        if (start_addr & 0xFFF) != 0:
            raise ValueError(f"Starting address {start_addr:#x} is not 4K aligned")
        if start_addr < 0x10000:
            raise ValueError(
                f"Starting address {start_addr:#x} is smaller than 0x10000"
            )

        flash_data = bytearray()
        end_addr = start_addr + segment_count * 0x1000
        cur_addr = start_addr

        while cur_addr < end_addr:
            try:
                print(f"Reading 4k page at {cur_addr:#X}, first rebooting the device ({(((cur_addr-start_addr) / (end_addr-start_addr))*100):.2f}%)")
                for _ in range(10):
                    self.reboot_chip()
                if not self.__wait_for_link():
                    continue
                flash_data += self.__read_flash_4k_operation(cur_addr)
                cur_addr += 0x1000
            except:
                pass

        return flash_data

    def __wait_for_link(self, link_wait_timeout=0.01):
        timeout = Timeout(10)
        self.serial.timeout = link_wait_timeout
        while not timeout.expired():
            try:
                self.chip_info = self.read_chip_info()
                print(f"Connected! Chip info: {self.chip_info}")
                self.__drain()
                self.serial.timeout = self.timeout
                return True
            except ValueError:
                pass
        return False

    def __read_flash_4k_operation(self, start_addr):
        payload = struct.pack("<I", start_addr)

        wire_payload = self.__build_payload_preamble(
            COMMAND_READFLASH4K.code, len(payload), long_command=True
        )
        wire_payload += payload

        while True:
            response_type, response_payload = self.__send_and_parse_response(
                payload=wire_payload,
                request_type=COMMAND_READFLASH4K
            )
            if len(response_payload) != (4*1024) + 4:
                print(f"Expected length {(4*1024) + 4}, but got {len(response_payload)}")
                raise SystemError("Chip got borked")
            address = struct.unpack("<I", response_payload[:4])[0]
            if address == start_addr:
                break
            else:
                print("Retrying read")

        return response_payload[4:]

    def __send_and_parse_response(self, payload, request_type: CommandType):
        response_length = 0
        read_response_type = None

        while read_response_type != request_type.code:
            try:
                self.serial.write(payload)
                self.serial.flush()
                data = self.serial.read_until(self.RESPONSE_PREAMBLE)
                if len(data) == 0 or data[-len(self.RESPONSE_PREAMBLE):] != self.RESPONSE_PREAMBLE:
                    raise ValueError("No response received")

                response_length = struct.unpack("B", self.serial.read(1))[0]
                is_long_command = response_length == 0xFF
                if request_type.is_long != is_long_command:
                    # Invalid response, so continue reading until a new valid packet is found
                    continue

                response_data_marker = self.serial.read(len(self.RESPONSE_DATA_MARKER))
                if response_data_marker != self.RESPONSE_DATA_MARKER:
                    # Invalid packet, so continue reading until a new valid packet is found
                    continue

                if is_long_command:
                    data = self.serial.read_until(self.LONG_RESPONSE_MARKER)
                    response_length, read_response_type = struct.unpack("<HH", self.serial.read(4))
                    response_length -= 2
                else:
                    read_response_type = struct.unpack("B", self.serial.read(1))[0]
                    response_length -= 4
            except struct.error:
                pass

        response_payload = self.serial.read(response_length)
        return read_response_type, response_payload

    def __drain(self):
        self.serial.timeout = 0.001
        while self.serial.read(1 * 1024) != b"":
            pass
        self.serial.timeout = self.timeout

    def __build_payload_preamble(self, payload_type, payload_length=0, long_command=False):
        payload = self.COMMON_COMMAND_PREAMBLE
        payload_length += 1
        if payload_length >= 0xFF or long_command:
            payload += self.LONG_COMMAND_MARKER
            payload += struct.pack("<H", payload_length)
        else:
            payload += struct.pack("B", payload_length)
        payload += struct.pack("B", payload_type)
        return payload


def connect_device(device, baudrate, timeout):
    return BK7231Serial(device, baudrate, timeout)


def chip_info(device: BK7231Serial, args: List[str]):
    print(device.chip_info)


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

    parser_chip_info = subparsers.add_parser("chip_info", help="Shows chip information")
    parser_chip_info.set_defaults(handler=chip_info)

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


if __name__ == "__main__":
    args = parse_args()

    try:
        device = connect_device(args.device, args.baudrate, args.timeout)
        args.handler(device, args)
    except TimeoutError:
        print(traceback.format_exc(), file=sys.stderr)
