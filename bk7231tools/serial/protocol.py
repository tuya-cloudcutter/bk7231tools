import struct
from enum import Enum
from struct import pack, unpack
from textwrap import shorten
from time import sleep
from typing import Callable, Union

from serial import Serial

from .packets import RESPONSE_TABLE, Packet

PACKET_CMND_PREAMBLE = b"\x01\xE0\xFC"
PACKET_CMND_LONG = b"\xFF\xF4"
PACKET_RESP_PREAMBLE = b"\x04\x0E"
PACKET_RESP_DATA = b"\x01\xE0\xFC"
PACKET_RESP_LONG = b"\xF4"

SHORT = 0
LONG = 1


class ProtocolType(Enum):
    UNKNOWN = []
    # BK7231N BootROM protocol
    FULL = [
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
    ]
    BASIC_TUYA = [
        (0x0E, SHORT),  # CMD_Reboot
        (0x0F, SHORT),  # CMD_SetBaudRate
        (0x10, SHORT),  # CMD_CheckCRC
        (0x11, SHORT),  # CMD_ReadBootVersion
        (0x06, LONG),  # CMD_FlashWrite
        (0x07, LONG),  # CMD_FlashWrite4K
        (0x09, LONG),  # CMD_FlashRead4K
        (0x0F, LONG),  # CMD_FlashErase
    ]
    BASIC_BEKEN = [
        (0x0E, SHORT),  # CMD_Reboot
        (0x0F, SHORT),  # CMD_SetBaudRate
        (0x10, SHORT),  # CMD_CheckCRC
        (0x06, LONG),  # CMD_FlashWrite
        (0x07, LONG),  # CMD_FlashWrite4K
        (0x09, LONG),  # CMD_FlashRead4K
        (0x0F, LONG),  # CMD_FlashErase
    ]
    BASIC_DEFAULT = BASIC_TUYA


# list of protocols with verified command support
# those not listed here will use BASIC_DEFAULT
PROTOCOLS = {
    # 863F_bk7231n_rom.bin
    "0x7231c": ProtocolType.FULL,
    # bl_bk7231s_1.0.1_79A6.bin
    "BK7231S_1.0.1": ProtocolType.BASIC_TUYA,
    # bl_bk7231s_1.0.3_DAAE.bin
    "BK7231S_1.0.3": ProtocolType.BASIC_TUYA,
    # bl_bk7231s_1.0.4_9940.bin
    "BK7231S_1.0.4": ProtocolType.BASIC_TUYA,
    # bl_bk7231s_1.0.5_4FF7.bin
    "BK7231S_1.0.5": ProtocolType.BASIC_TUYA,
    # bl_bk7231s_1.0.6_625D.bin
    "BK7231S_1.0.6": ProtocolType.BASIC_TUYA,
    # bl_bk7231q_6AFA.bin
    "BK7231QN40": ProtocolType.BASIC_BEKEN,
    # bl_bk7252_0.1.3_F4D3.bin
    "BK7252": ProtocolType.BASIC_BEKEN,
}

# CRC of first 256 bootloader bytes
# for chips that don't respond to BootVersion at all
CHIP_BY_CRC = {
    # bl_bk7231q_6AFA.bin
    0xF0231EF6: "BK7231QN40",
    # bl_bk7252_0.1.3_F4D3.bin
    0xC6064AF3: "BK7252",
}


