# messages.py
# FULL IMPLEMENTATION OF SOMFY SDN MESSAGES
from somfy.protocol import Message
from somfy.helpers import *
import logging
logger = logging.getLogger("somfy_sdn")



# --- ACK / NACK ---
class Ack(Message):
    MSG = 0x7F
    PARAMS_LENGTH = 0

class Nack(Message):
    MSG = 0x6F
    PARAMS_LENGTH = 1
    ERROR_CODES = {
        0x01: "data_error",
        0x10: "unknown_message",
        0x20: "node_is_locked",
        0x21: "wrong_position",
        0x22: "limits_not_set",
        0x23: "ip_not_set",
        0x24: "out_of_range",
        0xFF: "busy"
    }

    def __init__(self, error_code=None, **kwargs):
        super().__init__(**kwargs)
        self.error_code = error_code

    def parse(self, params):
        super().parse(params)
        code = to_number(params)
        self.error_code = self.ERROR_CODES.get(code, f"unknown({code})")

    def params(self):
        code = [k for k, v in self.ERROR_CODES.items() if v == self.error_code]
        return transform_param([code[0] if code else 0x01])

# 01 --- MOVE (MOMENTARY) ---
class Move(Message):
    MSG = 0x01
    PARAMS_LENGTH = 3
    DIRECTION = {"down": 0x00, "up": 0x01, "cancel": 0x02}
    SPEED = {"up": 0x00, "down": 0x01, "slow": 0x02}

    def __init__(self, direction="cancel", duration=None, speed="up", **kwargs):
        super().__init__(**kwargs)
        self.direction = direction
        self.duration = duration
        self.speed = speed

    def parse(self, params):
        self.direction = invert_dict(self.DIRECTION).get(to_number(params[0:1]))
        self.duration = to_number(params[1:2]) or None
        self.speed = invert_dict(self.SPEED).get(to_number(params[2:3]))

    def params(self):
        dur = self.duration or 0
        return transform_param([self.DIRECTION[self.direction], dur, self.SPEED[self.speed]])



# 02 --- STOP --- 
class Stop(Message):
    MSG = 0x02
    PARAMS_LENGTH = 1
    def params(self):
        return transform_param([0])


class MoveTo(Message):
    MSG = 0x03
    PARAMS_LENGTH = 4  # 1 byte type, 2 bytes target, 1 byte reserved or speed

    TARGET_TYPE = {
        "down_limit": 0x00,
        "up_limit": 0x01,
        "ip": 0x02,
        "position_pulses": 0x03,
        "position_percent": 0x04
    }

    def __init__(self, target_type="ip", target=1, **kwargs):
        super().__init__(**kwargs)
        self.target_type = target_type
        self.target = target

    def params(self):
        try:
            type_byte = self.TARGET_TYPE.get(self.target_type)
            if type_byte is None:
                raise ValueError(f"Unknown target_type: {self.target_type}")

            target_bytes = from_number(self.target, 2)
            reserved = [0xFF]  # Add a dummy reserved byte for compatibility
            return transform_param([type_byte]) + target_bytes + reserved
        except Exception as e:
            logger.error(f"❌ MoveTo.params() error: {e}")
            return []

    def parse(self, params):
        try:
            if len(params) != 4:
                raise ValueError(f"Invalid param length: expected 4, got {len(params)}")

            raw_type = params[0:1]
            raw_target = params[1:3]

            inverted_type = to_number(raw_type)
            inverted_target = to_number(raw_target)

            self.target_type = {v: k for k, v in self.TARGET_TYPE.items()}.get(inverted_type)
            self.target = inverted_target

            if self.target_type is None:
                logger.warning(f"⚠️ MoveTo.parse(): Unknown target_type → raw={raw_type[0]:02X}, inverted={inverted_type}")

            if self.target_type is None:
                raw_hex = ''.join(f"{b:02X}" for b in params)
                logger.warning(f"⚠️ MoveTo.parse(): Params issue → full raw={raw_hex}")

        except Exception as e:
            logger.error(f"❌ MoveTo.parse() error: {e}")


