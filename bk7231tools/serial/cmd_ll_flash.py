#  Copyright (c) Kuba Szczodrzyński 2024-3-5.

from typing import Tuple

from .base import BK7231SerialInterface
from .base.packets import (
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


class BK7231SerialCmdLLFlash(BK7231SerialInterface):
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
        return response.data0, response.data1, response.data2

    def flash_read_sr(self, size: int = 1) -> int:
        sr = self.flash_read_reg8(0x05)
        if size == 2:
            sr |= self.flash_read_reg8(0x35) << 8
        return sr

    def flash_write_sr(self, sr: int, size: int = 1, mask: int = 0xFFFF) -> None:
        if size == 1:
            self.flash_write_reg8(0x01, sr)
        else:
            self.flash_write_reg16(0x01, sr)
        sr_read = self.flash_read_sr(size)
        if (sr & mask) != (sr_read & mask):
            raise RuntimeError(
                f"Writing Status Register failed: wrote 0x{sr:04X}, got 0x{sr_read:04X}"
            )

    def flash_read_id(self, cmd: int = 0x9F) -> dict:
        self.flash_id = self.flash_id or bytes(self.flash_read_reg24(cmd))
        self.flash_params = dict(
            id=self.flash_id,
            manufacturer_id=self.flash_id[0],
            chip_id=self.flash_id[1],
            size_code=self.flash_id[2],
            size=(1 << self.flash_id[2]),
        )
        return self.flash_params

    def flash_detect_size(self) -> int:
        sizes = [0x100_000, 0x200_000, 0x400_000, 0x800_000, 0x1000_000]

        command = BkFlashRead4KCmnd(0)
        response: BkFlashRead4KResp = self.command(command)
        start_data = response.data

        for size in sizes:
            command = BkFlashRead4KCmnd(size)
            response: BkFlashRead4KResp = self.command(command)
            if start_data == response.data:
                return size
        raise ValueError("Couldn't detect flash chip size!")

    def flash_read_4k(
        self,
        start: int,
        crc_check: bool = True,
    ) -> bytes:
        start = self.fix_addr(start)
        attempt = 0
        while True:
            try:
                command = BkFlashRead4KCmnd(start)
                response: BkFlashRead4KResp = self.command(command)
                if crc_check:
                    self.check_crc(start, response.data)
                break
            except ValueError as e:
                self.warn(f"Reading failure ({e}), retrying (attempt {attempt})")
                attempt += 1
                if attempt > self.read_retries:
                    raise
        return response.data

    def flash_write_bytes(
        self,
        start: int,
        data: bytes,
        crc_check: bool = False,
        dry_run: bool = False,
    ) -> None:
        start = self.fix_addr(start)
        if len(data) > 256:
            raise ValueError(f"Data too long ({len(data)} > 256)")
        if dry_run:
            self.info(f" -> would write {len(data)} bytes to 0x{start:X}")
            return
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
        crc_check: bool = True,
        dry_run: bool = False,
    ) -> None:
        start = self.fix_addr(start)
        if len(data) > 4096:
            raise ValueError(f"Data too long ({len(data)} > 4096)")
        if len(data) < 4096:
            data += (4096 - len(data)) * b"\xff"
        if dry_run:
            self.info(f" -> would write {len(data)} bytes to 0x{start:X}")
            return

        attempt = 0
        while True:
            try:
                command = BkFlashWrite4KCmnd(start, data)
                self.command(command)
                if crc_check:
                    self.check_crc(start, data)
                break
            except ValueError as e:
                self.warn(f"Writing 4k failure ({e}), retrying (attempt {attempt})")
                attempt += 1
                if attempt > self.write_retries:
                    raise
                # need to erase the block again
                self.flash_erase_block(
                    start,
                    EraseSize.SECTOR_4K,
                    dry_run=dry_run,
                )

    def flash_erase_block(
        self,
        start: int,
        size: EraseSize,
        dry_run: bool = False,
    ) -> None:
        start = self.fix_addr(start)
        if dry_run:
            self.info(f" -> would erase {size.name} at 0x{start:X}")
            return
        attempt = 0
        while True:
            try:
                command = BkFlashEraseBlockCmnd(size, start)
                self.command(command)
                break
            except ValueError as e:
                self.warn(f"Erasing failure ({e}), retrying (attempt {attempt})")
                attempt += 1
                if attempt > self.write_retries:
                    raise
