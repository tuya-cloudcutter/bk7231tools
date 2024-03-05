#  Copyright (c) Kuba Szczodrzyński 2024-3-5.

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ChipType(Enum):
    BK7231Q = 0x7231
    BK7231T = 0x7231A
    BK7231N = 0x7231C
    BK7252 = 0x7252


SHORT = 0
LONG = 1


class ProtocolType(Enum):
    # BK7231N BootROM protocol
    FULL = (
        (0x01, SHORT),  # CMD_WriteReg
        (0x03, SHORT),  # CMD_ReadReg
        (0x0E, SHORT),  # CMD_Reboot
        (0x0F, SHORT),  # CMD_SetBaudRate
        (0x10, SHORT),  # CMD_CheckCRC
        (0x70, SHORT),  # CMD_RESET
        (0xAA, SHORT),  # CMD_StayRom
        (0x06, LONG),  # CMD_FlashWrite
        (0x07, LONG),  # CMD_FlashWrite4K
        (0x08, LONG),  # CMD_FlashRead
        (0x09, LONG),  # CMD_FlashRead4K
        (0x0A, LONG),  # CMD_FlashEraseAll
        (0x0B, LONG),  # CMD_FlashErase4K
        (0x0C, LONG),  # CMD_FlashReadSR
        (0x0D, LONG),  # CMD_FlashWriteSR
        (0x0E, LONG),  # CMD_FlashGetMID
        (0x0F, LONG),  # CMD_FlashErase
    )
    BASIC_BEKEN = (
        (0x0E, SHORT),  # CMD_Reboot
        (0x0F, SHORT),  # CMD_SetBaudRate
        (0x10, SHORT),  # CMD_CheckCRC
        (0x06, LONG),  # CMD_FlashWrite
        (0x07, LONG),  # CMD_FlashWrite4K
        (0x09, LONG),  # CMD_FlashRead4K
        (0x0F, LONG),  # CMD_FlashErase
    )
    BASIC_TUYA = (
        (0x0E, SHORT),  # CMD_Reboot
        (0x0F, SHORT),  # CMD_SetBaudRate
        (0x10, SHORT),  # CMD_CheckCRC
        (0x11, SHORT),  # CMD_ReadBootVersion
        (0x06, LONG),  # CMD_FlashWrite
        (0x07, LONG),  # CMD_FlashWrite4K
        (0x09, LONG),  # CMD_FlashRead4K
        (0x0F, LONG),  # CMD_FlashErase
    )


@dataclass
class Bootloader:
    # CRC of first 256 bootloader bytes
    # NOTE: the values here are RAW, as received from the chip.
    # They need to be XOR'ed to represent the real CRC.
    # - BK7231N: CRC of 0..256, end-inclusive (257 bytes)
    # - otherwise: CRC of 0..256, end-exclusive (256 bytes)
    crc: int
    chip: ChipType
    protocol: ProtocolType
    version: Optional[str]


class BootloaderType(Enum):
    # bl_bk7231n_1.0.1_34B7.bin
    BK7231N_1_0_1 = Bootloader(
        0x1EBE6E45,
        ChipType.BK7231N,
        ProtocolType.FULL,
        "1.0.1",
    )
    # bl_bk7231q_6AFA.bin
    BK7231Q_1 = Bootloader(
        0x0FDCE109,
        ChipType.BK7231Q,
        ProtocolType.BASIC_BEKEN,
        None,
    )
    # bl_bk7231q_tysdk_03ED.bin
    BK7231Q_2 = Bootloader(
        0x00A5C153,
        ChipType.BK7231Q,
        ProtocolType.BASIC_BEKEN,
        None,
    )
    # bl_bk7231s_1.0.1_79A6.bin
    BK7231S_1_0_1 = Bootloader(
        0x3E13578E,
        ChipType.BK7231T,
        ProtocolType.BASIC_TUYA,
        "1.0.1",
    )
    # bl_bk7231s_1.0.3_DAAE.bin
    BK7231S_1_0_3 = Bootloader(
        0xB4CE1BB2,
        ChipType.BK7231T,
        ProtocolType.BASIC_TUYA,
        "1.0.3",
    )
    # bl_bk7231s_1.0.5_4FF7.bin
    BK7231S_1_0_5 = Bootloader(
        0x45AB3E47,
        ChipType.BK7231T,
        ProtocolType.BASIC_TUYA,
        "1.0.5",
    )
    # bl_bk7231s_1.0.6_625D.bin
    BK7231S_1_0_6 = Bootloader(
        0x1A3436AC,
        ChipType.BK7231T,
        ProtocolType.BASIC_TUYA,
        "1.0.6",
    )
    # bl_bk7252_0.1.3_F4D3.bin
    BK7252_0_1_3 = Bootloader(
        0xC6064AF3,
        ChipType.BK7252,
        ProtocolType.BASIC_BEKEN,
        "0.1.3",
    )
    # bootloader_7252_2M_uart1_log_20190828.bin
    BK7252_SDK = Bootloader(
        0x1C5D83D9,
        ChipType.BK7252,
        ProtocolType.BASIC_BEKEN,
        None,
    )

    @staticmethod
    def get_by_crc(crc: int) -> Optional["BootloaderType"]:
        crc ^= 0xFFFFFFFF
        for item in BootloaderType:
            if item.value.crc == crc:
                return item
        return None