# 04 --- MOVE OF (RELATIVE) ---
class MoveOf(Message):
    MSG = 0x04
    PARAMS_LENGTH = 4
    TARGET_TYPE = {
        "next_ip": 0x00, "previous_ip": 0x01,
        "jog_down_pulses": 0x02, "jog_up_pulses": 0x03,
        "jog_down_ms": 0x04, "jog_up_ms": 0x05
    }

    def __init__(self, target_type="next_ip", target=None, **kwargs):
        super().__init__(**kwargs)
        self.target_type = target_type
        self.target = target

    def parse(self, params):
        self.target_type = invert_dict(self.TARGET_TYPE).get(to_number(params[0:1]))
        target = to_number(params[1:3])
        if self.target_type in {"jog_down_ms", "jog_up_ms"}:
            target *= 10
        self.target = target

    def params(self):
        val = (self.target or 0xffff)
        if self.target_type in {"jog_down_ms", "jog_up_ms"}:
            val = val // 10
        return transform_param([self.TARGET_TYPE[self.target_type]]) + from_number(val, 2) + transform_param([0])


# 05 --- WINK ---
class Wink(Message):
    MSG = 0x05
    PARAMS_LENGTH = 0
    def params(self):
        return []


# 06 --- LOCK ---
class Lock(Message):
    MSG = 0x06
    PARAMS_LENGTH = 5
    TARGET_TYPE = {
        "current": 0, "up_limit": 1, "down_limit": 2,
        "ip": 4, "unlock": 5, "position_percent": 7
    }

    def __init__(self, target_type="unlock", target=None, priority=1, **kwargs):
        super().__init__(**kwargs)
        self.target_type = target_type
        self.target = target
        self.priority = priority

    def parse(self, params):
        self.target_type = invert_dict(self.TARGET_TYPE).get(to_number(params[0:1]))
        self.target = to_number(params[1:3])
        self.priority = to_number(params[3:4])

    def params(self):
        return transform_param([self.TARGET_TYPE[self.target_type]]) + from_number(self.target or 0xffff, 2) + transform_param([self.priority]) + transform_param([0])



#GETS-----------------------------------------------------------------------------------

# --- GET GROUP ADDR ---
class GetGroupAddr(Message):
    MSG = 0x41
    PARAMS_LENGTH = 1

    def __init__(self, group_index=1, **kwargs):
        super().__init__(**kwargs)
        self.group_index = group_index

    def parse(self, params):
        self.group_index = to_number(params[0:1]) + 1

    def params(self):
        return transform_param([self.group_index - 1])

# --- SIMPLE GET MESSAGES (NO PARAMS) ---
class GetMotorDirection(Message):
    MSG = 0x22
    PARAMS_LENGTH = 0

class GetMotorLimits(Message):
    MSG = 0x21
    PARAMS_LENGTH = 0

class GetMotorPosition(Message):
    MSG = 0x0C
    PARAMS_LENGTH = 0

class GetMotorRollingSpeed(Message):
    MSG = 0x23
    PARAMS_LENGTH = 0

class GetMotorStatus(Message):
    MSG = 0x0E
    PARAMS_LENGTH = 0

class GetNetworkLock(Message):
    MSG = 0x26
    PARAMS_LENGTH = 0

class GetNodeAppVersion(Message):
    MSG = 0x74
    PARAMS_LENGTH = 0

class GetNodeLabel(Message):
    MSG = 0x45
    PARAMS_LENGTH = 0

class GetNodeSerialNumber(Message):
    MSG = 0x4C
    PARAMS_LENGTH = 0

class GetNodeStackVersion(Message):
    MSG = 0x70
    PARAMS_LENGTH = 0

