#  Copyright (c) Kuba Szczodrzyński 2024-3-5.

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Optional


class BkChipType(IntEnum):
    BK7231Q = 0x7231
    BK7231U = 0x0001  # not checked
    BK7231T = 0x7231A
    BK7231N = 0x7231C
    BK7238 = 0x7238
    BK7252 = 0x7252


SHORT = 0
LONG = 1


class BkProtocolType(Enum):
    # BK7231N BootROM protocol
    FULL = (
        (0x00, SHORT),  # CMD_LinkCheck
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
        (0x00, SHORT),  # CMD_LinkCheck
        (0x0E, SHORT),  # CMD_Reboot
        (0x0F, SHORT),  # CMD_SetBaudRate
        (0x10, SHORT),  # CMD_CheckCRC
        (0x06, LONG),  # CMD_FlashWrite
        (0x07, LONG),  # CMD_FlashWrite4K
        (0x09, LONG),  # CMD_FlashRead4K
        (0x0F, LONG),  # CMD_FlashErase
    )
    BASIC_TUYA = (
        (0x00, SHORT),  # CMD_LinkCheck
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
class BkBootloader:
    # CRC-32 of first 256 bootloader bytes
    # - BK7231N: CRC of 0..256, end-inclusive (257 bytes)
    # - otherwise: CRC of 0..256, end-exclusive (256 bytes)
    crc: int
    chip: BkChipType
    protocol: BkProtocolType
    version: Optional[str] = None
    flash_size: int = 0
    # for bootloaders that protect flash after every CMD_CheckCRC
    # it can then be unprotected by CMD_FlashErase - only after a CMD_LinkCheck !!!
    # (currently on all known non-BootROM protocols)
    crc_flash_protect_lock: bool = False


class BkBootloaderType(Enum):
    # bl_bk7231n_1.0.1_34B7.bin
    BK7231N_1_0_1 = BkBootloader(
        crc=0xE14191BA,  # 510fb093a3cbeadc5993a17ec7adeb03
        chip=BkChipType.BK7231N,
        protocol=BkProtocolType.FULL,
        version="1.0.1",
    )
    # bl_bk7231q_6AFA.bin
    BK7231Q_1 = BkBootloader(
        crc=0xF0231EF6,  # 00000000000000000000000000000000
        chip=BkChipType.BK7231Q,
        protocol=BkProtocolType.BASIC_BEKEN,
        crc_flash_protect_lock=True,
    )
    # bl_bk7231q_tysdk_03ED.bin
    BK7231Q_2 = BkBootloader(
        crc=0xFF5A3EAC,  # 00000000000000000000000000000000
        chip=BkChipType.BK7231Q,
        protocol=BkProtocolType.BASIC_BEKEN,
        crc_flash_protect_lock=True,
    )
    # bl_bk7231s_1.0.1_79A6.bin
    BK7231S_1_0_1 = BkBootloader(
        crc=0xC1ECA871,  # 510fb093a3cbeadc5993a17ec7adeb03
        chip=BkChipType.BK7231T,
        protocol=BkProtocolType.BASIC_TUYA,
        version="1.0.1",
        flash_size=0x200_000,
        crc_flash_protect_lock=True,
    )
    # bl_bk7231s_1.0.3_DAAE.bin
    BK7231S_1_0_3 = BkBootloader(
        crc=0x4B31E44D,  # 510fb093a3cbeadc5993a17ec7adeb03
        chip=BkChipType.BK7231T,
        protocol=BkProtocolType.BASIC_TUYA,
        version="1.0.3",
        flash_size=0x200_000,
        crc_flash_protect_lock=True,
    )
    # bl_bk7231s_1.0.5_4FF7.bin
    BK7231S_1_0_5 = BkBootloader(
        crc=0xBA54C1B8,  # 510fb093a3cbeadc5993a17ec7adeb03
        chip=BkChipType.BK7231T,
        protocol=BkProtocolType.BASIC_TUYA,
        version="1.0.5",
        flash_size=0x200_000,
        crc_flash_protect_lock=True,
    )
    # bl_bk7231s_1.0.6_625D.bin
    BK7231S_1_0_6 = BkBootloader(
        crc=0xE5CBC953,  # 510fb093a3cbeadc5993a17ec7adeb03
        chip=BkChipType.BK7231T,
        protocol=BkProtocolType.BASIC_TUYA,
        version="1.0.6",
        flash_size=0x200_000,
        crc_flash_protect_lock=True,
    )
    # bl_bk7231u_1.0.6_9B7F.bin
    BK7231U_1_0_6 = BkBootloader(
        crc=0x2739019F,  # 00000000000000000000000000000000
        chip=BkChipType.BK7231U,
        protocol=BkProtocolType.BASIC_BEKEN,
        version="1.0.6",
        flash_size=0x200_000,
        crc_flash_protect_lock=True,
    )
    # bl_bk7252_0.1.3_F4D3.bin
    BK7252_0_1_3 = BkBootloader(
        crc=0x39F9B50C,  # 00000000000000000000000000000000
        chip=BkChipType.BK7252,
        protocol=BkProtocolType.BASIC_BEKEN,
        version="0.1.3",
        crc_flash_protect_lock=True,
    )
    # bootloader_7252_2M_uart1_log_20190828.bin
    BK7252_SDK = BkBootloader(
        crc=0xE3A27C26,  # 00000000000000000000000000000000
        chip=BkChipType.BK7252,
        protocol=BkProtocolType.BASIC_BEKEN,
        crc_flash_protect_lock=True,
    )

    @staticmethod
    def get_by_crc(crc: int) -> Optional["BkBootloaderType"]:
        for item in BkBootloaderType:
            if item.value.crc == crc:
                return item
        return None
