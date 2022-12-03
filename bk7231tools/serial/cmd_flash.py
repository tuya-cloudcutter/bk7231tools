# Copyright (c) Kuba Szczodrzyński 2022-07-06.

from typing import Generator, Tuple

from .cmd_chip import BK7231CmdChip
from .packets import (
    BkFlashEraseBlockCmnd,
    BkFlashRead4KCmnd,
    BkFlashRead4KResp,
    BkFlashReg8ReadCmnd,
    BkFlashReg8ReadResp,
    BkFlashReg8WriteCmnd,
    BkFlashReg8WriteResp,
    BkFlashReg16WriteCmnd,
    BkFlashReg16WriteResp,
    BkFlashReg24ReadCmnd,
    BkFlashReg24ReadResp,
    BkFlashWrite4KCmnd,
    BkFlashWriteCmnd,
    BkFlashWriteResp,
    EraseSize,
)
from .utils import fix_addr


class BK7231CmdFlash(BK7231CmdChip):
    FLASH_SR_SIZE = {
        b"\x0B\x40\x14": 2,
        b"\x0B\x40\x15": 2,
        b"\x0B\x40\x16": 2,
        b"\x0B\x40\x17": 2,
        b"\x0B\x60\x17": 2,
        b"\x0E\x40\x16": 2,
        b"\x1C\x31\x13": 1,
        b"\x1C\x41\x16": 1,
        b"\x1C\x70\x15": 1,
        b"\x1C\x70\x16": 1,
        b"\x20\x40\x16": 2,
        b"\x51\x40\x13": 1,
        b"\x51\x40\x14": 1,
        b"\x5E\x40\x14": 1,
        b"\x85\x60\x13": 2,
        b"\x85\x60\x14": 2,
        b"\x85\x60\x16": 2,
        b"\x85\x60\x17": 2,
        b"\xC2\x23\x14": 2,
        b"\xC2\x23\x15": 1,
        b"\xC2\x23\x15": 2,
        b"\xC8\x40\x13": 1,
        b"\xC8\x40\x14": 2,
        b"\xC8\x40\x15": 2,
        b"\xC8\x40\x16": 1,
        b"\xC8\x65\x15": 2,
        b"\xC8\x65\x16": 2,
        b"\xC8\x65\x17": 2,
        b"\xCD\x60\x14": 2,
        b"\xE0\x40\x13": 1,
        b"\xE0\x40\x14": 1,
        b"\xEB\x60\x15": 2,
        b"\xEF\x40\x16": 2,
        b"\xEF\x40\x18": 2,
    }

    flash_id: bytes = None

    def flash_write_bytes(
        self,
        start: int,
        data: bytes,
        crc_check: bool = False,
        dry_run: bool = False,
    ):
        start = fix_addr(start)
        if len(data) > 256:
            raise ValueError(f"Data too long ({len(data)} > 256)")
        if dry_run:
            print(f" -> would write {len(data)} bytes to 0x{start:X}")
            return True
        command = BkFlashWriteCmnd(start, data)
        response: BkFlashWriteResp = self.command(command)
        if response.written != len(data):
            raise ValueError(f"Writing failed; wrote only {response.written} bytes")
        if crc_check:
            self.check_crc(start, data)

    def flash_write_4k(
        self,
        start: int,
        data: bytes,
        crc_check: bool = False,
        dry_run: bool = False,
    ):
        start = fix_addr(start)
        if len(data) > 4096:
            raise ValueError(f"Data too long ({len(data)} > 4096)")
        if len(data) < 4096:
            data += (4096 - len(data)) * b"\xff"
        if dry_run:
            print(f" -> would write {len(data)} bytes to 0x{start:X}")
            return True
        command = BkFlashWrite4KCmnd(start, data)
        self.command(command)
        if crc_check:
            self.check_crc(start, data)

    def flash_read(
        self,
        start: int,
        length: int,
        crc_check: bool = True,
    ) -> Generator[bytes, None, None]:
        start = fix_addr(start)
        if start & 0xFFF:
            raise ValueError(f"Starting address 0x{start:X} is not 4K aligned")
        if length & 0xFFF:
            raise ValueError(f"Read length 0x{length:X} is not 4K aligned")
        if start + length > 0x400000:
            raise ValueError(
                f"Read length 0x{length:X} is larger than flash memory size"
            )
        length = int(length // 4096)

        for i in range(length):
            addr = start + i * 4096
            progress = i / length * 100.0
            print(f"Reading 4k page at 0x{addr:06X} ({progress:.2f}%)")
            command = BkFlashRead4KCmnd(addr)
            response: BkFlashRead4KResp = self.command(command)
            if crc_check:
                self.check_crc(addr, response.data)
            yield response.data

    def flash_read_reg8(self, cmd: int) -> int:
        command = BkFlashReg8ReadCmnd(cmd)
        response: BkFlashReg8ReadResp = self.command(command)
        return response.data0

    def flash_write_reg8(self, cmd: int, data: int) -> bool:
        command = BkFlashReg8WriteCmnd(cmd, data)
        response: BkFlashReg8WriteResp = self.command(command)
        return response.data == command.data

    def flash_write_reg16(self, cmd: int, data: int) -> bool:
        command = BkFlashReg16WriteCmnd(cmd, data)
        response: BkFlashReg16WriteResp = self.command(command)
        return response.data == command.data

    def flash_read_reg24(self, cmd: int) -> Tuple[int, int, int]:
        command = BkFlashReg24ReadCmnd(cmd)
        response: BkFlashReg24ReadResp = self.command(command)
        return (response.data0, response.data1, response.data2)

    def flash_read_sr(self, size: int = 1) -> int:
        sr = self.flash_read_reg8(0x05)
        if size == 2:
            sr |= self.flash_read_reg8(0x35) << 8
        return sr

    def flash_write_sr(self, sr: int, size: int = 1):
        if size == 1:
            self.flash_write_reg8(0x01, sr)
        else:
            self.flash_write_reg16(0x01, sr)
        sr_read = self.flash_read_sr(size)
        if sr != sr_read:
            raise RuntimeError(
                f"Writing Status Register failed: wrote 0x{sr:04X}, got 0x{sr_read:04X}"
            )

    def flash_read_id(self, cmd: int = 0x9F) -> dict:
        self.flash_id = self.flash_id or bytes(self.flash_read_reg24(cmd))
        return dict(
            id=self.flash_id,
            manufacturer_id=self.flash_id[0],
            chip_id=self.flash_id[1],
            size_code=self.flash_id[2],
            size=(1 << self.flash_id[2]),
        )

    # 1 byte SR:
    # |  7  |  6  |  5  |  4  |  3  |  2  |  1  |  0  |
    # | SRP | BL4 | TBP | BP2 | BP1 | BP0 | WEL | WIP |
    #
    # 2 byte SR:
    # | 15  | 14  | 13  | 12  | 11  | 10  |  9  |  8  |
    # | SUS | CMP | HPF |  -  |  -  | LB  | QE  |SRP1 |
    #
    # |  7  |  6  |  5  |  4  |  3  |  2  |  1  |  0  |
    # |SRP0 | BP4 | BP3 | BP2 | BP1 | BP0 | WEL | WIP |
    def flash_unprotect(self, mask: int = 0b01111100):
        flash_id: bytes = self.flash_read_id()["id"]
        if flash_id not in self.FLASH_SR_SIZE:
            raise ValueError(f"Flash ID not known: {flash_id.hex()}")
        sr_size = self.FLASH_SR_SIZE[flash_id]
        sr = self.flash_read_sr(size=sr_size)
        sr &= ~mask
        self.flash_write_sr(sr, size=sr_size)

    def flash_erase_block(
        self,
        start: int,
        size: EraseSize,
        dry_run: bool = False,
    ):
        start = fix_addr(start)
        if dry_run:
            print(f" -> would erase {size.name} at 0x{start:X}")
            return True
        command = BkFlashEraseBlockCmnd(size, start)
        self.command(command)