# --- GET MOTOR IP ---
class GetMotorIP(Message):
    MSG = 0x25
    PARAMS_LENGTH = 1

    def __init__(self, ip=1, **kwargs):
        super().__init__(**kwargs)
        self.ip = ip

    def parse(self, params):
        self.ip = to_number(params[0:1])

    def params(self):
        return transform_param([self.ip])

# --- GET NODE ADDR (wildcard default dest) ---
class GetNodeAddr(Message):
    MSG = 0x40
    PARAMS_LENGTH = 0

    def __init__(self, **kwargs):
        if 'dest' not in kwargs:
            kwargs['dest'] = [0xFF, 0xFF, 0xFF]
        super().__init__(**kwargs)
    
    def params(self):
        return []  # <-- ADD THIS LINE


# --- POST GROUP ADDRESS ---
class PostGroupAddr(Message):
    MSG = 0x61
    PARAMS_LENGTH = 4

    def __init__(self, group_index=None, group_address=None, **kwargs):
        super().__init__(**kwargs)
        self.group_index = group_index
        self.group_address = group_address

    def parse(self, params):
        self.group_index = to_number(params[0:1]) + 1
        self.group_address = transform_param(params[1:4])
        if self.group_address in ([0, 0, 0], [0x01, 0x01, 0xFF]):
            self.group_address = None

    def params(self):
        return from_number(self.group_index - 1) + transform_param(self.group_address or [0, 0, 0])

# --- POST MOTOR DIRECTION ---
class PostMotorDirection(Message):
    MSG = 0x32
    PARAMS_LENGTH = 1
    DIRECTION = {0x00: "standard", 0x01: "reversed"}

    def parse(self, params):
        self.direction = self.DIRECTION.get(to_number(params[0:1]))

# --- POST MOTOR IP ---
class PostMotorIP(Message):
    MSG = 0x35
    PARAMS_LENGTH = 4

    def __init__(self, ip=None, position_pulses=None, position_percent=None, **kwargs):
        super().__init__(**kwargs)
        self.ip = ip
        self.position_pulses = position_pulses
        self.position_percent = position_percent

    def parse(self, params):
        self.ip = to_number(params[0:1])
        self.position_pulses = to_number(params[1:3], nillable=True)
        self.position_percent = to_number(params[3:4], nillable=True)

    def params(self):
        return transform_param([self.ip]) + from_number(self.position_pulses, 2) + transform_param([self.position_percent or 0xFF])

# --- POST MOTOR LIMITS ---
class PostMotorLimits(Message):
    MSG = 0x31
    PARAMS_LENGTH = 4

    def __init__(self, up_limit=None, down_limit=None, **kwargs):
        super().__init__(**kwargs)
        self.up_limit = up_limit
        self.down_limit = down_limit

    def parse(self, params):
        self.up_limit = to_number(params[0:2], nillable=True)
        self.down_limit = to_number(params[2:4], nillable=True)

    def params(self):
        return from_number(self.up_limit, 2) + from_number(self.down_limit, 2)

# --- POST MOTOR POSITION ---
class PostMotorPosition(Message):
    MSG = 0x0D
    PARAMS_LENGTH = 5

    def __init__(self, position_pulses=None, position_percent=None, ip=None, **kwargs):
        super().__init__(**kwargs)
        self.position_pulses = position_pulses
        self.position_percent = position_percent
        self.ip = ip

    def parse(self, params):
        self.position_pulses = to_number(params[0:2], nillable=True)
        self.position_percent = to_number(params[2:3], nillable=True)
        self.ip = to_number(params[4:5], nillable=True)

    def params(self):
        return from_number(self.position_pulses, 2) + from_number(self.position_percent) + from_number(self.ip)

# --- POST MOTOR ROLLING SPEED ---
class PostMotorRollingSpeed(Message):
    MSG = 0x33
    PARAMS_LENGTH = 6

    def parse(self, params):
        self.up_speed = to_number(params[0:1])
        self.down_speed = to_number(params[1:2])
        self.slow_speed = to_number(params[2:3])
        # 3 trailing bytes ignored

