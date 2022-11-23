import argparse
import base64
import io
import os
import sys
import traceback
from contextlib import closing
from pathlib import Path
from typing import List

from bk7231tools.analysis import flash, rbl, utils
from bk7231tools.analysis.storage import TuyaStorage
from bk7231tools.crypto.code import BekenCodeCipher
from bk7231tools.serial import BK7231Serial


def __add_serial_args(parser: argparse.ArgumentParser):
    parser.add_argument("-d", "--device", required=True, help="Serial device path")
    parser.add_argument(
        "-b",
        "--baudrate",
        type=int,
        default=115200,
        help="Serial device baudrate (default: 115200)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Timeout for operations in seconds (default: 10.0)",
    )
    parser.add_argument(
        "-D",
        "--debug",
        action="store_true",
        default=False,
        help="Visualize serial protocol messages (default: False)",
    )
    return parser


def __ensure_output_dir_exists(output_dir):
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)
    return output_dir


def __generate_payload_output_file_path(dumpfile: str, payload_name: str, output_directory: str, extra_tag: str) -> str:
    dumpfile_name = Path(dumpfile).stem
    return os.path.join(output_directory, f"{dumpfile_name}_{payload_name}_{extra_tag}.bin")


def __decrypt_code_partition(partition: flash.FlashPartition, payload: bytes):
    CODE_PARTITION_COEFFICIENTS = base64.b64decode("UQ+wk6PL6txZk6F+x63rAw==")
    coefficients = (CODE_PARTITION_COEFFICIENTS[i:i+4] for i in range(0, len(CODE_PARTITION_COEFFICIENTS), 4))
    coefficients = tuple(int.from_bytes(i, byteorder='big') for i in coefficients)

    cipher = BekenCodeCipher(coefficients)
    padded_payload = cipher.pad(payload)
    return cipher.decrypt(padded_payload, partition.mapped_address)


def __carve_and_write_rbl_containers(dumpfile: str, layout: flash.FlashLayout, output_directory: str, extract: bool = False, with_rbl: bool = False) -> List[rbl.Container]:
    containers = []
    with open(dumpfile, "rb") as fs:
        indices = rbl.find_rbl_containers_indices(fs)
        if indices:
            print("RBL containers:")
            for idx in indices:
                print(f"\t{idx:#x}: ", end="")
                container = None
                try:
                    fs.seek(idx, os.SEEK_SET)
                    container = rbl.Container.from_bytestream(fs, layout)
                except ValueError as e:
                    print(f"FAILED TO PARSE - {e.args[0]}")
                if container is not None:
                    containers.append(container)
                    if container.payload is not None:
                        print(
                            f"{container.header.name} - [encoding_algorithm={container.header.algo.name}, size={len(container.payload):#x}]")
                        partition = layout.partitions[0]
                        for p in layout.partitions:
                            if p.name == container.header.name:
                                partition = p
                                break
                        if extract:
                            extra_tag = container.header.version
                            filepath = __generate_payload_output_file_path(
                                dumpfile=dumpfile, payload_name=container.header.name, output_directory=output_directory, extra_tag=extra_tag)
                            with open(filepath, "wb") as fsout:
                                container.write_to_bytestream(fsout, payload_only=(not with_rbl))

                            extra_tag = f"{container.header.version}_decrypted"
                            decryptedpath = __generate_payload_output_file_path(
                                dumpfile=dumpfile, payload_name=container.header.name, output_directory=output_directory, extra_tag=extra_tag)
                            with open(decryptedpath, "wb") as fsout:
                                fsout.write(__decrypt_code_partition(partition, container.payload))

                            print(f"\t\textracted to {output_directory}")
                    else:
                        print(f"{container.header.name} - INVALID PAYLOAD")
    return containers


