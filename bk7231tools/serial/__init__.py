from binascii import crc32
from io import BytesIO
from typing import IO, Generator

from serial import Serial

from .cmd_flash import BK7231CmdFlash
from .packets import EraseSize
from .protocol import ProtocolType
from .utils import fix_addr


class BK7231Serial(BK7231CmdFlash):
    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        link_timeout: float = 10.0,
        cmnd_timeout: float = 1.0,
        link_baudrate: int = 115200,
        **kwargs,
    ) -> None:
        self.serial = Serial(
            port=port,
            baudrate=link_baudrate,
            timeout=cmnd_timeout,
        )
        self.serial.set_buffer_size(rx_size=8192)
        self.baudrate = baudrate
        self.link_timeout = link_timeout
        self.cmnd_timeout = cmnd_timeout
        if kwargs.get("debug_hl", False):
            self.debug = print
        if kwargs.get("debug_ll", False):
            self.verbose = print

    def connect(self):
        # try to communicate
        if not self.wait_for_link(self.link_timeout):
            raise TimeoutError("Timed out attempting to link with chip")
        # update the transmission baudrate
        if self.serial.baudrate != self.baudrate:
            self.set_baudrate(self.baudrate)
        # read and save chip info
        self.read_chip_info()
        try:
            self.flash_read_id()
        except NotImplementedError:
            self.flash_id = b"\x00\x00\x00"

    def close(self):
        if self.serial and not self.serial.closed:
            self.serial.close()
            self.serial = None

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
        start = fix_addr(start)
        end = start + io_size
        addr = start
        if start & 0xFFF and not really_erase:
            raise ValueError(f"Start address not on 4K boundary; sector erase needed")
        if end > 0x400000:
            raise ValueError(f"Input data is larger than flash memory size")

        # unprotect flash memory for BK7231N
        if self.protocol_type == ProtocolType.FULL:
            self.info("Trying to unprotect flash memory...")
            self.flash_unprotect()

        # start is NOT on sector boundary
        if addr & 0xFFF:
            self.info("Writing unaligned data...")
            # erase sector containing data start
            sector_addr = addr & 0x1FF000
            self.flash_erase_block(
                sector_addr,
                EraseSize.SECTOR_4K,
                dry_run=dry_run,
            )

            # write data in 256-byte chunks
            sector_end = (addr & 0x1FF000) + 4096
            while addr & 0xFFF:
                block = io.read(min(256, sector_end - addr))
                block_size = len(block)
                if not block_size:
                    # writing finished
                    return
                self.flash_write_bytes(
                    addr,
                    block,
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
                    dry_run=dry_run,
                )
            yield len(block)
            addr += block_size


__all__ = ["BK7231Serial"]