# --- POST MOTOR STATUS ---
class PostMotorStatus(Message):
    MSG = 0x0F
    PARAMS_LENGTH = 4
    STATE = {0x00: "stopped", 0x01: "running", 0x02: "blocked", 0x03: "locked"}
    DIRECTION = {0x00: "down", 0x01: "up"}
    SOURCE = {0x00: "internal", 0x01: "network", 0x02: "dct"}
    CAUSE = {
        0x00: "target_reached", 0x01: "explicit_command", 0x02: "wink",
        0x10: "limits_not_set", 0x11: "ip_not_set", 0x12: "polarity_not_checked",
        0x13: "in_configuration_mode", 0x20: "obstacle_detection",
        0x21: "over_current_protection", 0x22: "thermal_protection"
    }

    def parse(self, params):
        self.state = self.STATE.get(to_number(params[0:1]))
        self.last_direction = self.DIRECTION.get(to_number(params[1:2]))
        self.last_action_source = self.SOURCE.get(to_number(params[2:3]))
        self.last_action_cause = self.CAUSE.get(to_number(params[3:4]))

# --- POST NETWORK LOCK (not parsed yet) ---
class PostNetworkLock(Message):
    MSG = 0x36
    PARAMS_LENGTH = 5
    # Parsing not implemented
    def parse(self, params):
        self.raw = params
        
# --- POST NODE ADDRESS ---
class PostNodeAddr(Message):
    MSG = 0x60
    PARAMS_LENGTH = 0

# --- POST NODE APP VERSION ---
class PostNodeAppVersion(Message):
    MSG = 0x75
    PARAMS_LENGTH = 6

    def parse(self, params):
        self.reference = to_number(params[0:3])
        self.index_letter = to_string(params[3:4])
        self.index_number = transform_param(params[4:5])[0]
        self.profile = transform_param(params[5:6])[0]

# --- POST NODE STACK VERSION ---
class PostNodeStackVersion(PostNodeAppVersion):
    MSG = 0x71

# --- POST NODE LABEL ---
class PostNodeLabel(Message):
    MSG = 0x65
    MAX_LENGTH = 16

    def __init__(self, label=None, **kwargs):
        super().__init__(**kwargs)
        self.label = label

    def parse(self, params):
        self.label = to_string(params)

    def params(self):
        return from_string(self.label, self.MAX_LENGTH)

# --- POST NODE SERIAL NUMBER ---
class PostNodeSerialNumber(Message):
    MSG = 0x6C

    def parse(self, params):
        self.serial_number = to_string(params)

# --- SET FACTORY DEFAULT ---
class SetFactoryDefault(Message):
    MSG = 0x1F
    PARAMS_LENGTH = 1
    RESET = {
        "all_settings": 0x00,
        "group_addresses": 0x01,
        "limits": 0x11,
        "rotation": 0x12,
        "rolling_speed": 0x13,
        "ips": 0x15,
        "locks": 0x17
    }

    def __init__(self, reset="all_settings", **kwargs):
        super().__init__(**kwargs)
        if reset not in self.RESET:
            logger.warning(f"⚠️ SetFactoryDefault.__init__: Invalid reset '{reset}', defaulting to 'all_settings'")
            reset = "all_settings"
        self.reset = reset


    def parse(self, params):
        self.reset = invert_dict(self.RESET).get(to_number(params))

    def params(self):
        code = self.RESET.get(self.reset)
        if code is None:
            logger.warning(f"⚠️ SetFactoryDefault: Unknown or missing reset value '{self.reset}', defaulting to 'all_settings'")
            code = self.RESET["all_settings"]
        return transform_param([code])
        
