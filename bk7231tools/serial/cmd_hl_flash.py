#  Copyright (c) Kuba Szczodrzyński 2024-3-5.

from binascii import crc32
from io import BytesIO
from typing import IO, Generator

from .base import BK7231SerialInterface, BkProtocolType, EraseSize


class BK7231SerialCmdHLFlash(BK7231SerialInterface):
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
        b"\x85\x42\x15": 1,
        b"\x85\x60\x13": 2,
        b"\x85\x60\x14": 2,
        b"\x85\x60\x16": 2,
        b"\x85\x60\x17": 2,
        b"\xC2\x23\x14": 2,
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
    def flash_unprotect(self, mask: int = 0b01111100) -> None:
        flash_id: bytes = self.flash_read_id()["id"]
        if flash_id not in self.FLASH_SR_SIZE:
            raise ValueError(f"Flash ID not known: {flash_id.hex()}")
        sr_size = self.FLASH_SR_SIZE[flash_id]
        sr = self.flash_read_sr(size=sr_size)
        sr &= ~mask
        self.flash_write_sr(sr, size=sr_size, mask=mask)

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

    def program_flash(
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

        # unprotect flash memory for BK7231N
        if self.protocol_type == BkProtocolType.FULL:
            self.info("Trying to unprotect flash memory...")
            self.flash_unprotect()

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
                block = io.read(min(256, sector_end - addr))
                block_size = len(block)
                if not block_size:
                    # writing finished
                    return
                self.flash_write_bytes(
                    addr,
                    block,
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
                if crc_check:
                    self.info("Verifying CRC")
                    pad_size = (4096 - (io_size % 4096)) % 4096
                    crc = crc32(b"\xff" * pad_size, crc)
                    crc_chip = self.read_flash_range_crc(
                        start=start,
                        end=start + io_size + pad_size,
                    )
                    if crc != crc_chip:
                        raise ValueError(
                            f"Chip CRC value {crc_chip:X} does not match calculated CRC value {crc:X}"
                        )
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
