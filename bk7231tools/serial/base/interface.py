#  Copyright (c) Kuba Szczodrzyński 2024-3-5.

from typing import IO, Callable, Generator, Tuple, Type, Union

from .data import BK7231SerialData
from .packets import EraseSize, Packet


class BK7231SerialInterface(BK7231SerialData):
    # legacy.py
    chip_info: str

    def read_chip_info(self) -> str: ...

    def read_flash_4k(
        self,
        start: int,
        count: int = 1,
        crc_check: bool = True,
    ) -> bytes: ...

    # linking.py
    def connect(self): ...

    def close(self): ...

    def wait_for_link(self, timeout: float) -> bool: ...

    def set_baudrate(self, baudrate: int) -> None: ...

    def detect_chip(self) -> None: ...

    # protocol.py
    def hw_reset(self) -> None: ...

    def drain(self) -> None: ...

    def require_protocol(
        self,
        packet: Union[Packet, Type[Packet], int],
        is_long: bool = False,
    ) -> None: ...

    def check_protocol(
        self,
        packet: Union[Packet, Type[Packet], int],
        is_long: bool = False,
    ) -> bool: ...

    @staticmethod
    def encode(packet: Packet) -> bytes: ...

    def write(self, data: bytes) -> None: ...

    def read(self, count: int = None, until: bytes = None) -> Union[bytes, int]: ...

    def command(
        self,
        packet: Packet,
        after_send: Callable = None,
        support_optional: bool = False,
    ): ...

    # cmd_ll_chip.py
    def fix_addr(self, addr: int) -> int: ...

    def reboot_chip(self) -> None: ...

    def register_read(self, address: int) -> int: ...

    def register_write(self, address: int, value: int) -> None: ...

    def read_flash_range_crc(self, start: int, end: int) -> int: ...

    def check_crc(self, start: int, data: bytes) -> None: ...

    @property
    def has_crc_flash_protect_lock(self) -> bool:
        raise NotImplementedError()

    # cmd_ll_flash.py
    def flash_read_reg8(self, cmd: int) -> int: ...

    def flash_write_reg8(self, cmd: int, data: int) -> bool: ...

    def flash_write_reg16(self, cmd: int, data: int) -> bool: ...

    def flash_read_reg24(self, cmd: int) -> Tuple[int, int, int]: ...

    def flash_read_sr(self, size: int = 1) -> int: ...

    def flash_write_sr(self, sr: int, size: int = 1, mask: int = 0xFFFF) -> None: ...

    def flash_read_id(self, cmd: int = 0x9F) -> dict: ...

    def flash_read_4k(
        self,
        start: int,
        crc_check: bool = True,
    ) -> bytes: ...

    def flash_write_bytes(
        self,
        start: int,
        data: bytes,
        crc_check: bool = True,
        dry_run: bool = False,
    ) -> None: ...

    def flash_write_4k(
        self,
        start: int,
        data: bytes,
        crc_check: bool = True,
        dry_run: bool = False,
    ) -> None: ...

    def flash_erase_block(
        self,
        start: int,
        size: EraseSize,
        dry_run: bool = False,
    ) -> None: ...

    # cmd_hl_flash.py
    def flash_unprotect(self, mask: int = 0b01111100) -> None: ...

    def flash_detect_size(self) -> int: ...

    def flash_read(
        self,
        start: int,
        length: int,
        crc_check: bool = True,
    ) -> Generator[bytes, None, None]: ...

    def flash_read_bytes(
        self,
        start: int,
        length: int,
        crc_check: bool = True,
    ) -> bytes: ...

    def program_flash(
        self,
        io: IO[bytes],
        io_size: int,
        start: int,
        crc_check: bool = False,
        really_erase: bool = False,
        dry_run: bool = False,
    ) -> Generator[int, None, None]: ...
