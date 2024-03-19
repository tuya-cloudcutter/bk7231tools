# Copyright (c) Kuba Szczodrzyński 2022-06-21.

from dataclasses import astuple, dataclass
from enum import IntEnum
from struct import calcsize, pack, unpack
from typing import Dict, List, Type

PACKET_CMND_PREAMBLE = b"\x01\xE0\xFC"
PACKET_CMND_LONG = b"\xFF\xF4"
PACKET_RESP_PREAMBLE = b"\x04\x0E"
PACKET_RESP_DATA = b"\x01\xE0\xFC"
PACKET_RESP_LONG = b"\xF4"


class EraseSize(IntEnum):
    SECTOR_4K = 0x20
    BLOCK_64K = 0xD8


class Packet:
    CODE: int
    FORMAT: str
    IS_LONG: bool = False
    HAS_RESP_OTHER: bool = False
    HAS_RESP_SAME: slice = None
    STATUS_FIELDS: List[str] = None
    OFFSET_FIELDS: List[str] = None
    HEX_FIELDS: List[str] = None
    DATA_FIELDS: List[str] = None

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

    def __repr__(self) -> str:
        def repr(field: str) -> str:
            value = getattr(self, field)
            if self.HEX_FIELDS and field in self.HEX_FIELDS:
                return f"{field}=0x{value:X}"
            if self.OFFSET_FIELDS and field in self.OFFSET_FIELDS:
                return f"{field}=0x{value:X}"
            if self.DATA_FIELDS and field in self.DATA_FIELDS:
                return f"{field}=bytes({len(value)})"
            return f"{field}={value}"

        fields = getattr(self.__class__, "__dataclass_fields__")
        return self.__class__.__qualname__ + f"(" + ", ".join(map(repr, fields)) + ")"


@dataclass(repr=False)
class BkLinkCheckCmnd(Packet):
    CODE = 0x00  # CMD_LinkCheck
    FORMAT = ""
    HAS_RESP_OTHER = True


@dataclass(repr=False)
class BkLinkCheckResp(Packet):
    CODE = 0x01  # CMD_LinkCheck + 1
    FORMAT = "B"
    value: int


@dataclass(repr=False)
class BkWriteRegCmnd(Packet):
    CODE = 0x01  # CMD_WriteReg
    FORMAT = "<II"
    HAS_RESP_OTHER = True
    HAS_RESP_SAME = slice(0, 8)
    HEX_FIELDS = ["address", "value"]
    address: int
    value: int


@dataclass(repr=False)
class BkWriteRegResp(Packet):
    CODE = 0x01  # CMD_WriteReg
    FORMAT = "<II"
    HEX_FIELDS = ["address", "value"]
    address: int
    value: int


@dataclass(repr=False)
class BkReadRegCmnd(Packet):
    CODE = 0x03  # CMD_ReadReg
    FORMAT = "<I"
    HAS_RESP_OTHER = True
    HAS_RESP_SAME = slice(0, 4)
    HEX_FIELDS = ["address"]
    address: int


@dataclass(repr=False)
class BkReadRegResp(Packet):
    CODE = 0x03  # CMD_ReadReg
    FORMAT = "<II"
    HEX_FIELDS = ["address", "value"]
    address: int
    value: int


@dataclass(repr=False)
class BkRebootCmnd(Packet):
    CODE = 0x0E  # CMD_Reboot
    FORMAT = "B"
    HEX_FIELDS = ["value"]
    value: int


@dataclass(repr=False)
class BkSetBaudRateCmnd(Packet):
    CODE = 0x0F  # CMD_SetBaudRate
    FORMAT = "<IB"
    HAS_RESP_SAME = slice(0, 5)
    baudrate: int
    delay_ms: int


@dataclass(repr=False)
class BkCheckCrcCmnd(Packet):
    CODE = 0x10  # CMD_CheckCRC
    FORMAT = "<II"
    HAS_RESP_OTHER = True
    OFFSET_FIELDS = ["start", "end"]
    start: int
    end: int


@dataclass(repr=False)
class BkCheckCrcResp(Packet):
    CODE = 0x10  # CMD_CheckCRC
    FORMAT = "<I"
    HEX_FIELDS = ["crc32"]
    crc32: int


@dataclass(repr=False)
class BkBootVersionCmnd(Packet):
    CODE = 0x11  # CMD_ReadBootVersion
    FORMAT = ""
    HAS_RESP_OTHER = True


@dataclass(repr=False)
class BkBootVersionResp(Packet):
    CODE = 0x11  # CMD_ReadBootVersion
    FORMAT = "$"
    version: bytes


@dataclass(repr=False)
class BkFlashWriteCmnd(Packet):
    CODE = 0x06  # CMD_FlashWrite
    FORMAT = "<I$"
    IS_LONG = True
    HAS_RESP_OTHER = True
    HAS_RESP_SAME = slice(1, 5)
    OFFSET_FIELDS = ["start"]
    LONG_FIELDS = ["data"]
    start: int
    data: bytes


