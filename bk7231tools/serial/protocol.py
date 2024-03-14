#  Copyright (c) Kuba Szczodrzyński 2024-3-5.

import struct
import sys
from struct import pack, unpack
from textwrap import shorten
from time import sleep
from typing import Callable, Type, Union

from .base import BK7231SerialInterface, Packet
from .base.packets import (
    PACKET_CMND_LONG,
    PACKET_CMND_PREAMBLE,
    PACKET_RESP_DATA,
    PACKET_RESP_LONG,
    PACKET_RESP_PREAMBLE,
    RESPONSE_TABLE,
)
from .legacy import CHIP_BY_CRC

__compat__ = CHIP_BY_CRC


class BK7231SerialProtocol(BK7231SerialInterface):
    def hw_reset(self) -> None:
        # reset the chip using RTS and DTR lines
        self.serial.rts = True
        self.serial.dtr = True
        sleep(0.1)
        self.serial.dtr = False
        sleep(0.1)
        self.serial.rts = False

    def drain(self) -> None:
        tm_prev = self.serial.timeout
        self.serial.timeout = 0.001
        while self.serial.read(1 * 1024) != b"":
            pass
        self.serial.timeout = tm_prev

    def require_protocol(
        self,
        packet: Union[Packet, Type[Packet], int],
        is_long: bool = False,
    ) -> None:
        if self.protocol_type is None:
            return
        if isinstance(packet, int):
            pair = (packet, is_long)
        else:
            pair = (packet.CODE, packet.IS_LONG)
        if pair not in self.protocol_type.value:
            raise NotImplementedError(
                f"Not implemented in protocol {self.protocol_type.name}: "
                f"code={packet.CODE}, is_long={packet.IS_LONG}"
            )

    def check_protocol(
        self,
        packet: Union[Packet, Type[Packet], int],
        is_long: bool = False,
    ) -> bool:
        if self.protocol_type is None:
            return True
        if isinstance(packet, int):
            pair = (packet, is_long)
        else:
            pair = (packet.CODE, packet.IS_LONG)
        if pair not in self.protocol_type.value:
            return False
        return True

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

    def write(self, data: bytes) -> None:
        if data:
            if sys.version_info >= (3, 8):
                self.verbose(f"<- TX: {data.hex(' ')}")
            else:
                self.verbose(f"<- TX: {data.hex()}")
        self.serial.write(data)
        self.serial.flush()

    def read(self, count: int = None, until: bytes = None) -> Union[bytes, int]:
        if count:
            data = self.serial.read(count)
        elif until:
            data = self.serial.read_until(until)
        else:
            data = self.serial.read(1)

        if data:
            if sys.version_info >= (3, 8):
                self.verbose(f"-> RX: {data.hex(' ')}")
            else:
                self.verbose(f"-> RX: {data.hex()}")
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
            if not self.check_protocol(packet):
                return False
        else:
            self.require_protocol(packet)

        self.debug("<- TX:", shorten(str(packet), 64))

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
        if size != len(response):
            raise ValueError(f"Incomplete response read: {len(response)} != {size}")

        if packet.HAS_RESP_SAME:
            command = packet.serialize()
            part = packet.HAS_RESP_SAME
            check_len = part.stop - part.start
            if response[part] != command[:check_len]:
                raise ValueError("Invalid response data payload")
            self.debug(f"-> RX ({size}): Check OK")

        if packet.HAS_RESP_OTHER:
            try:
                response = cls.deserialize(response)
            except struct.error:
                if sys.version_info >= (3, 8):
                    resp = response.hex(" ", -1)
                else:
                    resp = response.hex()
                raise ValueError(f"Couldn't deserialize response: {resp}")
            self.debug(f"-> RX ({size}):", shorten(str(response), 64))
            return response

        return True
