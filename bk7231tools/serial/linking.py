#  Copyright (c) Kuba Szczodrzyński 2024-3-5.

from binascii import crc32
from time import sleep

from serial import Timeout

from .base import BK7231SerialInterface, BkBootloaderType, BkChipType, BkProtocolType
from .base.packets import (
    BkBootVersionCmnd,
    BkBootVersionResp,
    BkLinkCheckCmnd,
    BkLinkCheckResp,
    BkReadRegCmnd,
    BkSetBaudRateCmnd,
)


class BK7231SerialLinking(BK7231SerialInterface):
    def connect(self):
        # try to communicate
        if not self.wait_for_link(self.link_timeout):
            raise TimeoutError("Timed out attempting to link with chip")
        # update the transmission baud rate
        if self.serial.baudrate != self.baudrate:
            self.set_baudrate(self.baudrate)
        # identify the connected chip
        self.detect_chip()
        # identify the flash type
        try:
            self.flash_read_id()
        except NotImplementedError:
            pass
        if not self.flash_size and self.flash_params:
            self.flash_size = self.flash_params["size"]
        if not self.flash_size and self.bootloader_type.value.flash_size:
            self.flash_size = self.bootloader_type.value.flash_size
        if not self.flash_size:
            self.flash_size = self.flash_detect_size()
            self.flash_size_detected = True

    def close(self):
        if self.serial and not self.serial.closed:
            self.serial.close()
            self.serial = None

    def wait_for_link(self, timeout: float) -> bool:
        tm = Timeout(timeout)
        tm_prev = self.serial.timeout
        self.serial.timeout = 0.005

        command = BkLinkCheckCmnd()
        connected = False
        while not tm.expired():
            try:
                response: BkLinkCheckResp = self.command(command)
                if response and response.value == 0:
                    connected = True
                    break
            except ValueError:
                pass

        self.drain()
        self.serial.timeout = tm_prev
        return connected

    def set_baudrate(self, baudrate: int) -> None:
        command = BkSetBaudRateCmnd(baudrate, delay_ms=20)

        def baudrate_cb():
            self.debug("-- UART: Changing port baudrate")
            sleep(command.delay_ms / 1000 / 2)
            self.serial.baudrate = baudrate

        self.command(command, after_send=baudrate_cb)

    def detect_chip(self) -> None:
        # try bootloader CRC matching first
        # all known protocols support this command
        crc = self.read_flash_range_crc(0, 256)
        self.bootloader_type = BkBootloaderType.get_by_crc(crc)

        if self.bootloader_type:
            # if bootloader is known, set protocol_type and chip_type
            self.protocol_type = self.bootloader_type.value.protocol
            self.chip_type = self.bootloader_type.value.chip
            self.bootloader = self.bootloader_type.value
        else:
            # if bootloader is not known, try to guess the protocol type
            self.chip_type = None
            data = self.flash_read_bytes(start=0, length=256 + 1, crc_check=False)
            if crc == crc32(data[0:257]):
                # BK72xx BootROM protocol - CRC range end-inclusive
                self.protocol_type = BkProtocolType.FULL
            elif crc == crc32(data[0:256]):
                # BK72xx Bootloader protocol - assume minimal command support
                self.protocol_type = BkProtocolType.BASIC_BEKEN
            else:
                # CRC does not match - fail
                raise ValueError("CRC mismatch while checking chip type!")

        if self.check_protocol(BkReadRegCmnd):
            # read BK72xx BootROM SCTRL_CHIP_ID
            self.bk_chip_id = self.register_read(0x800000)
            # match the chip by ID
            if any(c.value == self.bk_chip_id for c in BkChipType):
                self.chip_type = BkChipType(self.bk_chip_id)
            else:
                self.warn(f"Unknown SCTRL_CHIP_ID - {hex(self.bk_chip_id)}")

        if self.check_protocol(BkBootVersionCmnd):
            # read BK7231T boot version
            command = BkBootVersionCmnd()
            response: BkBootVersionResp = self.command(command)
            if response.version != b"\x07":
                self.bk_boot_version = response.version.decode().strip("\x00\x20")
