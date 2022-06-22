# Copyright (c) Kuba Szczodrzyński 2022-06-21.

from dataclasses import astuple, dataclass
from struct import calcsize, pack, unpack
from typing import Dict, Type


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
class BkRebootCmnd(Packet):
    CODE = 0x0E  # CMD_Reboot
    FORMAT = "B"
    value = "\xA5"


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
    HAS_RESP_SAME = slice(1, 5)
    start: int
    data: bytes


@dataclass
class BkFlashWriteResp(Packet):
    CODE = 0x06  # CMD_FlashWrite
    FORMAT = "<BIB"
    status: int
    start: int
    status2: int


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


RESPONSE_TABLE: Dict[Type[Packet], Type[Packet]] = {
    BkLinkCheckCmnd: BkLinkCheckResp,
    BkCheckCrcCmnd: BkCheckCrcResp,
    BkBootVersionCmnd: BkBootVersionResp,
    BkFlashWriteCmnd: BkFlashWriteResp,
    BkFlashWrite4KCmnd: BkFlashWrite4KResp,
    BkFlashRead4KCmnd: BkFlashRead4KResp,
}
