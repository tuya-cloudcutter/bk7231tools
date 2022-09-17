# Copyright (c) Kuba Szczodrzyński 2022-07-06.

from binascii import crc32
from math import ceil
from time import sleep

from serial import Timeout

from .packets import (
    BkBootVersionCmnd,
    BkBootVersionResp,
    BkCheckCrcCmnd,
    BkCheckCrcResp,
    BkLinkCheckCmnd,
    BkLinkCheckResp,
    BkReadRegCmnd,
    BkReadRegResp,
    BkRebootCmnd,
    BkSetBaudRateCmnd,
)
from .protocol import BK7231Protocol
from .utils import fix_addr


class BK7231CmdChip(BK7231Protocol):
    crc_end_incl: bool = False
    crc_speed_bps: int = 400000
    chip_info: str

    def wait_for_link(self, timeout: float) -> bool:
        tm = Timeout(timeout)
        tm_prev = self.serial.timeout
        self.serial.timeout = 0.005

        command = BkLinkCheckCmnd()
        response = None
        while not tm.expired() and not response:
            try:
                response: BkLinkCheckResp = self.command(command)
                if response and response.value != 0:
                    response = None
            except ValueError:
                pass

        self.drain()
        self.serial.timeout = tm_prev
        return not not response

    def set_baudrate(self, baudrate: int) -> bool:
        command = BkSetBaudRateCmnd(baudrate, delay_ms=20)

        def baudrate_cb():
            if self.debug_hl:
                print("-- UART: Changing port baudrate")
            sleep(command.delay_ms / 1000 / 2)
            self.serial.baudrate = baudrate

        self.command(command, after_send=baudrate_cb)
        return True

    def reboot_chip(self):
        command = BkRebootCmnd(0xA5)
        self.command(command)

    def read_chip_info(self) -> str:
        command = BkBootVersionCmnd()
        response: BkBootVersionResp = self.command(command)
        if response.version == b"\x07":
            # read chip type from register if command is not implemented
            self.chip_info = hex(self.register_read(0x800000))  # SCTRL_CHIP_ID
        else:
            self.chip_info = response.version.decode()
        return self.chip_info

    def register_read(self, address: int) -> int:
        command = BkReadRegCmnd(address)
        response: BkReadRegResp = self.command(command)
        return response.value

    def read_flash_range_crc(self, start: int, end: int) -> int:
        start = fix_addr(start)
        end = fix_addr(end)
        # probably reading whole flash CRC
        if end == 0x200000:
            end += 0x200000
        # command arguments are (incl., excl.)
        if start == end:
            raise ValueError("Start and end must differ! (end is exclusive)")
        if start > end:
            raise ValueError("Start must be lesser than end!")
        # print a warning instead of just timeout-ing
        timeout_current = self.serial.timeout
        timeout_minimum = (end - start) / self.crc_speed_bps
        if timeout_minimum > timeout_current:
            print(
                "WARN: The current command timeout of",
                timeout_current,
                "second(s) is too low for reading",
                end - start,
                "bytes CRC. Increasing to",
                ceil(timeout_minimum),
                "second(s).",
            )
            self.serial.timeout = ceil(timeout_minimum)
        # fix for BK7231N which also counts the end offset
        if self.crc_end_incl:
            end -= 1
        command = BkCheckCrcCmnd(start, end)
        response: BkCheckCrcResp = self.command(command)
        self.serial.timeout = timeout_current
        return response.crc32 ^ 0xFFFFFFFF

    def check_crc(self, start: int, data: bytes):
        chip = self.read_flash_range_crc(start, start + len(data))
        calc = crc32(data)
        if chip != calc:
            raise ValueError(
                f"Chip CRC value {chip:X} does not match calculated CRC value {calc:X}"
            )
