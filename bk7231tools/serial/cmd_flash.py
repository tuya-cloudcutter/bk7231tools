# Copyright (c) Kuba Szczodrzyński 2022-07-06.

from io import BytesIO
from typing import Generator

from .cmd_chip import BK7231CmdChip
from .packets import (
    BkFlashEraseBlockCmnd,
    BkFlashRead4KCmnd,
    BkFlashRead4KResp,
    BkFlashReg8ReadCmnd,
    BkFlashReg8ReadResp,
    BkFlashReg24ReadCmnd,
    BkFlashReg24ReadResp,
    BkFlashWrite4KCmnd,
    BkFlashWriteCmnd,
    BkFlashWriteResp,
    EraseSize,
)
from .utils import fix_addr


class BK7231CmdFlash(BK7231CmdChip):
    def flash_write_bytes(
        self,
        start: int,
        data: bytes,
        crc_check: bool = False,
        dry_run: bool = False,
    ) -> bool:
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
        return True

    def flash_write_4k(
        self,
        start: int,
        data: bytes,
        crc_check: bool = False,
        dry_run: bool = False,
    ) -> bool:
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
        return True

    def read_flash_4k(
        self,
        start: int,
        count: int = 1,
        crc_check: bool = True,
    ) -> bytes:
        out = BytesIO()
        for data in self.flash_read(start, count * 4096, crc_check):
            out.write(data)
        return out.getvalue()

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

    def flash_read_reg24(self, cmd: int) -> int:
        command = BkFlashReg24ReadCmnd(cmd)
        response: BkFlashReg24ReadResp = self.command(command)
        return (response.data0, response.data1, response.data2)

    def flash_read_id(self, cmd: int = 0x9F) -> dict:
        rdid = self.flash_read_reg24(cmd)
        return dict(
            id=bytes(rdid),
            manufacturer_id=rdid[0],
            chip_id=rdid[1],
            size_code=rdid[2],
            size=(1 << rdid[2]),
        )

    def flash_erase_block(
        self,
        start: int,
        size: EraseSize,
        dry_run: bool = False,
    ) -> bool:
        start = fix_addr(start)
        if dry_run:
            print(f" -> would erase {size.name} at 0x{start:X}")
            return True
        command = BkFlashEraseBlockCmnd(size, start)
        self.command(command)
        return True
