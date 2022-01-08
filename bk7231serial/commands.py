from dataclasses import dataclass

@dataclass
class CommandType:
    code: int = 0x00
    response_code: int = 0x00
    is_long: bool = True
    has_response_code: bool = False


COMMAND_LINKCHECK = CommandType(code=0x00, response_code=0x01, has_response_code=True, is_long=False)
COMMAND_READCHIPINFO = CommandType(code=0x11, is_long=False)
COMMAND_READFLASH4K = CommandType(code=0x09, is_long=True)
COMMAND_REBOOT = CommandType(code=0x0E, is_long=False)
COMMAND_FLASHCRC = CommandType(code=0x10, is_long=False)
COMMAND_SETBAUDRATE = CommandType(code=0x0F, is_long=False)