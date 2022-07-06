from binascii import crc32
from io import BytesIO
from math import ceil
from time import sleep
from typing import IO, Generator

from serial import Serial, Timeout

from .packets import (
    BkBootVersionCmnd,
    BkBootVersionResp,
    BkCheckCrcCmnd,
    BkCheckCrcResp,
    BkFlashEraseBlockCmnd,
    BkFlashRead4KCmnd,
    BkFlashRead4KResp,
    BkFlashWrite4KCmnd,
    BkFlashWriteCmnd,
    BkFlashWriteResp,
    BkLinkCheckCmnd,
    BkLinkCheckResp,
    BkRebootCmnd,
    BkSetBaudRateCmnd,
    EraseSize,
)
from .protocol import BK7231Protocol


def fix_addr(addr: int) -> int:
    addr &= 0x1FFFFF
    addr |= 0x200000
    return addr


class BK7231Serial(BK7231Protocol):
    chip_info: bytes
    crc_end_incl: bool = False
    crc_speed_bps: int = 0

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        link_timeout: float = 10.0,
        cmnd_timeout: float = 1.0,
        debug_hl: bool = False,
        debug_ll: bool = False,
    ) -> None:
        super().__init__(
            serial=Serial(
                port=port,
                baudrate=115200,
                timeout=cmnd_timeout,
            ),
        )
        self.debug_hl = debug_hl
        self.debug_ll = debug_ll
        # reset the chip using RTS line
        self.hw_reset()
        # try to communicate
        if not self.wait_for_link(link_timeout):
            raise TimeoutError("Timed out attempting to link with chip")
        # update the transmission baudrate
        if self.serial.baudrate != baudrate:
            self.set_baudrate(baudrate)
        # read and save chip info
        self.read_chip_info()
        # apply workarounds for BK7231N
        if self.chip_info == b"\x07":
            print(f"Connected to BK7231N chip")
            self.crc_end_incl = True
            self.crc_speed_bps = 400000
        elif self.chip_info:
            print(f"Connected! Chip info: {self.chip_info}")
        else:
            print(f"Connected, but read no chip version")

    def close(self):
        if self.serial and not self.serial.closed:
            self.serial.close()
            self.serial = None

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
        command = BkRebootCmnd()
        self.command(command)

    def read_chip_info(self) -> str:
        command = BkBootVersionCmnd()
        response: BkBootVersionResp = self.command(command)
        self.chip_info = response.version
        return self.chip_info.decode("utf-8")

    def read_flash_range_crc(self, start: int, end: int) -> int:
        start = fix_addr(start)
        end = fix_addr(end)
        # probably reading whole flash CRC
        if end == 0x200000:
            end += 0x200000
        # command arguments are (incl., excl.)
        if start == end:
            raise ValueError("Start and end must differ! (end is exclusive)")
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

    def program_flash(
        self,
        io: IO[bytes],
        io_size: int,
        start: int,
        verbose: bool = True,
        crc_check: bool = False,
        really_erase: bool = False,
        dry_run: bool = False,
    ) -> bool:
        start = fix_addr(start)
        end = start + io_size
        addr = start
        if start & 0xFFF and not really_erase:
            raise ValueError(f"Start address not on 4K boundary; sector erase needed")

        # start is NOT on sector boundary
        if addr & 0xFFF:
            if verbose:
                print("Writing unaligned data...")
            # erase sector containing data start
            sector_addr = addr & 0x1FF000
            self.erase_flash_block(
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
                    return True
                self.write_flash_bytes(
                    addr,
                    block,
                    dry_run=dry_run,
                )
                addr += block_size

        assert (addr & 0xFFF) == 0

        # write the rest of data in 4K sectors
        crc = 0
        while True:
            block = io.read(4096)
            block_size = len(block)
            block_empty = not len(block.strip(b"\xff"))
            if not block_size:
                if crc_check:
                    if verbose:
                        print("Verifying CRC")
                    pad_size = 4096 - (io_size % 4096)
                    crc = crc32(b"\xff" * pad_size, crc)
                    crc_chip = self.read_flash_range_crc(
                        start=start,
                        end=start + io_size + pad_size,
                    )
                    if crc != crc_chip:
                        raise ValueError(
                            f"Chip CRC value {crc_chip:X} does not match calculated CRC value {crc:X}"
                        )
                if verbose:
                    print("OK!")
                return True
            # print progress info
            if verbose:
                progress = 100.0 - (end - addr) / io_size * 100.0
                if block_empty:
                    print(f"Erasing at 0x{addr:X} ({progress:.2f}%)")
                else:
                    print(f"Erasing and writing at 0x{addr:X} ({progress:.2f}%)")
            # compute CRC32
            crc = crc32(block, crc)
            self.erase_flash_block(
                addr,
                EraseSize.SECTOR_4K,
                dry_run=dry_run,
            )
            if not block_empty:
                # skip empty blocks
                self.write_flash_4k(
                    addr,
                    block,
                    dry_run=dry_run,
                )
            addr += block_size


__all__ = ["BK7231Serial"]
