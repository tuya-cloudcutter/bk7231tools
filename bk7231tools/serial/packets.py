# Copyright (c) Kuba Szczodrzyński 2022-06-21.

from dataclasses import astuple, dataclass
from enum import IntEnum
from struct import calcsize, pack, unpack
from typing import Dict, Type


class EraseSize(IntEnum):
    SECTOR_4K = 0x20
    BLOCK_64K = 0xD8


class Packet:
    CODE: int
    FORMAT: str
    IS_LONG: bool = False
    HAS_RESP_OTHER: bool = False
    HAS_RESP_SAME: slice = None

    def serialize(self) -> bytes:
        fields = astuple(self)
        if self.FORMAT.endswith("$"):
            data = pack(self.FORMAT[:-1], *fields[:-1])
            data += fields[-1]
            return data
        return pack(self.FORMAT, *fields)

    @classmethod
    def deserialize(cls, data: bytes) -> "Packet":
        if cls.FORMAT.endswith("$"):
            fmt = cls.FORMAT[:-1]
            size = calcsize(fmt)
            fields = unpack(fmt, data[:size])
            fields += (data[size:],)
        else:
            fields = unpack(cls.FORMAT, data)
        return cls(*fields)


@dataclass
class BkLinkCheckCmnd(Packet):
    CODE = 0x00  # CMD_LinkCheck
    FORMAT = ""
    HAS_RESP_OTHER = True


@dataclass
class BkLinkCheckResp(Packet):
    CODE = 0x01  # CMD_LinkCheck + 1
    FORMAT = "B"
    value: int


@dataclass
class BkReadRegCmnd(Packet):
    CODE = 0x03  # CMD_ReadReg
    FORMAT = "<I"
    HAS_RESP_OTHER = True
    HAS_RESP_SAME = slice(0, 4)
    address: int


@dataclass
class BkReadRegResp(Packet):
    CODE = 0x03  # CMD_ReadReg
    FORMAT = "<II"
    address: int
    value: int


@dataclass
class BkRebootCmnd(Packet):
    CODE = 0x0E  # CMD_Reboot
    FORMAT = "B"
    value: int


@dataclass
class BkSetBaudRateCmnd(Packet):
    CODE = 0x0F  # CMD_SetBaudRate
    FORMAT = "<IB"
    HAS_RESP_SAME = slice(0, 5)
    baudrate: int
    delay_ms: int


@dataclass
class BkCheckCrcCmnd(Packet):
    CODE = 0x10  # CMD_CheckCRC
    FORMAT = "<II"
    HAS_RESP_OTHER = True
    start: int
    end: int


@dataclass
class BkCheckCrcResp(Packet):
    CODE = 0x10  # CMD_CheckCRC
    FORMAT = "<I"
    crc32: int


@dataclass
class BkBootVersionCmnd(Packet):
    CODE = 0x11  # CMD_ReadBootVersion
    FORMAT = ""
    HAS_RESP_OTHER = True


@dataclass
class BkBootVersionResp(Packet):
    CODE = 0x11  # CMD_ReadBootVersion
    FORMAT = "$"
    version: bytes


@dataclass
class BkFlashWriteCmnd(Packet):
    CODE = 0x06  # CMD_FlashWrite
    FORMAT = "<I$"
    IS_LONG = True
    HAS_RESP_OTHER = True
    HAS_RESP_SAME = slice(1, 5)
    start: int
    data: bytes


@dataclass
class BkFlashWriteResp(Packet):
    CODE = 0x06  # CMD_FlashWrite
    FORMAT = "<BIB"
    status: int
    start: int
    written: int


@dataclass
class BkFlashWrite4KCmnd(Packet):
    CODE = 0x07  # CMD_FlashWrite4K
    FORMAT = "<I$"
    IS_LONG = True
    HAS_RESP_OTHER = True
    HAS_RESP_SAME = slice(1, 5)
    start: int
    data: bytes


@dataclass
class BkFlashWrite4KResp(Packet):
    CODE = 0x07  # CMD_FlashWrite4K
    FORMAT = "<BI"
    status: int
    start: int


@dataclass
class BkFlashRead4KCmnd(Packet):
    CODE = 0x09  # CMD_FlashRead4K
    FORMAT = "<I"
    IS_LONG = True
    HAS_RESP_OTHER = True
    HAS_RESP_SAME = slice(1, 5)
    start: int


