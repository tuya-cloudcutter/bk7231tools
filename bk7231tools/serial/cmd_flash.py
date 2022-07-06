# Copyright (c) Kuba Szczodrzyński 2022-07-06.

from io import BytesIO
from typing import Generator

from .cmd_chip import BK7231CmdChip
from .packets import (
    BkFlashEraseBlockCmnd,
    BkFlashGetMIDCmnd,
    BkFlashGetMIDResp,
    BkFlashRead4KCmnd,
    BkFlashRead4KResp,
    BkFlashWrite4KCmnd,
    BkFlashWriteCmnd,
    BkFlashWriteResp,
    EraseSize,
)
from .utils import fix_addr


class BK7231CmdFlash(BK7231CmdChip):
    def write_flash_bytes(
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

    def write_flash_4k(
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
        for data in self.read_flash(start, count * 4096, crc_check):
            out.write(data)
        return out.getvalue()

    def read_flash(
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

    def get_flash_id(self, address: int = 0x9F) -> dict:
        command = BkFlashGetMIDCmnd(address)
        response: BkFlashGetMIDResp = self.command(command)
        return dict(
            id=bytes([response.mfr_id, response.chip_id, response.size_code]),
            manufacturer_id=response.mfr_id,
            chip_id=response.chip_id,
            size_code=response.size_code,
            size=(1 << response.size_code),
        )

    def erase_flash_block(
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
