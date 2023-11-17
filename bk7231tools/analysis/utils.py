import struct

from .crc16 import crc16


def block_crc_check(block: bytes, crc_bytes: bytes) -> bool:
    calculated = crc16(block, initial_value=0xFFFF)
    unpacked_crc = struct.unpack(">H", crc_bytes)[0] & 0xFFFF
    return calculated == unpacked_crc
