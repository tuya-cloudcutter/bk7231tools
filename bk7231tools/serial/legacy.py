#  Copyright (c) Kuba Szczodrzyński 2024-3-5.

from io import BytesIO

from .base import BK7231SerialInterface


class BK7231SerialLegacy(BK7231SerialInterface):
    @property
    def chip_info(self) -> str:
        return (
            self.bk_boot_version
            or (self.chip_type and self.chip_type.name)
            or (self.bk_chip_id and hex(self.bk_chip_id))
            or "Unknown"
        )

    def read_chip_info(self) -> str:
        return self.chip_info

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


# legacy compatibility only - do not use!
# see ChipType, ProtocolType, BootloaderType instead
CHIP_BY_CRC = {
    0xBF9C2D66: ("BK7231N", "1.0.1"),
    0x1EBE6E45: ("BK7231N", "1.0.1"),
    0x0FDCE109: ("BK7231Q", None),
    0x00A5C153: ("BK7231Q", None),
    0x3E13578E: ("BK7231T", "1.0.1"),
    0xB4CE1BB2: ("BK7231T", "1.0.3"),
    0x45AB3E47: ("BK7231T", "1.0.5"),
    0x1A3436AC: ("BK7231T", "1.0.6"),
    0xC6064AF3: ("BK7252", "0.1.3"),
    0x1C5D83D9: ("BK7252", None),
}
