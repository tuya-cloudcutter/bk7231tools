#  Copyright (c) Kuba Szczodrzyński 2024-3-5.

from typing import Callable, Optional

from serial import Serial

from .enums import BootloaderType, ChipType, ProtocolType


class BK7231SerialData:
    serial: Serial
    baudrate: int
    link_timeout: float
    cmnd_timeout: float

    protocol_type: ProtocolType = None
    chip_type: Optional[ChipType] = None
    bootloader_type: Optional[BootloaderType] = None
    bk_boot_version: Optional[str] = None
    bk_chip_id: Optional[int] = None

    flash_params: dict = None
    flash_id: bytes = None
    flash_size: int = 0
    crc_speed_bps: int = 400_000

    read_retries: int = 20
    # flash has limited lifespan so don't do too many retries
    write_retries: int = 3

    warn: Callable = print
    info: Callable = lambda *args: None
    debug: Callable = lambda *args: None
    verbose: Callable = lambda *args: None
