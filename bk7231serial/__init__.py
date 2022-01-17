import struct
import time
from typing import Tuple
import zlib

import serial
from serial.serialutil import Timeout

from .commands import *
from .crc import crc32_ver2


class BK7231Serial(object):
    COMMON_COMMAND_PREAMBLE = b"\x01\xe0\xfc"
    LONG_COMMAND_MARKER = b"\xff\xf4"

    RESPONSE_PREAMBLE = b"\x04\x0e"
    RESPONSE_DATA_MARKER = COMMON_COMMAND_PREAMBLE
    LONG_RESPONSE_MARKER = b"\xf4"

    def __init__(self, device, baudrate, timeout=10.0):
        initial_baudrate = 115200
        self.device = device
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial = serial.Serial(
            port=self.device, baudrate=initial_baudrate, timeout=timeout
        )
        if not self.__wait_for_link():
            raise TimeoutError("Timed out attempting to link with chip")
        if self.baudrate != initial_baudrate:
            self.set_baudrate(self.baudrate)
        self.chip_info = self.read_chip_info()
        print(f"Connected! Chip info: {self.chip_info}")

    def close(self):
        if self.serial and not self.serial.closed:
            self.serial.close()

    def read_flash_range_crc(self, start_address, end_address):
        command_type = COMMAND_FLASHCRC
        payload = struct.pack("<II", start_address, end_address)
        payload = self.__build_payload(command_type.code, payload_body=payload)
        _, response_payload = self.__send_and_parse_response(payload=payload, request_type=command_type)
        return struct.unpack("<I", response_payload)[0]

    def reboot_chip(self):
        command_type = COMMAND_REBOOT
        payload = self.__build_payload(command_type.code, payload_body=b"\xA5")
        self.serial.write(payload)
        self.serial.flush()

    def set_baudrate(self, rate):
        delay = 20
        command_type = COMMAND_SETBAUDRATE
        payload = struct.pack("<IB", rate, delay)
        payload = self.__build_payload(command_type.code, payload)
        self.__send_payload(payload)
        time.sleep(delay/1000/2)
        self.serial.baudrate = rate
        response_type, _ = self.__read_response(command_type)
        return response_type == command_type.code

    def read_chip_info(self):
        command_type = COMMAND_READCHIPINFO
        payload = self.__build_payload(command_type.code)
        response_type, response_payload = self.__send_and_parse_response(payload=payload, request_type=command_type)
        if response_type == command_type.code:
            return response_payload.decode("utf8")
        else:
            raise ValueError("Invalid chip_info response")

    def read_flash_4k(self, start_addr: int, segment_count: int = 1, crc_check: bool = True):
        if (start_addr & 0xFFF) != 0:
            raise ValueError(f"Starting address {start_addr:#x} is not 4K aligned")
        if start_addr < 0x10000:
            raise ValueError(f"Starting address {start_addr:#x} is smaller than 0x10000")

        flash_data = bytearray()
        end_addr = start_addr + segment_count * 0x1000
        cur_addr = start_addr

        while cur_addr < end_addr:
            try:
                print(f"Reading 4k page at {cur_addr:#X} ({(((cur_addr - start_addr) / (end_addr - start_addr)) * 100):.2f}%)")
                block = self.__read_flash_4k_operation(cur_addr)
                crc = self.read_flash_range_crc(cur_addr, cur_addr+0x1000)
                actual_crc = crc32_ver2(0xFFFFFFFF, block)
                if (crc == actual_crc) and crc_check or not crc_check:
                    flash_data += block
                    cur_addr += 0x1000
                else:
                    print("Y'all dun goofed now with ya'll corrupt bytes!")
            except ValueError:
                pass

        return flash_data

    def __wait_for_link(self, link_wait_timeout=0.01):
        timeout = Timeout(self.timeout)
        self.serial.timeout = link_wait_timeout
        while not timeout.expired():
            try:
                command_type = COMMAND_LINKCHECK
                payload = self.__build_payload(command_type.code)
                response_code, response_payload = self.__send_and_parse_response(payload=payload, request_type=command_type)
                if response_code == command_type.response_code and response_payload == b"\x00":
                    self.__drain()
                    self.serial.timeout = self.timeout
                    return True
            except ValueError:
                pass
        return False

    def __read_flash_4k_operation(self, start_addr):
        command_type = COMMAND_READFLASH4K
        payload = struct.pack("<I", start_addr)
        payload = self.__build_payload(command_type.code, payload, long_command=True)

        while True:
            _, response_payload = self.__send_and_parse_response(payload=payload, request_type=command_type)
            if len(response_payload) != (4 * 1024) + 4:
                print(f"Expected length {(4 * 1024) + 4}, but got {len(response_payload)}")
                raise SystemError("Chip got borked")
            address = struct.unpack("<I", response_payload[:4])[0]
            if address == start_addr:
                break
            else:
                print("Retrying read")

        return response_payload[4:]

    def __send_payload(self, payload):
        self.serial.write(payload)
        self.serial.flush()

    def __read_response(self, request_type: CommandType):
        response_length = 0
        read_response_type = None

        while read_response_type != request_type.code:
            try:
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
                    long_response_marker = self.serial.read(1)

                    if long_response_marker != self.LONG_RESPONSE_MARKER:
                        # Invalid packet, so continue reading until a new valid packet is found
                        continue

                    response_length, read_response_type = struct.unpack(
                        "<HH", self.serial.read(4)
                    )
                    response_length -= 2
                else:
                    read_response_type = struct.unpack("B", self.serial.read(1))[0]
                    response_length -= 4

                # Special case if the request type has a special response code - if so
                # break out
                if (request_type.has_response_code and
                        read_response_type == request_type.response_code):
                    break

            except struct.error:
                pass

        response_payload = self.serial.read(response_length)
        return read_response_type, response_payload

    def __send_and_parse_response(self, payload, request_type: CommandType) -> Tuple[int, bytes]:
        self.__send_payload(payload)
        return self.__read_response(request_type)

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

    def __build_payload(self, payload_type, payload_body=None, long_command=False):
        if payload_body is None:
            payload_body = b''
        preamble = self.__build_payload_preamble(payload_type, len(payload_body), long_command=long_command)
        return preamble + payload_body


__all__ = ['BK7231Serial']
