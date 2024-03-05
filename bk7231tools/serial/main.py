#  Copyright (c) Kuba Szczodrzyński 2024-3-5.

from serial import Serial

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
        **kwargs,
    ) -> None:
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
        if kwargs.get("debug_hl", False):
            self.debug = print
        if kwargs.get("debug_ll", False):
            self.verbose = print