def __scan_pattern_find_payload(dumpfile: str, partition_name: str, layout: flash.FlashLayout, output_directory: str, extract: bool = False):
    if not partition_name in {p.name for p in layout.partitions}:
        raise ValueError(f"Partition name {partition_name} is unknown in layout {layout.name}")

    final_payload_data = None
    partition = list(filter(lambda p: p.name == partition_name, layout.partitions))[0]
    with open(dumpfile, "rb") as fs:
        fs.seek(partition.start_address, os.SEEK_SET)
        data = fs.read(partition.size)
        i = partition.size
        while i > 0:
            datablock = data[i-16:i]
            # Scan for a block of 16 FF bytes, indicating padding at the end of a partition.
            # This is to ignore RBL headers and other metadata while scanning.
            if datablock == (b"\xFF" * 16):
                break
            i -= 16
        if i <= 0:
            raise ValueError(f"Could not find end of partition for {partition.name}")

        # Now do a pattern scan until we hit the first CRC-16 block
        # and the padding block right before it
        while i > 0:
            datablock = data[i-16:i]
            if datablock != (b"\xFF" * 16) and data[i-32:i-16] == (b"\xFF" * 16):
                # This is exactly after the last 0xFF padding block including its CRC-16 checksum
                i = (i - 16 + 2)
                break
            i -= 16
        payload = data[:i]

        # Extra check for dealing with weird dumps, this essentially
        # changes the pattern scan to purely a moving block read
        # and CRC validation from the start of the partition
        if not payload:
            fs.seek(partition.start_address, os.SEEK_SET)
            payload = fs.read(partition.size)

        block_io_stream = io.BytesIO(payload)
        final_payload = io.BytesIO()
        block = block_io_stream.read(32)
        first = True
        while block:
            crc_bytes = block_io_stream.read(2)
            if not utils.block_crc_check(block, crc_bytes):
                if first:
                    raise ValueError(f"First block level CRC-16 checks failed while analyzing partition {partition.name}")
                else:
                    # One of the CRC checks after the first one has failed, so either
                    # end of stream has been reached or the dump is mangled.
                    # In both cases, not much to do hence bail out assuming it's fine
                    break
            first = False
            final_payload.write(block)
            block = block_io_stream.read(32)

        final_payload_data = final_payload.getbuffer()

    if final_payload_data is not None:
        print(f"\t{partition.start_address:#x}: {partition.name} - [NO RBL, size={len(final_payload_data):#x}]")
        if extract:
            extra_tag = "pattern_scan"
            filepath = __generate_payload_output_file_path(dumpfile, payload_name=partition_name,
                                                           output_directory=output_directory, extra_tag=extra_tag)
            with open(filepath, "wb") as fs:
                fs.write(final_payload_data)

            extra_tag = "pattern_scan_decrypted"
            decryptedpath = __generate_payload_output_file_path(dumpfile, payload_name=partition_name,
                                                                output_directory=output_directory, extra_tag=extra_tag)
            with open(decryptedpath, "wb") as fs:
                fs.write(__decrypt_code_partition(partition, final_payload_data))
            print(f"\t\textracted to {output_directory}")

    return final_payload_data


def dissect_dump_file(args):
    dumpfile = args.file
    flash_layout = args.layout
    default_output_dir = os.getcwd()
    output_directory = args.output_dir or default_output_dir
    layout = flash.FLASH_LAYOUTS.get(flash_layout, None)

    if output_directory != default_output_dir and not args.extract:
        print("Output directory is different from default: assuming -e (extract) is desired")
        args.extract = True

    if args.extract:
        output_directory = __ensure_output_dir_exists(output_directory)

    containers = __carve_and_write_rbl_containers(dumpfile=dumpfile, layout=layout,
                                                  output_directory=output_directory, extract=args.extract, with_rbl=args.rbl)
    container_names = {container.header.name for container in containers if container.payload is not None}
    missing_rbl_containers = {part.name for part in layout.partitions} - container_names
    for missing in missing_rbl_containers:
        print(f"Missing {missing} RBL container. Using a scan pattern instead")
        __scan_pattern_find_payload(dumpfile, partition_name=missing, layout=layout,
                                    output_directory=output_directory, extract=args.extract)

    storage = TuyaStorage()
    print("Storage partition:")
    pos = storage.load(dumpfile)
    if pos is None:
        print("\t- not found!")
        return
    if not storage.decrypt():
        print("\t- failed to decrypt!")
        return
    keys = storage.find_all_keys()
    print(f"\t{pos:#06x}: {storage.length // 1024:d} KiB - {len(keys)} keys")
    if args.extract:
        storage.extract_all(output_directory, separate_keys=args.storage)
    else:
        print("\n".join(f"\t- '{key}'" for key in keys))


