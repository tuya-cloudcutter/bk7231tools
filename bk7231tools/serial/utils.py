# Copyright (c) Kuba Szczodrzyński 2022-07-06.


def fix_addr(addr: int) -> int:
    addr &= 0x1FFFFF
    addr |= 0x200000
    return addr
