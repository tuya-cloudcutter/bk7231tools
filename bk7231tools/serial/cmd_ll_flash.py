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

CRC32_FF_4K = 0xF154670A


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
        self.info("Flash size - detecting...")
        sizes = [0.5, 1, 2, 4, 8, 16]  # MiB
        # disable bootloader protection bypass
        self.boot_protection_bypass = False
        safe_offset = 0x11000
        try:
            start_data = self.flash_read_4k(start=safe_offset, crc_check=False)
            for size in sizes:
                size = int(size * 0x100_000)
                start = size + safe_offset
                self.info(f" - Checking wraparound at {hex(start)}")
                check_data = self.flash_read_4k(start=start, crc_check=False)
                if start_data == check_data:
                    self.info(f"Flash size detected - {hex(size)}")
                    return size
            raise ValueError("Couldn't detect flash chip size!")
        finally:
            self.boot_protection_bypass = True

    def flash_read_4k(
        self,
        start: int,
        crc_check: bool = True,
    ) -> bytes:
        attempt = 0
        while True:
            try:
                command = BkFlashRead4KCmnd(start)
                response: BkFlashRead4KResp = self.command(command)
                if len(response.data) != 0x1000:
                    raise ValueError(
                        f"Invalid data length received: {len(response.data)}"
                    )
                if crc_check:
                    self.check_crc(start, response.data)
                break
            except ValueError as e:
                self.warn(
                    f"Reading failure @ {hex(start)} ({e}), retrying (attempt {attempt})"
                )
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
                self.warn(
                    f"Writing 4k failure @ {hex(start)} ({e}), retrying (attempt {attempt})"
                )
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
        if dry_run:
            self.info(f" -> would erase {size.name} at 0x{start:X}")
            return

        def do_erase():
            command = BkFlashEraseBlockCmnd(size, start)
            self.command(command)

        def do_erase_verify():
            # readout pre-erase contents
            self.info(f" - Checking block pre-erase @ {hex(start)}")
            crc_pre_erase = self.read_flash_range_crc(start, start + 0x1000)
            if crc_pre_erase == CRC32_FF_4K:
                # do not use this block for verification if already 0xFF
                # do not erase either - not necessary
                self.info(f" - Deferring, block @ {hex(start)} is already erased")
                return
            # run the erase command
            self.info(f" - Trying to erase block @ {hex(start)}")
            do_erase()
            # readout post-erase contents
            self.info(f" - Checking block post-erase @ {hex(start)}")
            crc_post_erase = self.read_flash_range_crc(start, start + 0x1000)
            # verify that all bytes are 0xFF
            if crc_post_erase != CRC32_FF_4K:
                raise ValueError(
                    "Erase failed - flash protected; "
                    f"found non-0xFF bytes @ {hex(start)}"
                )
            self.info(f" - Erase succeeded @ {hex(start)}")
            self.flash_erase_checked = True

        attempt = 0
        while True:
            try:
                if not self.flash_erase_checked:
                    if size != EraseSize.SECTOR_4K:
                        self.warn("Cannot verify erasing in 64K block mode")
                        do_erase()
                    else:
                        do_erase_verify()
                else:
                    do_erase()
                break
            except ValueError as e:
                self.warn(
                    f"Erasing failure @ {hex(start)} ({e}), retrying (attempt {attempt})"
                )
                attempt += 1
                if attempt > self.write_retries:
                    raise
