from binascii import crc32
from io import BytesIO
from time import sleep
from typing import Generator

from serial import Serial, Timeout

from .packets import (
    BkBootVersionCmnd,
    BkBootVersionResp,
    BkCheckCrcCmnd,
    BkCheckCrcResp,
    BkFlashRead4KCmnd,
    BkFlashRead4KResp,
    BkLinkCheckCmnd,
    BkLinkCheckResp,
    BkRebootCmnd,
    BkSetBaudRateCmnd,
)
from .protocol import BK7231Protocol


class BK7231Serial(BK7231Protocol):
    def __init__(
        self,
        port: str,
        baudrate: str,
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
        self.hw_reset()
        if not self.wait_for_link(link_timeout):
            raise TimeoutError("Timed out attempting to link with chip")
        if self.serial.baudrate != baudrate:
            self.set_baudrate(baudrate)
        print(f"Connected! Chip info: {self.read_chip_info()}")

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
        return response.version.decode("utf-8")

    def read_flash_range_crc(self, start: int, end: int) -> int:
        start &= 0x1FFFFF
        end &= 0x1FFFFF
        start |= 0x200000
        end |= 0x200000
        if end <= start:
            end += 0x200000
        command = BkCheckCrcCmnd(start, end)
        response: BkCheckCrcResp = self.command(command)
        return response.crc32 ^ 0xFFFFFFFF

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
        start &= 0x1FFFFF
        start |= 0x200000
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
                crc_expected = self.read_flash_range_crc(addr, addr + 4096)
                crc_found = crc32(response.data)
                if crc_expected != crc_found:
                    raise ValueError(
                        f"Expected CRC value {crc_expected:X} does not match calculated CRC value {crc_found:X}"
                    )
            yield response.data


__all__ = ["BK7231Serial"]