def connect_device(device, baudrate, timeout, debug):
    s = BK7231Serial(device, baudrate, timeout, debug_hl=debug)
    items = [
        f"Chip info: {s.chip_info}",
        f"Flash ID: {s.flash_id.hex(' ', -1) if s.flash_id else None}",
        f"Protocol: {s.protocol_type.name}",
    ]
    print("Connected!", " / ".join(items))
    return s


def chip_info(device: BK7231Serial, args):
    pass  # chip info is always printed by connect_device()


def read_flash(device: BK7231Serial, args):
    if args.deprecated_start is not None:
        print("WARNING! --start-address is deprecated: please use --start instead.")
        if args.start is not None:
            print("Both --start-address and --start provided. Cannot continue.")
            exit(1)
        args.start = args.deprecated_start

    if args.deprecated_count is not None:
        print("WARNING! -c/--count is deprecated: please use -l/--length <bytes> instead.")
        if args.length is not None:
            print("Both --count and --length provided. Cannot continue.")
            exit(1)
        args.length = args.deprecated_count * 0x1000

    args.start = args.start or 0x000000

    if args.length and args.start + args.length > 0x200000:
        print(f"Reading 0x{args.length:X} bytes at 0x{args.start:X} would go past the flash memory end")
        exit(1)

    args.length = args.length or (0x200000 - args.start)

    print(f"Reading {args.length} bytes from 0x{args.start:X}")

    with open(args.file, "wb") as fs:
        for data in device.flash_read(args.start, args.length, not args.no_verify_checksum):
            fs.write(data)


def write_flash(device: BK7231Serial, args):
    args.start = args.start or 0x000000
    args.skip = args.skip or 0x000000

    if args.start < 0x11000 and not args.bootloader:
        print(f"The start offset you specified (0x{args.start:06X}) will overwrite the bootloader area.")
        print("If that's really what you want, pass the additional -B/--bootloader flag.")
        print("This can only be used on BK7231N, otherwise it will probably render the device unusable (and unrecoverable).")
        print("** Passing the -B flag will not check for chip type **")
        exit(1)

    try:
        size = os.stat(args.file).st_size - args.skip
    except FileNotFoundError:
        print("Input file doesn't exist")
        exit(1)

    if args.length:
        if args.length > size:
            print("Length is bigger than entire file size")
            exit(1)
        if args.start + args.length > 0x200000:
            print(f"Writing 0x{args.length:X} bytes at 0x{args.start:X} would go past the flash memory end")
            exit(1)
        size = args.length

    print(f"Writing {size} bytes to 0x{args.start:X}")

    with open(args.file, "rb") as fs:
        fs.seek(args.skip, os.SEEK_SET)
        device.program_flash(
            io=fs,
            io_size=size,
            start=args.start,
            verbose=True,
            crc_check=not args.no_verify_checksum,
            dry_run=False,
        )


