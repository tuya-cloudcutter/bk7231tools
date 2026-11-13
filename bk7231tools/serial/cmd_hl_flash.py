#  Copyright (c) Kuba Szczodrzyński 2024-3-5.

from binascii import crc32
from io import BytesIO
from typing import IO, Generator, Tuple

from .base import BK7231SerialInterface, BkChipType, BkProtocolType, EraseSize


class BK7231SerialCmdHLFlash(BK7231SerialInterface):
    FLASH_SR_SIZE = {
        b"\x0b\x40\x14": 2,
        b"\x0b\x40\x15": 2,
        b"\x0b\x40\x16": 2,
        b"\x0b\x40\x17": 2,
        b"\x0b\x60\x17": 2,
        b"\x0e\x40\x16": 2,
        b"\x1c\x31\x13": 1,
        b"\x1c\x41\x16": 1,
        b"\x1c\x70\x15": 1,
        b"\x1c\x70\x16": 1,
        b"\x20\x40\x16": 2,
        b"\x51\x40\x13": 1,
        b"\x51\x40\x14": 1,
        b"\x5e\x40\x14": 1,
        b"\x85\x42\x15": 1,
        b"\x85\x20\x15": 2,
        b"\x85\x60\x13": 2,
        b"\x85\x60\x14": 2,
        b"\x85\x60\x16": 2,
        b"\x85\x60\x17": 2,
        b"\xc2\x23\x14": 2,
        b"\xc2\x23\x15": 2,
        b"\xc8\x40\x13": 1,
        b"\xc8\x40\x14": 2,
        b"\xc8\x40\x15": 2,
        b"\xc8\x40\x16": 1,
        b"\xc8\x65\x15": 2,
        b"\xc8\x65\x16": 2,
        b"\xc8\x65\x17": 2,
        b"\xcd\x60\x14": 2,
        b"\xe0\x40\x13": 1,
        b"\xe0\x40\x14": 1,
        b"\xeb\x60\x15": 2,
        b"\xef\x40\x16": 2,
        b"\xef\x40\x18": 2,
    }

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
    def flash_unprotect(self, mask: int = 0b0100000001111100) -> Tuple[int, int, int]:
        flash_id: bytes = self.flash_read_id()["id"]
        if flash_id not in self.FLASH_SR_SIZE:
            raise ValueError(f"Flash ID not known: {flash_id.hex()}")
        sr_size = self.FLASH_SR_SIZE[flash_id]
        sr = self.flash_read_sr(size=sr_size)
        self.flash_write_sr(sr & ~mask, size=sr_size, mask=mask)
        return sr_size, sr, mask

    def flash_restore_protection(self, state: Tuple[int, int, int]) -> None:
        sr_size, sr_original, mask = state
        sr_current = self.flash_read_sr(size=sr_size)
        sr_restored = (sr_current & ~mask) | (sr_original & mask)
        self.flash_write_sr(sr_restored, size=sr_size, mask=mask)

    def flash_read(
        self,
        start: int,
        length: int,
        crc_check: bool = True,
    ) -> Generator[bytes, None, None]:
        if self.flash_size and start + length > self.flash_size:
            raise ValueError(
                f"Read length 0x{length:X} is larger than "
                f"flash memory size (0x{self.flash_size:X})"
            )

        block_count = (length - 1) // 4096 + 1
        block_start = start & ~0xFFF
        start = start & 0xFFF
        for i in range(block_count):
            progress = i / block_count * 100.0
            self.info(f"Reading 4k page at 0x{block_start:06X} ({progress:.2f}%)")
            chunk = self.flash_read_4k(block_start, crc_check)
            # cut to the requested start offset and length
            chunk = chunk[start : start + length]
            start = 0
            length -= len(chunk)
            block_start += 4096
            yield chunk

    def flash_read_bytes(
        self,
        start: int,
        length: int,
        crc_check: bool = True,
    ) -> bytes:
        out = BytesIO()
        for data in self.flash_read(start, length, crc_check):
            out.write(data)
        assert out.tell() == length
        return out.getvalue()

    def program_flash(
        self,
        io: IO[bytes],
        io_size: int,
        start: int,
        crc_check: bool = False,
        really_erase: bool = False,
        dry_run: bool = False,
    ) -> Generator[int, None, None]:
        protection_state = None
        if self.protocol_type == BkProtocolType.FULL and not dry_run:
            self.info("Trying to unprotect flash memory...")
            state = self.flash_unprotect()
            if self.chip_type == BkChipType.BK7258:
                protection_state = state

        try:
            yield from self._program_flash_unprotected(
                io=io,
                io_size=io_size,
                start=start,
                crc_check=crc_check,
                really_erase=really_erase,
                dry_run=dry_run,
            )
        finally:
            if protection_state is not None:
                self.info("Restoring flash protection...")
                self.flash_restore_protection(protection_state)

    def _program_flash_unprotected(
        self,
        io: IO[bytes],
        io_size: int,
        start: int,
        crc_check: bool = False,
        really_erase: bool = False,
        dry_run: bool = False,
    ) -> Generator[int, None, None]:
        end = start + io_size
        addr = start
        if start & 0xFFF and not really_erase:
            raise ValueError(f"Start address not on 4K boundary; sector erase needed")
        if self.flash_size and end > self.flash_size:
            raise ValueError(f"Input data is larger than flash memory size")

        # start is NOT on sector boundary
        if addr & 0xFFF:
            self.info("Writing unaligned data...")
            # erase sector containing data start
            sector_addr = addr & ~0xFFF
            self.flash_erase_block(
                sector_addr,
                EraseSize.SECTOR_4K,
                dry_run=dry_run,
            )

            # write data in 256-byte chunks
            sector_end = (addr & ~0xFFF) + 4096
            while addr & 0xFFF:
                padding_len = addr & 0xFF
                block = io.read(min(256 - padding_len, sector_end - addr))
                block_size = len(block)
                if not block_size:
                    # writing finished
                    return
                self.flash_write_bytes(
                    addr - padding_len,
                    padding_len * b"\xff" + block,
                    crc_check=crc_check,
                    dry_run=dry_run,
                )
                yield len(block)
                addr += block_size

        assert (addr & 0xFFF) == 0

        # write the rest of data in 4K sectors
        crc = 0
        while True:
            block = io.read(4096)
            block_size = len(block) if addr < end else 0
            block_empty = not len(block.strip(b"\xff"))
            if not block_size:
                self.info("OK!")
                return
            # print progress info
            progress = 100.0 - (end - addr) / io_size * 100.0
            if block_empty:
                self.info(f"Erasing at 0x{addr:X} ({progress:.2f}%)")
            else:
                self.info(f"Erasing and writing at 0x{addr:X} ({progress:.2f}%)")
            # compute CRC32
            crc = crc32(block, crc)
            self.flash_erase_block(
                addr,
                EraseSize.SECTOR_4K,
                dry_run=dry_run,
            )
            if not block_empty:
                # skip empty blocks
                self.flash_write_4k(
                    addr,
                    block,
                    crc_check=crc_check,
                    dry_run=dry_run,
                )
            yield len(block)
            addr += block_size
