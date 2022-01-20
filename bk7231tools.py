import argparse
import os
import sys
import traceback
from contextlib import closing
from pathlib import Path
from typing import List

from bk7231tools.analysis import flash, rbl
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
    return parser


def __ensure_output_dir_exists(output_dir):
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)
    return output_dir


def dissect_dump_file(args):
    dumpfile = args.file
    flash_layout = args.layout
    output_directory = args.output_dir or os.getcwd()
    layout = flash.FLASH_LAYOUTS.get(flash_layout, None)
    dumpfile_name = Path(dumpfile).stem

    if args.extract:
        output_directory = __ensure_output_dir_exists(output_directory)

    with open(dumpfile, "rb") as fs:
        indices = rbl.find_rbl_containers_indices(fs)
        containers = []
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
                        ending = "" if args.extract else "\n"
                        print(
                            f"{container.header.name} - [encoding_algorithm={container.header.algo.name}, size={len(container.payload):#x}]", end=ending)
                        if args.extract:
                            filepath = os.path.join(
                                output_directory, f"{dumpfile_name}_{container.header.name}_{container.header.version}.bin")
                            with open(filepath, "wb") as fsout:
                                container.write_to_bytestream(fsout, payload_only=(not args.rbl))
                            print(f" - extracted to {filepath}")
                    else:
                        print(f"{container.header.name} - INVALID PAYLOAD")


def connect_device(device, baudrate, timeout):
    return BK7231Serial(device, baudrate, timeout)


def chip_info(device: BK7231Serial, args: List[str]):
    print(device.chip_info)


def read_flash(device: BK7231Serial, args: List[str]):
    with open(args.file, "wb") as fs:
        fs.write(device.read_flash_4k(args.start_address, args.count, not args.no_verify_checksum))


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
        "--start-address",
        dest="start_address",
        type=lambda x: int(x, 16),
        default=0x10000,
        help="Starting address to read from [hex] (default: 0x10000)",
    )
    parser_read_flash.add_argument(
        "-c",
        "--count",
        type=int,
        default=16,
        help="Number of 4K segments to read from flash (default: 16 segments = 64K)",
    )
    parser_read_flash.add_argument(
        "--no-verify-checksum",
        dest="no_verify_checksum",
        action="store_true",
        default=False,
        help="Do not verify checksum of retrieved flash segments and fail if they do not match (default: False)",
    )
    parser_read_flash.set_defaults(handler=read_flash)
    parser_read_flash.set_defaults(device_required=True)

    parser_dissect_dump = subparsers.add_parser("dissect_dump", help="Dissect and extract RBL containers from flash dump files")
    parser_dissect_dump.add_argument("file", help="Flash dump file to dissect")
    parser_dissect_dump.add_argument("-l", "--layout", default="ota_1", help="Flash layout used to generate the dump file (default: ota_1)")
    parser_dissect_dump.add_argument("-O", "--output-dir", dest="output_dir", default="",
                                     help="Output directory for extracted RBL files (default: current working directory)")
    parser_dissect_dump.add_argument("-e", "--extract", action="store_true", default=False,
                                     help="Extract identified RBL containers instead of outputting information only (default: False)")
    parser_dissect_dump.add_argument("--rbl", action="store_true", default=False,
                                     help="Extract the RBL container instead of just its payload (default: False)")
    parser_dissect_dump.set_defaults(handler=dissect_dump_file)
    parser_dissect_dump.set_defaults(device_required=False)

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    try:
        if args.device_required:
            with closing(connect_device(args.device, args.baudrate, args.timeout)) as device:
                args.handler(device, args)
        else:
            args.handler(args)
    except TimeoutError:
        print(traceback.format_exc(), file=sys.stderr)