# --- SET GROUP ADDRESS ---
class SetGroupAddr(Message):
    MSG = 0x51
    PARAMS_LENGTH = 4

    def __init__(self, group_index=1, group_address=None, **kwargs):
        super().__init__(**kwargs)
        self.group_index = group_index
        self.group_address = group_address or [0, 0, 0]

    def parse(self, params):
        self.group_index = to_number(params[0:1]) + 1
        self.group_address = transform_param(params[1:4])

    def params(self):
        return transform_param([self.group_index - 1]) + transform_param(self.group_address)

# --- SET MOTOR DIRECTION ---
class SetMotorDirection(Message):
    MSG = 0x12
    PARAMS_LENGTH = 1
    DIRECTION = {"standard": 0x00, "reversed": 0x01}

    def __init__(self, direction="standard", **kwargs):
        super().__init__(**kwargs)
        self.direction = direction

    def parse(self, params):
        self.direction = invert_dict(self.DIRECTION).get(to_number(params))

    def params(self):
        return transform_param([self.DIRECTION[self.direction]])

# --- SET MOTOR IP ---
class SetMotorIP(Message):
    MSG = 0x15
    PARAMS_LENGTH = 4
    TYPE = {
        "delete": 0x00,
        "current_position": 0x01,
        "position_pulses": 0x02,
        "position_percent": 0x03,
        "distribute": 0x04
    }

    def __init__(self, type="delete", ip=None, value=None, **kwargs):
        super().__init__(**kwargs)
        self.type = type
        self.ip = ip
        self.value = value

    def parse(self, params):
        self.type = invert_dict(self.TYPE).get(to_number(params[0:1]))
        ip = to_number(params[1:2])
        self.ip = None if ip == 0 else ip
        self.value = to_number(params[2:4])

    def params(self):
        return transform_param([self.TYPE[self.type]]) + transform_param([self.ip or 0]) + from_number(self.value or 0, 2)

# --- SET MOTOR LIMITS ---
class SetMotorLimits(Message):
    MSG = 0x11
    PARAMS_LENGTH = 4
    TYPE = {
        "delete": 0x00,
        "current_position": 0x01,
        "specified_position": 0x02,
        "jog_ms": 0x04,
        "jog_pulses": 0x05
    }
    TARGET = {"down": 0x00, "up": 0x01}

    def __init__(self, type="delete", target="up", value=None, **kwargs):
        super().__init__(**kwargs)
        self.type = type
        self.target = target
        self.value = value

    def parse(self, params):
        self.type = invert_dict(self.TYPE).get(to_number(params[0:1]))
        self.target = invert_dict(self.TARGET).get(to_number(params[1:2]))
        self.value = to_number(params[2:4])

    def params(self):
        param = self.value or 0
        if self.type == "jog_ms":
            param //= 10
        return transform_param([self.TYPE[self.type], self.TARGET[self.target]]) + from_number(param, 2)

# --- SET MOTOR ROLLING SPEED ---
class SetMotorRollingSpeed(Message):
    MSG = 0x13
    PARAMS_LENGTH = 3

    def __init__(self, up_speed=None, down_speed=None, slow_speed=None, **kwargs):
        super().__init__(**kwargs)
        self.up_speed = up_speed
        self.down_speed = down_speed
        self.slow_speed = slow_speed

    def parse(self, params):
        self.up_speed = to_number(params[0:1])
        self.down_speed = to_number(params[1:2])
        self.slow_speed = to_number(params[2:3])

    def params(self):
        return transform_param([self.up_speed or 0xFF, self.down_speed or 0xFF, self.slow_speed or 0xFF])

# --- SET NETWORK LOCK ---
class SetNetworkLock(Message):
    MSG = 0x16
    PARAMS_LENGTH = 2

    def __init__(self, locked=False, priority=0, **kwargs):
        super().__init__(**kwargs)
        self.locked = locked
        self.priority = priority

    def parse(self, params):
        self.locked = to_number(params[0:1]) == 1
        self.priority = to_number(params[1:2])

    def params(self):
        return transform_param([1 if self.locked else 0, self.priority])