def parse_args():
    parser = argparse.ArgumentParser(
        prog="bk7231tools",
        description="Utilities to interact with BK7231 chips over serial and analyze their artifacts",
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="subcommand to execute")

    parser_chip_info = subparsers.add_parser("chip_info", help="Show chip information")
    parser_chip_info = __add_serial_args(parser_chip_info)
    parser_chip_info.set_defaults(handler=chip_info)
    parser_chip_info.set_defaults(device_required=True)

    parser_read_flash = subparsers.add_parser("read_flash", help="Read data from flash")
    parser_read_flash = __add_serial_args(parser_read_flash)
    parser_read_flash.add_argument("file", help="File to store flash data")
    parser_read_flash.add_argument(
        "-s",
        "--start",
        type=lambda x: int(x, 0),
        help="Starting address to read from [dec/hex] (default: 0x000000)",
    )
    parser_read_flash.add_argument(
        "-l",
        "--length",
        type=lambda x: int(x, 0),
        help="Length to read from flash, in bytes [dec/hex] (default: 0x200000 = 2 MiB)",
    )
    parser_read_flash.add_argument(
        "--no-verify-checksum",
        dest="no_verify_checksum",
        action="store_true",
        default=False,
        help="Do not verify checksum of retrieved flash segments - not recommended (default: False)",
    )
    parser_read_flash.add_argument(
        "--start-address",
        dest="deprecated_start",
        type=lambda x: int(x, 16),
        required=False,
        help=argparse.SUPPRESS,
    )
    parser_read_flash.add_argument(
        "-c",
        "--count",
        dest="deprecated_count",
        type=int,
        required=False,
        help=argparse.SUPPRESS,
    )
    parser_read_flash.set_defaults(handler=read_flash)
    parser_read_flash.set_defaults(device_required=True)

    parser_write_flash = subparsers.add_parser("write_flash", help="Write data to flash")
    parser_write_flash = __add_serial_args(parser_write_flash)
    parser_write_flash.add_argument("file", help="File to write to flash")
    parser_write_flash.add_argument(
        "-s",
        "--start",
        type=lambda x: int(x, 0),
        help="Starting address to write to [dec/hex] (default: 0x000000)",
    )
    parser_write_flash.add_argument(
        "-S",
        "--skip",
        type=lambda x: int(x, 0),
        help="Amount of bytes to skip from **input file** [dec/hex] (default: 0)",
    )
    parser_write_flash.add_argument(
        "-l",
        "--length",
        type=lambda x: int(x, 0),
        help="Length of data to write, in bytes [dec/hex] (default: 0 = entire input file)",
    )
    parser_write_flash.add_argument(
        "--no-verify-checksum",
        dest="no_verify_checksum",
        action="store_true",
        default=False,
        help="Do not verify checksum of written flash segments - not recommended (default: False)",
    )
    parser_write_flash.add_argument(
        "-B",
        "--bootloader",
        dest="bootloader",
        action="store_true",
        default=False,
        help="Allow overwriting bootloader area (not recommended on BK7231T)",
    )
    parser_write_flash.set_defaults(handler=write_flash)
    parser_write_flash.set_defaults(device_required=True)

    parser_dissect_dump = subparsers.add_parser("dissect_dump", help="Dissect and extract RBL containers from flash dump files")
    parser_dissect_dump.add_argument("file", help="Flash dump file to dissect")
    parser_dissect_dump.add_argument("-l", "--layout", default="ota_1", help="Flash layout used to generate the dump file (default: ota_1)")
    parser_dissect_dump.add_argument("-O", "--output-dir", dest="output_dir", default="",
                                     help="Output directory for extracted RBL files (default: current working directory)")
    parser_dissect_dump.add_argument("-e", "--extract", action="store_true", default=False,
                                     help="Extract identified RBL containers instead of outputting information only (default: False)")
    parser_dissect_dump.add_argument("--rbl", action="store_true", default=False,
                                     help="Extract the RBL container instead of just its payload (default: False)")
    parser_dissect_dump.add_argument("--storage", action="store_true", default=False,
                                     help="Extract storage keys into separate files (default: False)")
    parser_dissect_dump.set_defaults(handler=dissect_dump_file)
    parser_dissect_dump.set_defaults(device_required=False)

    return parser.parse_args()


def cli():
    args = parse_args()

    try:
        if args.device_required:
            with closing(connect_device(args.device, args.baudrate, args.timeout, args.debug)) as device:
                args.handler(device, args)
        else:
            args.handler(args)
    except TimeoutError:
        print(traceback.format_exc(), file=sys.stderr)


if __name__ == "__main__":
    cli()