class BK7231Protocol:
    serial: Serial
    debug_hl: bool = False
    debug_ll: bool = False
    protocol_type: ProtocolType = ProtocolType.UNKNOWN

    def __init__(self, serial: Serial) -> None:
        self.serial = serial

    def hw_reset(self):
        self.serial.rts = True
        self.serial.dtr = True
        sleep(0.1)
        self.serial.rts = False
        self.serial.dtr = False

    def drain(self):
        tm_prev = self.serial.timeout
        self.serial.timeout = 0.001
        while self.serial.read(1 * 1024) != b"":
            pass
        self.serial.timeout = tm_prev

    def require_protocol(self, code: int, is_long: bool):
        if self.protocol_type == ProtocolType.UNKNOWN:
            return
        pair = (code, is_long)
        if pair not in self.protocol_type.value:
            raise NotImplementedError(
                f"Not implemented in protocol {self.protocol_type.name}: code={code}, is_long={is_long}"
            )

    def check_protocol(self, code: int, is_long: bool) -> bool:
        if self.protocol_type == ProtocolType.UNKNOWN:
            return True
        pair = (code, is_long)
        if pair not in self.protocol_type.value:
            return False

    @staticmethod
    def encode(packet: Packet) -> bytes:
        out = PACKET_CMND_PREAMBLE
        data = packet.serialize()
        size = len(data) + 1
        if size >= 0xFF or packet.IS_LONG:
            out += PACKET_CMND_LONG
            out += pack("<H", size)
        else:
            out += pack("B", size)
        out += pack("B", packet.CODE)
        out += data
        return out

    def write(self, data: bytes):
        if data and self.debug_ll:
            print(f"<- TX: {data.hex(' ')}")
        self.serial.write(data)
        self.serial.flush()

    def read(self, count: int = None, until: bytes = None) -> Union[bytes, int]:
        if count:
            data = self.serial.read(count)
        elif until:
            data = self.serial.read_until(until)
        else:
            data = self.serial.read(1)

        if data and self.debug_ll:
            print(f"-> RX: {data.hex(' ')}")
        if not count and not until:
            return data[0] if data else 0
        return data

    def command(
        self,
        packet: Packet,
        after_send: Callable = None,
        support_optional: bool = False,
    ) -> Union[Packet, bool]:
        if support_optional:
            if not self.check_protocol(packet.CODE, packet.IS_LONG):
                return False
        else:
            self.require_protocol(packet.CODE, packet.IS_LONG)

        if self.debug_hl:
            print("<- TX:", shorten(str(packet), 64))

        self.write(self.encode(packet))
        if after_send:
            after_send()

        if not packet.HAS_RESP_OTHER and not packet.HAS_RESP_SAME:
            return True

        if packet.HAS_RESP_OTHER:
            cls = RESPONSE_TABLE[type(packet)]
            response_code = cls.CODE
        if packet.HAS_RESP_SAME:
            response_code = packet.CODE

        while True:
            data = self.read(until=PACKET_RESP_PREAMBLE)
            if PACKET_RESP_PREAMBLE != data[-2:]:
                raise ValueError("No response received")

            size = self.read()
            if packet.IS_LONG != (size == 0xFF):
                # Invalid response, so continue reading until a new valid packet is found
                continue

            if PACKET_RESP_DATA != self.read(until=PACKET_RESP_DATA):
                # Invalid packet, so continue reading until a new valid packet is found
                continue

            if packet.IS_LONG:
                if PACKET_RESP_LONG != self.read(until=PACKET_RESP_LONG):
                    # Invalid packet, so continue reading until a new valid packet is found
                    continue
                (size, code) = unpack("<HB", self.read(count=3))
                size -= 1  # code
            else:
                code = self.read()
                size -= 4  # code + PACKET_RESP_DATA

            if code == response_code:
                # Found valid packet header
                break

        response = self.read(count=size)

        if packet.HAS_RESP_SAME:
            command = packet.serialize()
            part = packet.HAS_RESP_SAME
            check_len = part.stop - part.start
            if response[part] != command[:check_len]:
                raise ValueError("Invalid response data payload")
            if self.debug_hl:
                print(f"-> RX ({size}): Check OK")

        if packet.HAS_RESP_OTHER:
            try:
                response = cls.deserialize(response)
            except struct.error:
                raise ValueError(f"Partial response received: {response.hex(' ', -1)}")
            if self.debug_hl:
                print(f"-> RX ({size}):", shorten(str(response), 64))
            return response

        return True