@dataclass(repr=False)
class BkFlashWriteResp(Packet):
    CODE = 0x06  # CMD_FlashWrite
    FORMAT = "<BIB"
    STATUS_FIELDS = ["status"]
    OFFSET_FIELDS = ["start"]
    status: int
    start: int
    written: int


@dataclass(repr=False)
class BkFlashWrite4KCmnd(Packet):
    CODE = 0x07  # CMD_FlashWrite4K
    FORMAT = "<I$"
    IS_LONG = True
    HAS_RESP_OTHER = True
    HAS_RESP_SAME = slice(1, 5)
    OFFSET_FIELDS = ["start"]
    DATA_FIELDS = ["data"]
    start: int
    data: bytes


@dataclass(repr=False)
class BkFlashWrite4KResp(Packet):
    CODE = 0x07  # CMD_FlashWrite4K
    FORMAT = "<BI"
    STATUS_FIELDS = ["status"]
    OFFSET_FIELDS = ["start"]
    status: int
    start: int


@dataclass(repr=False)
class BkFlashRead4KCmnd(Packet):
    CODE = 0x09  # CMD_FlashRead4K
    FORMAT = "<I"
    IS_LONG = True
    HAS_RESP_OTHER = True
    HAS_RESP_SAME = slice(1, 5)
    OFFSET_FIELDS = ["start"]
    start: int


@dataclass(repr=False)
class BkFlashRead4KResp(Packet):
    CODE = 0x09  # CMD_FlashRead4K
    FORMAT = "<BI$"
    STATUS_FIELDS = ["status"]
    OFFSET_FIELDS = ["start"]
    DATA_FIELDS = ["data"]
    status: int
    start: int
    data: bytes


@dataclass(repr=False)
class BkFlashReg8ReadCmnd(Packet):
    CODE = 0x0C  # CMD_FlashReadSR
    FORMAT = "B"
    IS_LONG = True
    HAS_RESP_OTHER = True
    HAS_RESP_SAME = slice(1, 2)
    HEX_FIELDS = ["cmd"]
    cmd: int


@dataclass(repr=False)
class BkFlashReg8ReadResp(Packet):
    CODE = 0x0C  # CMD_FlashReadSR
    FORMAT = "BBB"
    HEX_FIELDS = ["cmd", "data0"]
    status: int
    cmd: int
    data0: int


@dataclass(repr=False)
class BkFlashReg8WriteCmnd(Packet):
    CODE = 0x0D  # CMD_FlashWriteSR
    FORMAT = "BB"
    IS_LONG = True
    HAS_RESP_OTHER = True
    HAS_RESP_SAME = slice(1, 3)
    HEX_FIELDS = ["cmd", "data"]
    cmd: int
    data: int


@dataclass(repr=False)
class BkFlashReg8WriteResp(Packet):
    CODE = 0x0D  # CMD_FlashWriteSR
    FORMAT = "BBB"
    HEX_FIELDS = ["cmd", "data"]
    status: int
    cmd: int
    data: int


@dataclass(repr=False)
class BkFlashReg16WriteCmnd(Packet):
    CODE = 0x0D  # CMD_FlashWriteSR
    FORMAT = "<BH"
    IS_LONG = True
    HAS_RESP_OTHER = True
    HAS_RESP_SAME = slice(1, 4)
    HEX_FIELDS = ["cmd", "data"]
    cmd: int
    data: int


@dataclass(repr=False)
class BkFlashReg16WriteResp(Packet):
    CODE = 0x0D  # CMD_FlashWriteSR
    FORMAT = "<BBH"
    HEX_FIELDS = ["cmd", "data"]
    status: int
    cmd: int
    data: int


@dataclass(repr=False)
class BkFlashReg24ReadCmnd(Packet):
    CODE = 0x0E  # CMD_FlashGetMID
    FORMAT = "<I"
    IS_LONG = True
    HAS_RESP_OTHER = True
    HEX_FIELDS = ["cmd"]
    cmd: int


@dataclass(repr=False)
class BkFlashReg24ReadResp(Packet):
    CODE = 0x0E  # CMD_FlashGetMID
    FORMAT = "<BxBBB"
    HEX_FIELDS = ["data0", "data1", "data2"]
    status: int
    data0: int
    data1: int
    data2: int


@dataclass(repr=False)
class BkFlashEraseBlockCmnd(Packet):
    CODE = 0x0F  # CMD_FlashErase
    FORMAT = "<BI"
    IS_LONG = True
    HAS_RESP_SAME = slice(1, 6)
    OFFSET_FIELDS = ["start"]
    erase_size: EraseSize
    start: int

    @classmethod
    def deserialize(cls, data: bytes) -> "Packet":
        packet: "BkFlashEraseBlockCmnd" = super().deserialize(data)
        packet.erase_size = EraseSize(packet.erase_size)
        return packet


RESPONSE_TABLE: Dict[Type[Packet], Type[Packet]] = {
    # short commands
    BkLinkCheckCmnd: BkLinkCheckResp,  # 0x00 / CMD_LinkCheck
    BkWriteRegCmnd: BkWriteRegResp,  # 0x01 / CMD_WriteReg
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