class SetNodeDiscovery(Message):
    MSG = 0x50
    PARAMS_LENGTH = 1
    DISCOVERY = {"startDiscovery": 0x00, "endDiscovery": 0x01}

    def __init__(self, discovery="startDiscovery", **kwargs):
        super().__init__(**kwargs)
        if discovery not in self.DISCOVERY:
            logger.warning(f"⚠️ SetNodeDiscovery.__init__: invalid '{discovery}', defaulting to 'startDiscovery'")
            discovery = "startDiscovery"
        self.discovery = discovery

    def parse(self, params):
        # params is 1 byte (obfuscated). to_number(params) returns the de-obfuscated value.
        self.discovery = invert_dict(self.DISCOVERY).get(to_number(params))

    def params(self):
        # Correctly map the current selection to its opcode
        code = self.DISCOVERY.get(self.discovery, self.DISCOVERY["startDiscovery"])
        return transform_param([code])



# --- SET NODE LABEL ---
class SetNodeLabel(Message):
    MSG = 0x55
    MAX_LENGTH = 16

    def __init__(self, label="", **kwargs):
        super().__init__(**kwargs)
        self.label = label

    def parse(self, params):
        self.label = to_string(params)

    def params(self):
        return from_string(self.label, self.MAX_LENGTH)

# --- ILT2 Set ----
# --- ILT2: SetMotorIP ---
class SetMotorIP_ILT2(Message):
    MSG = 0x53
    PARAMS_LENGTH = 3

    def __init__(self, dest=None, ip=1, value=None, **kwargs):
        kwargs.setdefault("dest", dest)
        super().__init__(**kwargs)
        self.ip = ip
        self.value = value

    def parse(self, params):
        self.ip = to_number(params[0:1]) + 1
        self.value = to_number(params[1:3], nillable=True)

    def params(self):
        if not (self.ip is None or 1 <= self.ip <= 16):
            raise ValueError("ip must be in range 1..16 or None")
        return transform_param(self.ip - 1) + from_number(self.value, 2)


# --- ILT2: SetMotorPosition ---
class SetMotorPosition(Message):
    MSG = 0x54
    PARAMS_LENGTH = 3
    TARGET_TYPE = {
        "up_limit": 1,
        "down_limit": 2,
        "stop": 3,
        "ip": 4,
        "next_ip_up": 5,
        "next_ip_down": 6,
        "position_pulses": 8,
        "jog_up_ms": 10,
        "jog_down_ms": 11,
        "jog_up_pulses": 12,
        "jog_down_pulses": 13,
        "position_percent": 16
    }

    def __init__(self, dest=None, target_type="up_limit", target=0, **kwargs):
        kwargs.setdefault("dest", dest)
        super().__init__(**kwargs)
        self.target_type = target_type
        self.target = target

    def parse(self, params):
        self.target_type = {v: k for k, v in self.TARGET_TYPE.items()}.get(to_number(params[0:1]))
        print(f"TARGET TYPE ={self.target_type}")
        val = to_number(params[1:3])
        if self.target_type == "position_percent":
            val = val * 100 / 255
        if self.target_type == "ip":
            val += 1
        self.target = val

    def params(self):
        val = self.target
        if self.target_type == "position_percent":
            val = int(val * 255 / 100)
        if self.target_type == "ip":
            val -= 1
        return transform_param([self.TARGET_TYPE[self.target_type]]) + from_number(val, 2)


# TODO: Add SetMotorSettings, GetMotorSettings, GetLockStatus
# TODO: Add ILT2 Post, and Get

# Use this template to easily register more:
# class YourMessageName(Message):
#     MSG = 0xXX
#     PARAMS_LENGTH = N
#     def parse(self, params): ...
#     def params(self): return [...]
