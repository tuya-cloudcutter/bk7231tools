from typing import Tuple

from .util import uint8, uint16, uint32


def _generate_uint_pn15(index_mask, flag):
    if flag:
        return 0
    PN15_AND_CONST = 0x6371
    val_rshift_5 = uint16(index_mask >> 5)
    val_rshift_5_nibble = val_rshift_5 & 0xF

    xor_lhs = uint16(uint16(index_mask >> 7) + uint16(index_mask * 0x200))
    xor_rhs = uint16(val_rshift_5 * 0x1000) + \
        uint16(val_rshift_5_nibble * 0x100) + \
        uint8(val_rshift_5 * 0x10) + \
        val_rshift_5_nibble

    xor_rhs = xor_rhs & PN15_AND_CONST

    return uint16(xor_lhs ^ xor_rhs)


def _generate_uint_pn16(index_mask, flag):
    if flag:
        return 0
    PN16_AND_CONST = 0x13659
    part1 = ((index_mask >> 13) & 1) + \
            (((index_mask >> 9) & 1) * 2) + \
            (((index_mask >> 5) & 1) * 4) + \
            (((index_mask >> 1) & 1) * 8)

    xor_lhs = ((index_mask & 0x3FF) << 7) + ((index_mask >> 10) & 0x7F)
    xor_rhs = uint32((((index_mask >> 4) & 1) * 0x10000) + (part1 * 0x1000) + (part1 * 0x111))
    xor_rhs = xor_rhs & PN16_AND_CONST

    return uint32(xor_lhs ^ xor_rhs)


def _generate_uint_pn32(index_mask, flag):
    if flag:
        return 0
    PN32_AND_CONST = 0xE519A4F1
    xor_lhs = uint32(index_mask >> 0xF | index_mask << 0x11)
    xor_rhs_start = (index_mask >> 2) & 0xF
    xor_rhs = uint32(xor_rhs_start * 0x10000000) + \
        uint32(xor_rhs_start * 0x01000000) + \
        uint32(xor_rhs_start * 0x00100000) + \
        uint32(xor_rhs_start * 0x00010000) + \
        uint32(xor_rhs_start * 0x00001111)
    xor_rhs = xor_rhs & PN32_AND_CONST
    return xor_lhs ^ xor_rhs


class BekenCodeCipher(object):
    BLOCK_LENGTH_BYTES = 32

    def __init__(self, coefficients: Tuple[int, int, int, int]):
        self._coef0, self._coef1, self._coef2, self._coef3 = coefficients

    def encrypt(self, data: bytes, stream_start_offset: int = 0):
        if (len(data) % self.BLOCK_LENGTH_BYTES) != 0:
            raise ValueError(f"Given data length {len(data)} is not a multiple of block length {self.BLOCK_LENGTH_BYTES}")

        encrypted = bytearray()
        for i in range(0, len(data), self.BLOCK_LENGTH_BYTES):
            block = data[i:i+self.BLOCK_LENGTH_BYTES]
            block_start_offset = (i + stream_start_offset)
            encrypted.extend(self._encrypt_block(block, block_start_offset))

        return encrypted

    def decrypt(self, data: bytes, stream_start_offset: int = 0):
        return self.encrypt(data, stream_start_offset=stream_start_offset)

    def pad(self, data: bytes):
        data_rem = len(data) % self.BLOCK_LENGTH_BYTES
        result = data
        if data_rem != 0:
            result += b"\xFF" * (self.BLOCK_LENGTH_BYTES - data_rem)
        return result

    def _encrypt_block(self, block: bytes, block_start_offset: int):
        if len(block) != self.BLOCK_LENGTH_BYTES:
            raise ValueError(f"Block length must be exactly {self.BLOCK_LENGTH_BYTES} bytes")

        WORD_SIZE = 4

        encrypted = bytearray()
        for i in range(0, len(block), WORD_SIZE):
            word = int.from_bytes(block[i:i+WORD_SIZE], byteorder="little")
            encrypted_word = self._encrypt_word(block_start_offset + i, word)
            encrypted.extend(encrypted_word.to_bytes(WORD_SIZE, byteorder="little"))

        return encrypted

    def _encrypt_word(self, index: int, word: int):
        coef3_highbyte_cond = False
        coef3_1_bit, coef3_2_bit, coef3_4_bit, coef3_8_bit = False, False, False, False

        if (((self._coef3 & 0xff000000) == 0xff000000) or ((self._coef3 & 0xff000000) == 0)):
            coef3_highbyte_cond = True

        if coef3_highbyte_cond:
            coef3_1_bit = coef3_2_bit = coef3_4_bit = coef3_8_bit = True
        if self._coef3 & 1 != 0:
            coef3_1_bit = True
        if self._coef3 & 2 != 0:
            coef3_2_bit = True
        if self._coef3 & 4 != 0:
            coef3_4_bit = True
        if self._coef3 & 8 != 0:
            coef3_8_bit = True

        coef3_4_rsh = self._coef3 >> 4
        coef3_5_rsh = (self._coef3 >> 5) & 3
        coef3_8_rsh = (self._coef3 >> 8) & 3
        coef3_11_rsh = (self._coef3 >> 11) & 3
        index_mask_16_rsh = uint16(index >> 16)
        index_mask_seq = uint16(index >> 8)

        if coef3_5_rsh == 0:
            pn15_word = (uint8(index_mask_16_rsh) + uint16((index >> 24) << 8)) ^ uint16(index)
        elif coef3_5_rsh == 1:
            pn15_word = (uint8(index_mask_16_rsh) + uint16((index >> 24) << 8))
            pn15_word ^= (uint8(index_mask_seq) + uint16(index << 8))
        elif coef3_5_rsh == 2:
            pn15_word = ((index_mask_16_rsh >> 8) + uint16((index >> 16) << 8)) ^ uint16(index)
        else:
            pn15_word = ((index_mask_16_rsh >> 8) + uint16((index >> 16) << 8))
            pn15_word ^= (uint8(index_mask_seq) + uint16(index << 8))

        pn16_word = (index >> coef3_8_rsh) & 0x1ffff
        PN32_SHIFTS = ((0, 0), (8, 24), (16, 16), (24, 8))
        pn32_word = uint32(index >> PN32_SHIFTS[coef3_11_rsh][0] | index << PN32_SHIFTS[coef3_11_rsh][1])

        pn15_index_mask = uint16((self._coef1 >> 16) ^ pn15_word)

        pn16_index_mask = uint8(self._coef1) + (uint8(self._coef1 >> 8) * 0x200)
        pn16_index_mask += uint8(coef3_4_rsh & 1) * 0x100
        pn16_index_mask ^= pn16_word

        pn32_index_mask = pn32_word ^ self._coef0

        pn15_val = _generate_uint_pn15(pn15_index_mask, coef3_1_bit)
        pn16_val = _generate_uint_pn16(pn16_index_mask, coef3_2_bit)
        pn32_val = _generate_uint_pn32(pn32_index_mask, coef3_4_bit)

        final_val = 0 if coef3_8_bit else self._coef2

        word_encryption_mask = pn15_val * 0x10000
        word_encryption_mask += pn16_val

        return word_encryption_mask ^ pn32_val ^ final_val ^ word
