crc32_table = []
for i in range(0, 256):
    c = i
    for j in range(0, 8):
        if c & 1:
            c = 0xEDB88320 ^ (c >> 1)
        else:
            c = c >> 1
    crc32_table.append(c)


def crc32_ver2(crc, buf):
    for c in buf:
        crc = (crc >> 8) ^ crc32_table[(crc ^ c) & 0xff]
    return crc
