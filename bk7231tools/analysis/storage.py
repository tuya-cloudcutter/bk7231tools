# Copyright (c) Kuba Szczodrzyński 2022-11-16.

import json
import os
import re
from json import JSONDecodeError
from pathlib import Path
from struct import unpack
from typing import List

from Cryptodome.Cipher import AES

from .goto import with_goto

KEY_MASTER = b"qwertyuiopasdfgh"
# FF's encrypted using master key
KEY_MAGIC = "46DCED0E672F3B70AE1276A3F8712E03"
KEY_PART_1 = b"8710_2M"
KEY_PART_2 = b"HHRRQbyemofrtytf"

# don't complain vscode, please
goto = None
label = None


def check_crc(crc_read: int, data: bytearray) -> bool:
    out = 0
    for b in data:
        out += b
    crc_calc = out & 0xFFFFFFFF
    if crc_read != crc_calc:
        print(f"\t- invalid CRC: read {crc_read:08x}, calculated {crc_calc:08x}")
        return False
    return True


def check_magic(expected: int, found: int) -> bool:
    if expected != found:
        print(f"\t- invalid magic: expected {expected:08x}, found {found:08x}")
        return False
    return True


class TuyaStorage:
    data: bytearray
    indexes: dict

    def __init__(self, flash_sz: int = 0xE000, swap_flash_sz: int = 0x3000) -> None:
        self.indexes = {}
        self.flash_sz = flash_sz
        self.swap_flash_sz = swap_flash_sz
        self.block_sz = 1 << 12
        self.start_addr = 0x200000 - swap_flash_sz - flash_sz
        self.key_restore_addr = 0x200000 - swap_flash_sz - flash_sz - self.block_sz
        self.flash_key_addr = self.key_restore_addr
        self.block_nums = int(flash_sz // self.block_sz)
        self.swap_block_nums = int(swap_flash_sz // self.block_sz)
        # not sure what that does
        v12 = 1
        while True:
            self.page_sz = (v12 << 7) & 0xFFFF
            self.block_pages = int(self.block_sz // self.page_sz) & 0xFFFF
            v12 *= 2
            if not (self.block_pages > 8 * ((self.page_sz - 15) & 0xFFFF)):
                break
        self.flash_pages = self.block_pages * (self.block_nums & 0xFFFF)
        self.free_pages = self.flash_pages - self.block_nums

    @property
    def length(self):
        return len(self.data)

    def get_output_name(self, key: str, output_directory: str) -> str:
        dumpfile_name = Path(self.dumpfile).stem
        if key:
            return os.path.join(output_directory, f"{dumpfile_name}_storage_{key}.json")
        return os.path.join(output_directory, f"{dumpfile_name}_storage.json")

    @staticmethod
    def make_inner_key(inner_key: bytes) -> bytes:
        key = bytearray(0x10)
        for i in range(0, 16):
            key[i] = KEY_PART_1[i & 3] + KEY_PART_2[i]
        for i in range(16):
            key[i] = (key[i] + inner_key[i]) % 256
        return bytes(key)

    @staticmethod
    def parse_user_param_key(value: str) -> dict:
        value = re.sub(r"([^{}\[\]:,]+)", r'"\1"', value)
        value = re.sub(r'"([1-9][0-9]*|0)"', r"\1", value)
        value = re.sub(",}", "}", value)
        try:
            value = json.loads(value)
        except Exception:
            return None
        value = dict(sorted(value.items()))
        return value

    @staticmethod
    def find_user_param_key(data: bytes) -> dict:
        patterns = [b",crc:", b",module:", b"Jsonver:"]
        pos = -1
        for pattern in patterns:
            pos = data.find(pattern)
            if pos != -1 and data[pos + len(pattern)] != 0x00:
                break
            else:
                pos = -1
        if pos == -1:
            return None
        start = data.rfind(b"\x00", 0, pos) + 1
        if not start:
            return None
        end = data.find(b"\x00", start)
        if end == -1:
            return None
        upk = data[start:end].decode()
        return TuyaStorage.parse_user_param_key(upk)

    def load(self, file: str) -> int:
        self.dumpfile = file
        magic = bytes.fromhex(KEY_MAGIC) * 4
        with open(file, "rb") as f:
            filedata = f.read()
        try:
            pos = filedata.index(magic)
            pos -= 32  # rewind to block start
        except ValueError:
            return None
        self.data = filedata[pos: pos + self.flash_sz + self.swap_flash_sz]
        self.data = bytearray(self.data)
        if len(self.data) != self.flash_sz + self.swap_flash_sz:
            return None
        return pos

    def block(self, i: int, new: bytearray = None) -> bytearray:
        if new:
            self.data[i * self.block_sz: (i + 1) * self.block_sz] = new
            return new
        return self.data[i * self.block_sz: (i + 1) * self.block_sz]

    def page(self, ib: int, ip: int, size: int = 0) -> bytearray:
        if not size:
            size = self.page_sz
        return self.block(ib + 1)[ip * self.page_sz: ip * self.page_sz + size]

    def decrypt(self) -> bool:
        aes = AES.new(KEY_MASTER, AES.MODE_ECB)
        master = self.block(0, aes.decrypt(self.block(0)))
        magic, crc, key = unpack("<II16s", master[0:24])
        if not check_magic(0x13579753, magic):
            return False
        if not check_crc(crc, key):
            return False

        key = self.make_inner_key(key)
        aes = AES.new(key, AES.MODE_ECB)
        for i in range(self.block_nums):
            block = self.block(i + 1, aes.decrypt(self.block(i + 1)))
            magic, crc, _ = unpack("<IIH", block[0:10])
            if not check_magic(0x98761234, magic):
                return False
            if not check_crc(crc, block[8:]):
                return False
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
            value = value.rstrip(b"\x00").decode()
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
                    buf[read: read + data_len - read] = self.page(
                        ib=element["block_id"],
                        ip=k,
                        size=data_len - read,
                    )
                    read = idx["data_len"]
                    break
                buf[read: read + self.page_sz] = self.page(
                    ib=element["block_id"],
                    ip=k,
                )
                k += 1
                read += self.page_sz
            i += 1

        if not check_crc(idx["crc32"], buf[0: idx["data_len"]]):
            return None
        return buf

    @with_goto
    def sf_find_index(self, name: str):
        v9 = 0
        label.label_12
        if v9 >= self.block_nums:
            return None
        v8 = self.page(ib=v9, ip=0)
        j = 0

        while True:
            if j >= v8[14]:
                v9 += 1
                goto.label_12
            if v8[j + 15]:
                break
            label.label_18
            j += 1

        k = 0
        while True:
            if not ((v8[j + 15] >> k) & 1):
                goto.label_17
            v13 = ((8 * j & 0xFF) + k) & 0xFF
            v14, tmp_index = self.make_sf_index((v8[9] << 8) | v8[8], v13)
            if not v14:
                break
            if v14 != 8:
                return None
            label.label_17
            k += 1
            if k == 8:
                goto.label_18

        v15 = len(name)
        if v15 + 1 != tmp_index["name_len"] or name != tmp_index["name"]:
            goto.label_17

        return tmp_index

    def make_sf_index(self, block_id: int, page_id: int):
        v5 = self.page(block_id, page_id, 18)
        v10 = v5[17] + 18
        size = v10 + 4 * ((v5[12] << 8) | v5[11])
        if size > self.page_sz:
            return 8, None
        v4 = self.page(block_id, page_id, size)
        v4 = bytearray(v4)
        # print(v4.hex(" ", -1))
        start = v4[17] + 18
        # v15 = block + i
        v4s = unpack("<IIHBHIB", v4[0:18])
        elements = []
        for i in range(v4s[4]):
            element = unpack("<HBB", v4[start + i * 4: start + i * 4 + 4])
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
            name=v4[18: 18 + v4s[6]].rstrip(b"\x00").decode(),
        )
        self.indexes[idx["name"]] = idx
        return 0, idx