@dataclass
class BkFlashRead4KResp(Packet):
    CODE = 0x09  # CMD_FlashRead4K
    FORMAT = "<BI$"
    status: int
    start: int
    data: bytes


@dataclass
class BkFlashReg8ReadCmnd(Packet):
    CODE = 0x0C  # CMD_FlashReadSR
    FORMAT = "B"
    IS_LONG = True
    HAS_RESP_OTHER = True
    HAS_RESP_SAME = slice(1, 2)
    cmd: int


@dataclass
class BkFlashReg8ReadResp(Packet):
    CODE = 0x0C  # CMD_FlashReadSR
    FORMAT = "BBB"
    status: int
    cmd: int
    data0: int


@dataclass
class BkFlashReg8WriteCmnd(Packet):
    CODE = 0x0D  # CMD_FlashWriteSR
    FORMAT = "BB"
    IS_LONG = True
    HAS_RESP_OTHER = True
    HAS_RESP_SAME = slice(1, 3)
    cmd: int
    data: int


@dataclass
class BkFlashReg8WriteResp(Packet):
    CODE = 0x0D  # CMD_FlashWriteSR
    FORMAT = "BBB"
    status: int
    cmd: int
    data: int


@dataclass
class BkFlashReg16WriteCmnd(Packet):
    CODE = 0x0D  # CMD_FlashWriteSR
    FORMAT = "<BH"
    IS_LONG = True
    HAS_RESP_OTHER = True
    HAS_RESP_SAME = slice(1, 4)
    cmd: int
    data: int


@dataclass
class BkFlashReg16WriteResp(Packet):
    CODE = 0x0D  # CMD_FlashWriteSR
    FORMAT = "<BBH"
    status: int
    cmd: int
    data: int


@dataclass
class BkFlashReg24ReadCmnd(Packet):
    CODE = 0x0E  # CMD_FlashGetMID
    FORMAT = "<I"
    IS_LONG = True
    HAS_RESP_OTHER = True
    cmd: int


@dataclass
class BkFlashReg24ReadResp(Packet):
    CODE = 0x0E  # CMD_FlashGetMID
    FORMAT = "<BxBBB"
    status: int
    data0: int
    data1: int
    data2: int


@dataclass
class BkFlashEraseBlockCmnd(Packet):
    CODE = 0x0F  # CMD_FlashErase
    FORMAT = "<BI"
    IS_LONG = True
    HAS_RESP_SAME = slice(1, 6)
    erase_size: EraseSize
    start: int

    @classmethod
    def deserialize(cls, data: bytes) -> "Packet":
        packet: "BkFlashEraseBlockCmnd" = super().deserialize(data)
        packet.erase_size = EraseSize(packet.erase_size)


RESPONSE_TABLE: Dict[Type[Packet], Type[Packet]] = {
    # short commands
    BkLinkCheckCmnd: BkLinkCheckResp,  # 0x00 / CMD_LinkCheck
    BkReadRegCmnd: BkReadRegResp,  # 0x03 / CMD_ReadReg
    BkCheckCrcCmnd: BkCheckCrcResp,  # 0x10 / CMD_CheckCRC
    BkBootVersionCmnd: BkBootVersionResp,  # 0x11 / CMD_ReadBootVersion
    # long commands
    BkFlashWriteCmnd: BkFlashWriteResp,  # 0x06 / CMD_FlashWrite
    BkFlashWrite4KCmnd: BkFlashWrite4KResp,  # 0x07 / CMD_FlashWrite4K
    BkFlashRead4KCmnd: BkFlashRead4KResp,  # 0x09 / CMD_FlashRead4K
    BkFlashReg8ReadCmnd: BkFlashReg8ReadResp,  # 0x0c / CMD_FlashReadSR
    BkFlashReg8WriteCmnd: BkFlashReg8WriteResp,  # 0x0d / CMD_FlashWriteSR
    BkFlashReg16WriteCmnd: BkFlashReg16WriteResp,  # 0x0d / CMD_FlashWriteSR
    BkFlashReg24ReadCmnd: BkFlashReg24ReadResp,  # 0x0e / CMD_FlashGetMID
}
