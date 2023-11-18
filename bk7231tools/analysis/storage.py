# Copyright (c) Kuba Szczodrzyński 2022-11-16.

import json
import os
from json import JSONDecodeError
from pathlib import Path
from struct import unpack
from typing import List, Optional
from warnings import warn

from .kvstorage import (
    KEY_MASTER,
    MAGIC_DATA_1,
    MAGIC_DATA_2,
    MAGIC_KEY,
    KVStorage,
    make_data_aes,
)


def check_crc(crc_read: int, data: bytes) -> bool:
    out = 0
    for b in data:
        out += b
    crc_calc = out & 0xFFFFFFFF
    if crc_read != crc_calc:
        print(f"\t- invalid CRC: read {crc_read:08x}, calculated {crc_calc:08x}")
        return False
    return True


def check_magic(found: int, *expected: int) -> bool:
    if found not in expected:
        expected = [f"{e:08x}" for e in expected]
        print(f"\t- invalid magic: expected {expected}, found {found:08x}")
        return False
    return True


class TuyaStorage:
    _data: bytearray
    indexes: dict

    def __init__(self, flash_sz: int = 0xE000, swap_flash_sz: int = None) -> None:
        warn(
            "TuyaStorage class is deprecated - please migrate "
            "to KVStorage or update your software version",
            stacklevel=2,
        )
        if swap_flash_sz is not None:
            print("swap_flash_sz= is deprecated")
        self.set_flash_sz(flash_sz)

    @property
    def data(self):
        return self._data

    @property
    def length(self):
        return len(self._data)

    @data.setter
    def data(self, value: bytes):
        self._data = bytearray(value)
        self.set_flash_sz(len(self.data))

    @length.setter
    def length(self, value: int):
        if len(self.data) < value:
            raise ValueError("Data length too short")
        if len(self.data) & 0xFFF:
            raise ValueError("Data length not on 4K boundary")
        self.data = self.data[0:value]

    def set_flash_sz(self, flash_sz: int):
        self.flash_sz = flash_sz
        self.block_sz = 1 << 12
        self.block_nums = int(flash_sz // self.block_sz) - 1
        # not sure what that does
        v12 = 1
        while True:
            self.page_sz = (v12 << 7) & 0xFFFF
            self.block_pages = int(self.block_sz // self.page_sz) & 0xFFFF
            v12 *= 2
            if not (self.block_pages > 8 * ((self.page_sz - 15) & 0xFFFF)):
                break

    def get_output_name(self, key: str, output_directory: str) -> str:
        dumpfile_name = Path(self.dumpfile).stem
        if key:
            return os.path.join(output_directory, f"{dumpfile_name}_storage_{key}.json")
        return os.path.join(output_directory, f"{dumpfile_name}_storage.json")

    @staticmethod
    def make_inner_key(inner_key: bytes) -> bytes:
        return make_data_aes(inner_key=inner_key)

    @staticmethod
    def parse_user_param_key(value: str) -> Optional[dict]:
        try:
            return KVStorage.parse_user_param_key(value)
        except Exception:
            return None

    @staticmethod
    def find_user_param_key(data: bytes) -> Optional[dict]:
        result = KVStorage.find_user_param_key(data)
        if not result:
            return None
        _, upk = result
        return TuyaStorage.parse_user_param_key(upk)

    def load(self, file: str) -> int:
        self.dumpfile = file
        with open(file, "rb") as f:
            filedata = f.read()
        return self.load_raw(filedata)

    def load_raw(
        self, filedata: bytes, allow_incomplete: bool = False
    ) -> Optional[int]:
        result = KVStorage.find_storage(filedata)
        if not result:
            return None
        pos, storage = result
        self.indexes = {}
        self.data = storage
        return pos

    def save(self, file: str):
        with open(file, "wb") as f:
            f.write(self.data)

    def block(self, i: int, new: bytes = None) -> bytes:
        if new:
            self.data[i * self.block_sz : (i + 1) * self.block_sz] = new
            return new
        return self.data[i * self.block_sz : (i + 1) * self.block_sz]

    def page(self, ib: int, ip: int, size: int = 0) -> bytes:
        if not size:
            size = self.page_sz
        return self.block(ib + 1)[ip * self.page_sz : ip * self.page_sz + size]

    def decrypt(self) -> bool:
        try:
            from Crypto.Cipher import AES
        except (ImportError, ModuleNotFoundError):
            raise ImportError(
                "PyCryptodome dependency is required for storage decryption. "
                "Install it with: pip install pycryptodome"
            )

        aes = AES.new(KEY_MASTER, AES.MODE_ECB)
        master = self.block(0, aes.decrypt(self.block(0)))
        magic, crc, key = unpack("<II16s", master[0:24])
        if not check_magic(magic, MAGIC_KEY):
            return False
        if not check_crc(crc, key):
            return False

        aes = make_data_aes(inner_key=key)
        i = 0
        while True:
            block = self.block(i + 1)
            if not block.strip(b"\xFF"):
                # skip empty blocks
                break
            block = self.block(i + 1, aes.decrypt(block))
            magic, crc, _ = unpack("<IIH", block[0:10])
            if not check_magic(magic, MAGIC_DATA_1, MAGIC_DATA_2):
                break
            if not check_crc(crc, block[8:]):
                break
            i += 1
        self.length = i * self.block_sz
        return True

    def find_all_keys(self) -> List[str]:
        # go through all elements, trying to find one that doesn't exist
        self.sf_find_index("abcdef")
        return list(self.indexes.keys())

    def read_all_keys(self) -> dict:
        kv = {}
        for name, index in self.indexes.items():
            value = self.sf_read_from_index(index)
            if not value:
                continue
            value = value.rstrip(b"\x00").decode(errors="replace")
            # standard JSON
            try:
                kv[name] = json.loads(value)
                continue
            except JSONDecodeError:
                pass
            # Tuya's weird JSON
            if name == "user_param_key":
                value = self.parse_user_param_key(value)
            # else an unknown string
            kv[name] = value
        return kv

    def extract_all(self, output_directory: str, separate_keys: bool):
        kv = self.read_all_keys()
        out_name = self.get_output_name(None, output_directory)
        with open(out_name, "w") as f:
            print(f"\t\textracted all keys to {out_name}")
            json.dump(kv, f, indent="\t")
        if not separate_keys:
            return
        for key, value in kv.items():
            out_name = self.get_output_name(key, output_directory)
            with open(out_name, "w") as f:
                print(f"\t\textracted '{key}' to {out_name}")
                json.dump(value, f, indent="\t")

    def sf_read_from_index(self, idx: dict) -> bytearray:
        buf = bytearray(idx["data_len"])
        read = 0
        i = 0
        while i < idx["element_num"]:
            element = idx["elements"][i]
            k = element["start_page_id"]
            while True:
                if k > element["end_page_id"]:
                    break
                data_len = idx["data_len"]
                if read + self.page_sz > data_len:
                    buf[read : read + data_len - read] = self.page(
                        ib=element["block_id"],
                        ip=k,
                        size=data_len - read,
                    )
                    read = idx["data_len"]
                    break
                buf[read : read + self.page_sz] = self.page(
                    ib=element["block_id"],
                    ip=k,
                )
                k += 1
                read += self.page_sz
            i += 1

        if not check_crc(idx["crc32"], buf[0 : idx["data_len"]]):
            return None
        return buf

    def sf_find_index(self, name: str):
        for block_id in range(0, self.block_nums):
            page = self.page(ib=block_id, ip=0)
            map_size = page[14]
            map_data = page[15 : 15 + map_size]
            for map_byte in range(0, map_size):
                if not map_data[map_byte]:
                    continue
                for map_bit in range(0, 8):
                    if not (map_data[map_byte] & (1 << map_bit)):
                        continue
                    page_id = (map_byte * 8) + map_bit
                    tmp_index = self.make_sf_index((page[9] << 8) | page[8], page_id)
                    if not tmp_index:
                        continue
                    if (
                        len(name) + 1 == tmp_index["name_len"]
                        and name == tmp_index["name"]
                    ):
                        return tmp_index
        return None

    def make_sf_index(self, block_id: int, page_id: int):
        v5 = self.page(block_id, page_id, 18)
        v10 = v5[17] + 18
        size = v10 + 4 * ((v5[12] << 8) | v5[11])
        if size > self.page_sz:
            return None
        v4 = self.page(block_id, page_id, size)
        v4 = bytearray(v4)
        # print(v4.hex(" ", -1))
        start = v4[17] + 18
        # v15 = block + i
        v4s = unpack("<IIHBHIB", v4[0:18])
        elements = []
        for i in range(v4s[4]):
            element = unpack("<HBB", v4[start + i * 4 : start + i * 4 + 4])
            element = dict(
                block_id=element[0],
                start_page_id=element[1],
                end_page_id=element[2],
            )
            elements.append(element)
        idx = dict(
            crc32=v4s[0],
            data_len=v4s[1],
            block_id=v4s[2],
            page_id=v4s[3],
            element_num=v4s[4],
            elements=elements,
            name_len=v4s[6],
            name=v4[18 : 18 + v4s[6]].rstrip(b"\x00").decode(),
        )
        self.indexes[idx["name"]] = idx
        return idx
