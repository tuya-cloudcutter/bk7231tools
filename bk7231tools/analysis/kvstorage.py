#  Copyright (c) Kuba Szczodrzyński 2023-11-12.

import json
import re
from dataclasses import dataclass
from io import SEEK_END, SEEK_SET
from json import JSONDecodeError
from logging import warning
from typing import Dict, List, Optional, Tuple, Union

from Crypto.Cipher import AES
from datastruct import Context, DataStruct, datastruct
from datastruct.fields import (
    built,
    checksum_end,
    checksum_field,
    checksum_start,
    crypt,
    crypt_end,
    eval_into,
    field,
    repeat,
    subfield,
    switch,
    tell,
    text,
    validate,
    varlist,
    virtual,
)

KEY_MASTER = b"qwertyuiopasdfgh"
KEY_PART_1 = b"8710_2M"
KEY_PART_2 = b"HHRRQbyemofrtytf"
MAGIC_PROTECTED = 0x13579753
MAGIC_KEY = 0x13579753
MAGIC_DATA_1 = 0x98761234
MAGIC_DATA_2 = 0x135726AB
ASCII = bytes(range(32, 128)) + b"\r\n"


BLOCK_CRYPT = crypt(
    block_size=16,
    init=lambda ctx: ctx.G.root.aes,
    decrypt=lambda data, obj, ctx: obj and obj.decrypt(data) or data,
    encrypt=lambda data, obj, ctx: obj and obj.encrypt(data) or data,
)
BLOCK_CHECKSUM = checksum_field("block checksum")(field("I", default=0))
BLOCK_CHECKSUM_CALC = checksum_start(
    init=lambda ctx: 0,
    update=lambda value, obj, ctx: (obj + sum(value)) & 0xFFFFFFFF,
    end=lambda obj, ctx: obj,
    target=BLOCK_CHECKSUM,
)
BLOCK_PADDING = field(lambda ctx: 4096 - ctx.P.tell())
PAGE_PADDING = field(lambda ctx: 128 - ctx.P.tell())


def block_magic(value: int):
    return built("I", lambda ctx: value, always=False)


def block_magic_check(*values: int):
    return validate(
        check=lambda ctx: ctx.magic in values,
        doc="block magic",
    )


def make_data_aes(inner_key: bytes) -> AES:
    data_key = bytearray(16)
    for i in range(0, 16):
        data_key[i] = KEY_PART_1[i & 0b11] + KEY_PART_2[i]
    for i in range(16):
        data_key[i] = (data_key[i] + inner_key[i]) % 256
    return AES.new(key=data_key, mode=AES.MODE_ECB)


@dataclass
class ProtectedBlock(DataStruct):
    @dataclass
    @datastruct(padding_pattern=b"\x00")
    class Data(DataStruct):
        # sf_protected_data_s
        length: int = built("I", lambda ctx: len(ctx.value))
        key: str = text(32)
        value: bytes = field(lambda ctx: ctx.length)

    # sf_protected_s
    _crypt: ... = BLOCK_CRYPT
    magic: int = block_magic(MAGIC_PROTECTED)
    _magic: ... = block_magic_check(MAGIC_PROTECTED)
    checksum: int = BLOCK_CHECKSUM
    _checksum: ... = BLOCK_CHECKSUM_CALC

    key: bytes = field(16)
    data_length: int = built("I", lambda ctx: ctx.self.sizeof("data"))
    reserved: int = field("I", default=0xFFFFFFFF)

    _crypt_inner: ... = crypt(
        block_size=16,
        init=lambda ctx: make_data_aes(ctx.key),
        decrypt=lambda data, obj, ctx: obj.decrypt(data),
        encrypt=lambda data, obj, ctx: obj.encrypt(data),
    )
    data_start: int = tell()
    data: List[Data] = varlist(
        when=lambda ctx: ctx.P.tell() < ctx.data_start + ctx.data_length,
    )(subfield())
    block_padding: bytes = BLOCK_PADDING
    _crypt_inner_end: ... = crypt_end(_crypt_inner)

    _checksum_end: ... = checksum_end(_checksum)
    _crypt_end: ... = crypt_end(_crypt)


