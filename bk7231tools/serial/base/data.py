#  Copyright (c) Kuba Szczodrzyński 2024-3-5.

from typing import Callable, Optional

from serial import Serial

from .enums import BkBootloader, BkBootloaderType, BkChipType, BkProtocolType


class BK7231SerialData:
    serial: Serial
    baudrate: int
    link_timeout: float
    cmnd_timeout: float

    protocol_type: BkProtocolType = None
    chip_type: Optional[BkChipType] = None
    bootloader_type: Optional[BkBootloaderType] = None
    bootloader: Optional[BkBootloader] = None
    bk_chip_id: Optional[int] = None
    bk_boot_version: Optional[str] = None

    flash_params: dict = None
    flash_id: bytes = None
    flash_size: int = 0
    flash_size_detected: bool = False
    crc_speed_bps: int = 400_000

    read_retries: int = 20
    # flash has limited lifespan so don't do too many retries
    write_retries: int = 3

    warn: Callable = print
    info: Callable = lambda *args: None
    debug: Callable = lambda *args: None
    verbose: Callable = lambda *args: None
