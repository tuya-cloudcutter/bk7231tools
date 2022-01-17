import argparse
import sys
import traceback
from contextlib import closing
from typing import List

from bk7231serial import BK7231Serial

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


def connect_device(device, baudrate, timeout):
    return BK7231Serial(device, baudrate, timeout)


def chip_info(device: BK7231Serial, args: List[str]):
    print(device.chip_info)


def read_flash(device: BK7231Serial, args: List[str]):
    with open(args.file, "wb") as fs:
        fs.write(device.read_flash_4k(args.start_address, args.count, args.verify_checksum))


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
        "--verify-checksum",
        dest="verify_checksum",
        action="store_true",
        default=True,
        help="Verify checksum of retrieved flash segments and fail if they do not match (default: True)",
    )
    parser_read_flash.set_defaults(handler=read_flash)
    parser_read_flash.set_defaults(device_required=True)

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
