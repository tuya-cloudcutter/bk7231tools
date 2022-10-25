# bk7231tools
This is a collection of tools to interact with and analyze artifacts for BK7231 MCUs.

## Contributors
- [Kuba Szczodrzyński - @kuba2k2](https://github.com/kuba2k2)

## Installation
Install the package from PyPI:
```
pip install bk7231tools
```

## ⚠️ WARNING⚠️
Please be aware that this software is provided without any guarantees from the authors. If you will still use it, then please be aware that:

1. You understand what the software is doing
2. You choose to use it at your own risk
3. The authors cannot be held accountable for any damages that arise.

## Usage
There are a couple of usage modes for this toolset:
- dissecting already extracted flash artifacts; does not require interaction with the device
- chip identification
- reading flash
- writing flash

### Flash reading

**Note:** since version 1.0.0 of this tool, the `--no-verify-checksum` argument is not needed (even for BK7231N). It is recommended to remove that argument, to ensure that the captured dump is valid.

Ensure that the MCU is hooked up to a UART bridge such that:
- `UART_TXD1` on the MCU is hooked up to the `RXD` pin on the UART bridge
- `UART_RXD1` on the MCU is hooked up to the `TXD` pin on the UART bridge

Afterwards, hook up the `GND` and `3v3` line to the MCU off the bridge or some other power source. In case another power source is used, ensure the power source's `GND` line is tied to the UART bridge's `GND` line.

Once the devices are connected, invoke `bk7231tools`. For example, to read all internal flash contents (2 MB in size, that's `0x200000` in hex) off a BK7231T device hooked up to `/dev/ttyUSB0` and into the file `dump.bin`, use:

```sh
# the -s and -l arguments are optional and default to the values provided here
bk7231tools read_flash -d /dev/ttyUSB0 -s 0 -l 0x200000 dump.bin
```

The toolset will then attempt to connect to the MCU and perform the requested operation. During the connection attempt process, it may be the case that the device is not reset (in case RTS signal is not hooked up as well). If that's the case, the connection will fail. In order to remedy this issue, manually reset the device by disconnecting its power (but not the UART bridge!) a few times after issuing the command.

### Dissecting flash dumps
Once a flash dump has been acquired, it can be dissected into its constituents by invoking the `dissect_dump` subcommand. For example, to dissect and extract artifacts from the flash dump file produced by the command in [flash reading](#flash-reading):

```sh
$ bk7231tools dissect_dump -e -O dump_extract_dir dump.bin

RBL containers:
        0x10f9a: bootloader - [encoding_algorithm=NONE, size=0xdd40]
                extracted to dump_extract_dir
        0x129f0a: app - [encoding_algorithm=NONE, size=0xfd340]
                extracted to dump_extract_dir
```
The above command flags are `-e` to extract - otherwise only a listing is shown and `-O` to write the extracted files to the specified directory (`dump_extract_dir`).
Combined with `--rbl`, you can also extract fully reconstructed RBL files for later usage.

Extracted artifacts are dependent on the flash layout supplied, but usually there are two partitions `app` and `bootloader`. If an extracted partition is also a known encrypted code partition (e.g. `app`), its decrypted version is also extracted with the suffix `_decrypted.bin`.

### Writing flash
Writing can be used to restore stock firmware or flash custom firmware. The tool allows to flash a binary file to an arbitrary location in flash (which needs to be 4K-aligned).

The writing process is optimized to not write empty (all 0xFF) blocks, to speed up the UART communication.

The tool can also skip certain amount of bytes from the input file (i.e. to skip uploading the bootloader).

```sh
# write app firmware (from app-only binary file)
# start=0x11000, skip=0, length=(entire file)
bk7231tools write_flash -d /dev/ttyUSB0 -s 0x11000 -S 0 dump_app.bin

# write stock app (from full dump)
# start=0x11000, skip=0x11000, length=0x121000
bk7231tools write_flash -d /dev/ttyUSB0 -s 0x11000 -S 0x11000 -l 0x121000 dump_stock_full_2mb.bin

# write/restore bootloader only (BK7231N only!!)
# start=0, skip=0, length=0x11000
bk7231tools write_flash -d /dev/ttyUSB0 -s 0 -S 0 -l 0x11000 --bootloader dump_stock_full_2mb.bin

# write entire flash dump (BK7231N only!!)
# start=0, skip=0, length=0x200000
bk7231tools write_flash -d /dev/ttyUSB0 -s 0 -S 0 -l 0x200000 --bootloader dump_stock_full_2mb.bin
```
