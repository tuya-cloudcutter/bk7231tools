from .crc16 import crc16

CRC_DATA_SIZE = 32
CRC_SIZE = 2
BK7258_FLASH_BASE = 0x02000000


def crc_packed_size(size: int) -> int:
    if size < 0:
        raise ValueError("Size cannot be negative")
    return (size + CRC_DATA_SIZE - 1) // CRC_DATA_SIZE * (CRC_DATA_SIZE + CRC_SIZE)


def add_crc(data: bytes) -> bytes:
    output = bytearray()

    for offset in range(0, len(data), CRC_DATA_SIZE):
        block = data[offset : offset + CRC_DATA_SIZE].ljust(CRC_DATA_SIZE, b"\xff")
        output.extend(block)
        output.extend(crc16(block, initial_value=0xFFFF).to_bytes(CRC_SIZE, "big"))

    return bytes(output)


def logical_to_physical(address: int, flash_base: int = BK7258_FLASH_BASE) -> int:
    if address < flash_base:
        raise ValueError(
            f"Logical address 0x{address:X} is below flash base 0x{flash_base:X}"
        )

    offset = address - flash_base
    if offset % CRC_DATA_SIZE:
        raise ValueError(
            f"Logical address 0x{address:X} is not {CRC_DATA_SIZE}-byte aligned"
        )

    return offset // CRC_DATA_SIZE * (CRC_DATA_SIZE + CRC_SIZE)


def physical_to_logical(address: int, flash_base: int = BK7258_FLASH_BASE) -> int:
    block_size = CRC_DATA_SIZE + CRC_SIZE
    if address < 0:
        raise ValueError("Physical address cannot be negative")
    if address % block_size:
        raise ValueError(
            f"Physical address 0x{address:X} is not {block_size}-byte aligned"
        )

    return flash_base + address // block_size * CRC_DATA_SIZE
