from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class FlashPartition:
    name: str
    size: int
    start_address: int
    mapped_address: int


@dataclass(frozen=True)
class FlashLayout:
    name: str
    partitions: List[FlashPartition]
    with_crc: bool


FLASH_LAYOUTS = {
    "ota_1": FlashLayout(name="ota_1",
                         with_crc=True,
                         partitions=[
                             FlashPartition(name="bootloader", size=68*1024, start_address=0x00000000, mapped_address=0x0),
                             FlashPartition(name="app", size=1150832, start_address=0x00011000, mapped_address=0x10000)
                         ])
}
