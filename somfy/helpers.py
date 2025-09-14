import logging
from typing import List
logger = logging.getLogger("somfy_sdn")

def parse_address(addr_string):
    try:
        if "." in addr_string or ":" in addr_string:
            parts = addr_string.replace(".", ":").split(":")
        else:
            if len(addr_string) != 6:
                raise ValueError("Flat address string must be exactly 6 hex characters")
            parts = [addr_string[i:i+2] for i in range(0, 6, 2)]
        return [int(p, 16) for p in parts]
    except Exception:
        logger.exception(f"❌ parse_address failed for input: {addr_string}")
        return [0, 0, 0]

def print_address(addr_bytes):
    try:
        return f"{addr_bytes[0]:02X}{addr_bytes[1]:02X}{addr_bytes[2]:02X}"
    except Exception:
        logger.exception(f"❌ print_address failed for: {addr_bytes}")
        return "000000"

def group_address(addr_bytes):
    try:
        return addr_bytes[0:2] == [1, 1]
    except Exception:
        logger.exception(f"❌ group_address failed for: {addr_bytes}")
        return False

def transform_param(param, length=None, pad=0x00):
    try:
        if param is None or any(b is None for b in param):
            logger.warning(f"⚠️ transform_param: received invalid param {param}, padding with 0x{pad:02X} (len={length})")
            if length:
                return [pad] * length
            return []
        return [0xFF - b for b in reversed(param)]
    except Exception:
        logger.exception(f"❌ transform_param failed for param={param}")
        return [pad] * (length or 1)

def to_number(param, nillable=False):
    try:
        param = list(param)
        val = 0
        for b in reversed(param):
            val = (val << 8) + (0xFF - b)
        if nillable and val == (1 << (8 * len(param))) - 1:
            return None
        return val
    except Exception:
        logger.exception(f"❌ to_number failed for param={param}")
        return None if nillable else 0

def from_number(number, length=1):
    try:
        number = (1 << (8 * length)) - 1 if number is None else int(number)
        result = []
        for _ in range(length):
            result.append(0xFF - (number & 0xFF))
            number >>= 8
        return result
    except Exception:
        logger.exception(f"❌ from_number failed for number={number}, length={length}")
        return [0x00] * length

def to_string(param):
    try:
        chars = [chr(0xFF - b) for b in param]
        return ''.join(chars).rstrip('\x00').strip()
    except Exception:
        logger.exception(f"❌ to_string failed for param={param}")
        return ""

def from_string(string, length):
    try:
        chars = list(string.encode())[:length]
        chars += [ord(' ')] * (length - len(chars))
        return [0xFF - b for b in chars]
    except Exception:
        logger.exception(f"❌ from_string failed for string='{string}', length={length}")
        return [0x00] * length

def checksum(bytes_):
    try:
        result = sum(bytes_)
        return [result >> 8, result & 0xFF]
    except Exception:
        logger.exception(f"❌ checksum failed for: {bytes_}")
        return [0x00, 0x00]

def invert_dict(d):
    try:
        return {v: k for k, v in d.items()}
    except Exception:
        logger.exception("❌ invert_dict failed")
        return {}

NODE_TYPE_MAP = {
    0: "All Devices",
    1: "RS485 4ILT Interface",
    2: "ST30 RS485",
    5: "RTS_BRIDGE",
    6: "GLYDEA",
    7: "ST50AC",
    8: "ST50DC",
    9: "ST40AC",
    15: "Bridge/Tool",
    240: "All Devices",
    111: "Bridge/Tool",
    127: "Bridge/Tool",
    255: "Bridge/Tool",
    247: "LSU50AC",
    246: "GLYDEA"
}

def node_type_from_number(number):
    try:
        return NODE_TYPE_MAP.get(number, f"unknown_{number}")
    except Exception:
        logger.exception(f"❌ node_type_from_number failed for number={number}")
        return "unknown"

def node_type_to_number(type_input):
    try:
        if isinstance(type_input, int):
            return type_input
        if isinstance(type_input, str):
            if type_input.startswith("unknown_"):
                try:
                    return int(type_input.split("_")[1])
                except:
                    return 0x00
            inverted = invert_dict(NODE_TYPE_MAP)
            return inverted.get(type_input, 0x00)
    except Exception:
        logger.exception(f"❌ node_type_to_number failed for input={type_input}")
    return 0x00


# Add this helper (e.g., near the Bridge class)
def is_unicast_non_group(dest: List[int]) -> bool:
    """
    Return True if dest is a true unicast (not group/broadcast).
    
    Rules:
      • Group addresses are in 0x0_0001 – 0x0_FFFF (leading nibble 0x0).
      • Broadcast/group patterns like FF FF F* are excluded.
      • Unicast = anything else in 0x100000 – 0xFFFFFE.
    """
    if not dest or len(dest) < 3:
        return False

    # Reject broadcast / group patterns like FF FF F*
    if dest[0] == 0xFF and dest[1] == 0xFF:
        return False

    addr = (dest[0] << 16) | (dest[1] << 8) | dest[2]

    # Group = 0x000001–0x0FFFFF
    if 0x000001 <= addr <= 0x0FFFFF:
        return False

    # Everything else (up to 0xFFFFFF) is unicast
    return 0x000001 <= addr <= 0xFFFFFF
