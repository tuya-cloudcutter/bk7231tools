import struct
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


class BK7231Protocol:
    serial: Serial
    debug_hl: bool = False
    debug_ll: bool = False

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
    ) -> Union[Packet, bool]:
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
