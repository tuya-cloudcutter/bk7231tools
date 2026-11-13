#  Copyright (c) Kuba Szczodrzyński 2024-3-5.

from serial import Serial

from .base import BkChipType
from .cmd_hl_flash import BK7231SerialCmdHLFlash
from .cmd_ll_chip import BK7231SerialCmdLLChip
from .cmd_ll_flash import BK7231SerialCmdLLFlash
from .legacy import BK7231SerialLegacy
from .linking import BK7231SerialLinking
from .protocol import BK7231SerialProtocol


class BK7231Serial(
    BK7231SerialLegacy,
    BK7231SerialProtocol,
    BK7231SerialLinking,
    BK7231SerialCmdLLChip,
    BK7231SerialCmdLLFlash,
    BK7231SerialCmdHLFlash,
):
    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        link_timeout: float = 10.0,
        cmnd_timeout: float = 1.0,
        link_baudrate: int = 115200,
        link_read_timeout: float = 0.005,
        chip_type: BkChipType = None,
        reset_mode: str = "dtr-rts",
        reset_hold: float = 0.1,
        **kwargs,
    ) -> None:
        if reset_mode not in ("dtr-rts", "rts", "none"):
            raise ValueError(f"Unsupported reset mode: {reset_mode}")
        if reset_hold < 0:
            raise ValueError("Reset hold time cannot be negative")

        if reset_mode in ("rts", "none"):
            # Keep both lines inactive before opening the port. This prevents
            # an unintended DTR pulse in RTS-only and no-reset modes.
            self.serial = Serial(
                port=None,
                baudrate=link_baudrate,
                timeout=cmnd_timeout,
            )
            self.serial.rts = False
            self.serial.dtr = False
            self.serial.port = port
            self.serial.open()
        else:
            self.serial = Serial(
                port=port,
                baudrate=link_baudrate,
                timeout=cmnd_timeout,
            )
        if hasattr(self.serial, "set_buffer_size"):
            # This method doesn't exist in pyserial POSIX implementation
            self.serial.set_buffer_size(rx_size=8192)
        self.baudrate = baudrate
        self.link_timeout = link_timeout
        self.cmnd_timeout = cmnd_timeout
        self.link_read_timeout = link_read_timeout
        self.chip_type_forced = chip_type
        self.reset_mode = reset_mode
        self.reset_hold = reset_hold
        if kwargs.get("debug_hl", False):
            self.debug = print
        if kwargs.get("debug_ll", False):
            self.verbose = print
