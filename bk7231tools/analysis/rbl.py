import io
import os
import struct
from dataclasses import astuple, dataclass
from enum import IntFlag
from typing import ClassVar, List
from zlib import crc32

from .flash import FlashLayout
from .utils import block_crc_check


class OTAAlgorithm(IntFlag):
    NONE = 0
    CRYPT_XOR = 1
    CRYPT_AES256 = 2
    COMPRESS_GZIP = 256
    COMPRESS_QUICKLZ = 512
    COMPRESS_FASTLZ = 768


@dataclass
class Header:
    magic: bytes
    algo: OTAAlgorithm
    timestamp: int
    name: str
    version: str
    sn: str
    crc32: int
    hash: int
    size_raw: int
    size_package: int
    info_crc32: int

    FORMAT: ClassVar[struct.Struct] = struct.Struct("<4sII16s24s24sIIIII")
    MAGIC: ClassVar[str] = b"RBL\x00"

    @classmethod
    def from_bytes(cls, data: bytes):
        header = cls(*cls.FORMAT.unpack(data))
        header.algo = OTAAlgorithm(header.algo)
        cls.__validate_data(data, info_crc32=header.info_crc32)
        def __clean_c_string(x): return x[:x.index(b"\x00")].decode()
        header.name, header.version, header.sn = tuple(
            map(__clean_c_string, [header.name, header.version, header.sn]))
        return header

    def to_bytes(self) -> bytes:
        data_tuple = astuple(self)
        def encode_str(x): return x if not isinstance(x, str) else x.encode('utf-8')
        data_tuple = tuple(map(encode_str, data_tuple))
        return self.FORMAT.pack(*data_tuple)

    @classmethod
    def __validate_data(cls, data: bytes, info_crc32: int):
        calculated_crc = crc32(data[:-4])
        if calculated_crc != info_crc32:
            raise ValueError(
                f"Header crc32 {info_crc32:#x} does not match calculated header crc32 {calculated_crc:#x}")


__HEADER_MAGIC_NEEDLE = bytes([Header.MAGIC[0]]), Header.MAGIC[1:]


class Container(object):
    def __init__(self, header: Header, payload: bytes):
        self.header = header
        self.payload = payload

    @classmethod
    def from_bytestream(cls, bytestream: io.BytesIO, flash_layout: FlashLayout = None):
        magic = bytestream.read(len(Header.MAGIC))

        if magic != Header.MAGIC:
            raise ValueError(
                f"Given bytestream magic {magic.hex()}[hex] does not match an RBL container magic")

        if flash_layout and flash_layout.with_crc:
            bytestream.seek(bytestream.tell() - len(magic), os.SEEK_SET)
            headerstream = cls.__create_bytestream_without_crc(bytestream)
            header_byte_count = Header.FORMAT.size
            crc_byte_count = (header_byte_count // 32) * 2
            header = Header.from_bytes(headerstream.read(header_byte_count))
            bytestream.seek(bytestream.tell() + header_byte_count + crc_byte_count, os.SEEK_SET)
        else:
            header_byte_count = Header.FORMAT.size - len(magic)
            header = Header.from_bytes(
                magic + bytestream.read(header_byte_count))

        bytestream = cls.__create_bytestream_for_layout(
            header, bytestream, flash_layout)
        payload = bytestream.read(header.size_package)
        # TODO: implement AES and GZIP support
        if header.algo == OTAAlgorithm.NONE:
            padding = header.size_package - header.size_raw
            payload = payload[:header.size_raw] + (bytes([padding]) * padding)
        payload_crc = crc32(payload)
        if payload_crc != header.crc32:
            payload = None

        return cls(header, payload)

    def write_to_bytestream(self, bytestream: io.BytesIO, payload_only=True):
        if self.payload is None:
            raise ValueError("Container has invalid payload")
        if not payload_only:
            bytestream.write(self.header.to_bytes())
        bytestream.write(self.payload)

    @classmethod
    def __create_bytestream_for_layout(cls, header: Header, bytestream: io.BytesIO, flash_layout: FlashLayout) -> io.BytesIO:
        if flash_layout is None:
            return bytestream
        partition = filter(lambda x: x.name == header.name,
                           flash_layout.partitions).__next__()
        start_position = bytestream.tell()
        package_position = start_position - partition.size
        if package_position < 0:
            raise ValueError(
                f"Partition {header.name} does not have enough bytes for payload")
        new_stream = io.BytesIO()
        package_read_bytes = partition.size - Header.FORMAT.size
        if flash_layout.with_crc:
            package_read_bytes -= (Header.FORMAT.size // 32) * 2
        bytestream.seek(package_position)
        new_stream.write(bytestream.read(package_read_bytes))
        bytestream.seek(start_position, os.SEEK_SET)
        new_stream.seek(0, os.SEEK_SET)
        return new_stream if not flash_layout.with_crc else cls.__create_bytestream_without_crc(new_stream)

    @classmethod
    def __create_bytestream_without_crc(cls, bytestream: io.BytesIO) -> io.BytesIO:
        new_stream = io.BytesIO()
        start_position = bytestream.tell()
        crc_blocks = bytestream.read(36)
        if block_crc_check(crc_blocks[:32], crc_blocks[32:34]):
            bytestream.seek(start_position, os.SEEK_SET)
        elif block_crc_check(crc_blocks[2:34], crc_blocks[34:36]):
            bytestream.seek(start_position+2, os.SEEK_SET)
        else:
            pass

        block = bytestream.read(32)
        while block:
            new_stream.write(block)
            bytestream.read(2)
            block = bytestream.read(32)

        bytestream.seek(start_position, os.SEEK_SET)
        new_stream.seek(0, os.SEEK_SET)
        return new_stream


def find_rbl_containers_indices(bytestream: io.BytesIO) -> List[int]:
    oldpos = bytestream.tell()
    rbl_locations = []
    magic_needle = __HEADER_MAGIC_NEEDLE[0]
    magic_remainder = __HEADER_MAGIC_NEEDLE[1]
    c = bytestream.read(len(magic_needle))
    while c:
        location = bytestream.tell() - 1
        if c == magic_needle:
            remainder = bytestream.read(len(magic_remainder))
            if remainder == magic_remainder:
                rbl_locations.append(location)
        c = bytestream.read(len(magic_needle))
    bytestream.seek(oldpos, os.SEEK_SET)
    return rbl_locations
