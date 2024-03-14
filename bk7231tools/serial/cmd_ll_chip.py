#  Copyright (c) Kuba Szczodrzyński 2024-3-5.

from binascii import crc32
from math import ceil

from .base import BK7231SerialInterface, BkProtocolType
from .base.packets import (
    BkCheckCrcCmnd,
    BkCheckCrcResp,
    BkReadRegCmnd,
    BkReadRegResp,
    BkRebootCmnd,
    BkWriteRegCmnd,
)


class BK7231SerialCmdLLChip(BK7231SerialInterface):
    def fix_addr(self, addr: int) -> int:
        if self.flash_size == 0:
            return addr
        addr &= 0x1FFFFF
        addr |= 0x200000
        return addr

    def reboot_chip(self) -> None:
        command = BkRebootCmnd(0xA5)
        self.command(command)

    def register_read(self, address: int) -> int:
        command = BkReadRegCmnd(address)
        response: BkReadRegResp = self.command(command)
        return response.value

    def register_write(self, address: int, value: int) -> None:
        command = BkWriteRegCmnd(address, value)
        self.command(command)

    def read_flash_range_crc(self, start: int, end: int) -> int:
        start = self.fix_addr(start)
        end = self.fix_addr(end)
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
            self.warn(
                "The current command timeout of",
                timeout_current,
                "second(s) is too low for reading",
                end - start,
                "bytes CRC. Increasing to",
                ceil(timeout_minimum),
                "second(s).",
            )
            self.serial.timeout = ceil(timeout_minimum)
        # fix for BK7231N which also counts the end offset
        if self.protocol_type == BkProtocolType.FULL:
            end -= 1
        command = BkCheckCrcCmnd(start, end)
        response: BkCheckCrcResp = self.command(command)
        self.serial.timeout = timeout_current
        return response.crc32 ^ 0xFFFFFFFF

    def check_crc(self, start: int, data: bytes) -> None:
        chip = self.read_flash_range_crc(start, start + len(data))
        calc = crc32(data)
        if chip != calc:
            raise ValueError(
                f"Chip CRC value {chip:X} does not match calculated CRC value {calc:X}"
            )