@dataclass
class KeyBlock(DataStruct):
    _crypt: ... = BLOCK_CRYPT
    magic: int = block_magic(MAGIC_KEY)
    _magic: ... = block_magic_check(MAGIC_KEY)
    checksum: int = BLOCK_CHECKSUM
    _checksum: ... = BLOCK_CHECKSUM_CALC

    key: bytes = field(16)

    _checksum_end: ... = checksum_end(_checksum)
    block_padding: bytes = BLOCK_PADDING
    _crypt_end: ... = crypt_end(_crypt)


@dataclass
class DataBlock(DataStruct):
    # noinspection PyProtectedMember
    @dataclass
    @datastruct(padding_pattern=b"\x00")
    class IndexPage(DataStruct):
        @dataclass
        class Part(DataStruct):
            block_id: int = field("H")
            page_id_start: int = field("B")
            page_id_end: int = field("B")

        crc: int = field("I")
        length: int = field("I")
        block_id: int = field("H")
        page_id: int = field("B")
        parts_size: int = field("H")
        element: int = field("I")
        name_len: int = built("B", lambda ctx: len(ctx.name) + 1)
        name: str = text(lambda ctx: ctx.name_len)
        parts_data: List[Part] = repeat(lambda ctx: ctx.parts_size)(subfield())
        page_padding: bytes = PAGE_PADDING

        _id_check: ... = validate(
            check=lambda ctx: ctx.block_id == ctx._.block_id
            and ctx.page_id == ctx._.P.i + 1,
            doc="block and page ID",
        )

    @dataclass
    class DataPage(DataStruct):
        data: bytes = field(128)

    _crypt: ... = BLOCK_CRYPT
    magic: int = block_magic(MAGIC_DATA_1)
    _magic: ... = block_magic_check(MAGIC_DATA_1, MAGIC_DATA_2)
    checksum: int = BLOCK_CHECKSUM
    _checksum: ... = BLOCK_CHECKSUM_CALC

    block_id: int = field("H")
    unknown: int = field("I")
    map_size: int = field("B")
    map_data: List[int] = repeat(lambda ctx: ctx.map_size)(field("B"))
    page_padding: bytes = PAGE_PADDING

    @staticmethod
    def is_index_page(ctx: Context) -> bool:
        i = ctx.P.i + 1
        return bool(ctx.map_data[i // 8] & (1 << i % 8))

    pages: List[Union[DataPage, IndexPage]] = repeat(count=4096 // 128 - 1)(
        switch(is_index_page)(
            _True=(IndexPage, subfield()),
            _False=(DataPage, subfield()),
        )
    )

    _checksum_end: ... = checksum_end(_checksum)
    _crypt_end: ... = crypt_end(_crypt)


# noinspection PyProtectedMember
@dataclass
class KVStorage(DataStruct):
    key_block: KeyBlock = subfield()
    _data_aes: ... = eval_into(
        "aes", lambda ctx: ctx.aes and make_data_aes(ctx.key_block.key)
    )

    @staticmethod
    def check_end(ctx: Context) -> int:
        pos = ctx.G.tell()
        ctx.G.seek(0, SEEK_END)
        end = ctx.G.tell()
        ctx.G.seek(pos, SEEK_SET)
        return end

    _data_end: int = virtual(check_end)
    data_blocks: List[DataBlock] = repeat(
        when=lambda ctx: ctx.G.tell() < ctx._data_end,
    )(subfield())

    @staticmethod
    def find_storage(data: bytes) -> Optional[Tuple[int, bytes]]:
        aes = AES.new(key=KEY_MASTER, mode=AES.MODE_ECB)
        magic = aes.encrypt(b"\xFF" * 16)
        try:
            pos = data.index(magic)
            pos -= 32  # rewind to block start
        except ValueError:
            return None
        return pos, data[pos:]

    @staticmethod
    def find_user_param_key(data: bytes) -> Optional[Tuple[int, str]]:
        patterns = [b",crc:", b",module:", b"Jsonver:"]
        pos = -1
        for pattern in patterns:
            match_found = False
            pos = data.find(pattern, 0)
            while pos != -1:
                if data[pos + len(pattern)] != 0x00:
                    match_found = True
                    break
                pos = data.find(pattern, pos + 1)
            if match_found:
                break
        if pos == -1:
            return None
        start = data.rfind(b"\x00", 0, pos) + 1
        if not start:
            return None
        end = data.find(b"\x00", start)
        if end == -1:
            return None
        return start, data[start:end].decode()

    @staticmethod
    def parse_user_param_key(value: str) -> dict:
        value = re.sub(r"([^{}\[\]:,]+)", r'"\1"', value)
        value = re.sub(r'"([1-9][0-9]*|0)"', r"\1", value)
        value = re.sub(",}", "}", value)
        value = json.loads(value)
        value = dict(sorted(value.items()))
        return value

    @staticmethod
    def decrypt_and_unpack(
        data: bytes,
        find: bool = False,
        key: bytes = KEY_MASTER,
    ) -> "KVStorage":
        if find:
            result = KVStorage.find_storage(data)
            if result is None:
                raise RuntimeError("KV storage not found in input data")
            _, data = result
        aes = AES.new(key=key, mode=AES.MODE_ECB)
        return KVStorage.unpack(data, aes=aes)

    def __post_init__(self) -> None:
        self.blocks: Dict[
            int, Dict[int, Union[DataBlock.IndexPage, DataBlock.DataPage]]
        ] = {}
        self.indexes: Dict[str, DataBlock.IndexPage] = {}

        for block in self.data_blocks:
            block_id = block.block_id
            if block_id in self.blocks:
                # skip swap blocks
                continue

            block_pages = self.blocks[block_id] = {}
            for i, page in enumerate(block.pages):
                page_id = i + 1
                block_pages[page_id] = page
                if not isinstance(page, DataBlock.IndexPage):
                    continue

                if block_id != page.block_id:
                    raise RuntimeError(
                        f"Block ID mismatch: in_block={page_id}, "
                        f"in_page={page.block_id}"
                    )
                if page_id != page.page_id:
                    raise RuntimeError(
                        f"Page ID mismatch: index={page_id}, id={page.page_id}"
                    )

                if page.name in self.indexes:
                    warning(f"Duplicate index for '{page.name}': {page}")
                    continue
                self.indexes[page.name] = page

    def read_value(self, index: DataBlock.IndexPage) -> bytes:
        value = b""
        for part in index.parts_data:
            block_id = part.block_id
            if block_id not in self.blocks:
                raise RuntimeError(f"Block by ID {block_id} does not exist")
            for page_id in range(part.page_id_start, part.page_id_end + 1):
                page = self.blocks[block_id].get(page_id, None)
                if page is None:
                    raise RuntimeError(
                        f"Page by ID {page_id} does not exist in block {block_id}"
                    )
                if not isinstance(page, DataBlock.DataPage):
                    raise RuntimeError(f"Page is not a DataPage, but {type(page)}")
                value += page.data
        return value[0 : index.length]

    def read_value_parsed(self, index: DataBlock.IndexPage) -> Union[str, dict, list]:
        value = self.read_value(index)
        # non-binary string
        value = value.rstrip(b"\x00")
        if all(c in ASCII for c in value):
            value = value.decode()
        else:
            return f"HEX:{value.hex()}"
        # standard JSON
        try:
            return json.loads(value)
        except JSONDecodeError:
            pass
        # Tuya's weird JSON
        if index.name == "user_param_key":
            return self.parse_user_param_key(value)
        # something else?
        return value

    def read_all_values(self) -> Dict[str, bytes]:
        result = {}
        for name, index in self.indexes.items():
            result[name] = self.read_value(index)
        return result

    def read_all_values_parsed(self) -> Dict[str, Union[str, dict, list]]:
        result = {}
        for name, index in self.indexes.items():
            result[name] = self.read_value_parsed(index)
        return result

    @property
    def length(self) -> int:
        return 0x1000 + len(self.blocks) * 0x1000
