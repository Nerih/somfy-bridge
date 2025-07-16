import logging
from somfy.helpers import *

logger = logging.getLogger("somfy_sdn")

class MalformedMessage(Exception):
    pass

class MessageMeta(type):
    registry = {}

    def __new__(cls, name, bases, attrs):
        new_class = super().__new__(cls, name, bases, attrs)
        msg = attrs.get("MSG")
        if msg is not None:
            MessageMeta.registry[msg] = new_class
        return new_class

class Message(metaclass=MessageMeta):
    MSG = None
    PARAMS_LENGTH = None

    def __init__(self, node_type=0, src_node_type=0, des_node_type=0, ack_requested=False, src=None, dest=None):
        self.node_type = node_type
        self.src_node_type = src_node_type
        self.des_node_type = des_node_type
        self.ack_requested = ack_requested
        self.src = src or [0, 0, 1]
        self.dest = dest or [0, 0, 0]

    @property
    def node_type_str(self) -> str:
        if self.src and len(self.src) > 0:
            return node_type_from_number(self.src[0])
        return "unknown"

    @property
    def src_node_type_str(self) -> str:
        return node_type_from_number(getattr(self, 'src_node_type', 0))

    @property
    def des_node_type_str(self) -> str:
        return node_type_from_number(getattr(self, 'des_node_type', 0))

    def __str__(self):
        msg_type = f"0x{self.MSG:02X}" if self.MSG is not None else "unknown"
        src = print_address(self.src)
        dest = print_address(self.dest)
        params_str = " ".join(f"{b:02X}" for b in self.params()) or "none"
        raw_bytes = "".join(f"{b:02X}" for b in self.to_bytes())

        return (
            f"<||{self.__class__.__name__}|| "
            f"FROM:[{src}]/{self.src_node_type_str} → "
            f"TO:[{dest}]/{self.des_node_type_str} | "
            f"ackn={self.ack_requested} | "
            f"prms={params_str}>"
            # f"\n 🧾 Bytes: {raw_bytes}"  # optional: uncomment for full byte log
        )

    def parse(self, params):
        if self.PARAMS_LENGTH is not None and len(params) != self.PARAMS_LENGTH:
            raise MalformedMessage(f"Unexpected params for {type(self).__name__}: {params}")

    def params(self):
        return []

    def to_bytes(self):
        # Recombine node type byte from split fields
        node_type_byte = (self.src_node_type << 4) | (self.des_node_type & 0x0F)

        payload = transform_param([node_type_byte]) + transform_param(self.src) + transform_param(self.dest) +  self.params()
        length = len(payload) + 4
        if self.ack_requested:
            length |= 0x80
        result = transform_param([self.MSG]) + transform_param([length]) + payload
        result += checksum(result)
        return bytes(result)

    def __eq__(self, other):
        return self.to_bytes() == other.to_bytes()

    def __repr__(self):
        msg_type = getattr(self, 'MSG', None)
        msg_name = self.__class__.__name__
        src = print_address(self.src)
        dest = print_address(self.dest)
        ack = self.ack_requested
        try:
            params_hex = [f"{b:02X}" for b in self.params()]
        except Exception:
            params_hex = ["?"]
        parts = [
            f"{msg_name}",
            f"msg=0x{msg_type:02X}" if msg_type is not None else "",
            f"src={src}",
            f"dest={dest}",
            f"ack={ack}",
            f"params={params_hex}"
        ]
        return "<" + " ".join(p for p in parts if p) + ">"


    @classmethod
    def expected_response(cls, message):
        if cls.__name__.startswith("Get"):
            return message.__class__.__name__ == cls.__name__.replace("Get", "Post")
        return isinstance(message, (Ack, Nack))

    @classmethod
    def parse_from_bytes(cls, data):
        offset = -1
        while True:
            offset += 1
            if len(data) - offset < 11:
                return None, 0

            msg = to_number([data[offset]])
            length = to_number([data[offset + 1]])
            ack_requested = (length & 0x80) == 0x80
            length &= 0x7F

            if length < 11 or length > 43:
                continue
            if length > len(data) - offset:
                continue

            expected_checksum = checksum(data[offset:offset + length - 2])
            read_checksum = data[offset + length - 2:offset + length]
            if expected_checksum != list(read_checksum):
                continue

            msg_cls = MessageMeta.registry.get(msg, UnknownMessage)
            node_type = node_type_from_number(to_number([data[offset + 2]]))
            
            # Correct node type decoding
            node_type_byte = to_number([data[offset + 2]])
            src_node_type = (node_type_byte >> 4) & 0x0F
            des_node_type = node_type_byte & 0x0F

            src = transform_param(data[offset + 3:offset + 6])
            dest = transform_param(data[offset + 6:offset + 9])
            body = data[offset + 9:offset + length - 2]

            try:
                msg_instance = msg_cls(node_type=node_type,src_node_type=src_node_type, des_node_type=des_node_type, ack_requested=ack_requested, src=src, dest=dest)

                # Attach correct node type details
                msg_instance.node_type_byte = node_type_byte

                raw_hex = ''.join(f"{b:02X}" for b in data[offset:offset+length])
                logger.debug(f"🔍 Parsing raw SDN message: {raw_hex}")


                msg_instance.parse(body)
                if isinstance(msg_instance, UnknownMessage):
                    msg_instance.msg = msg
                return msg_instance, offset + length
            except Exception as e:
                logger.warning(f"Invalid message {msg_cls.__name__}: {e}")
                return None, offset + length

class UnknownMessage(Message):
    def __init__(self, params=None, **kwargs):
        super().__init__(**kwargs)
        self.params_ = params or []
        self.msg = None

    def parse(self, params):
        self.params_ = list(params)

    def params(self):
        return self.params_

    def to_bytes(self):
        if self.params_ is None:
            raise NotImplementedError("Cannot serialize unknown message without params")
        return super().to_bytes()

    def __repr__(self):
        base = super().__repr__()
        msg_hex = f"0x{self.msg:02X}" if hasattr(self, "msg") and self.msg is not None else "unknown"
        params_hex = [f"0x{p:02X}" for p in self.params_]
        return f"{base} msg={msg_hex} params={params_hex}"

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

# Ensure somfy_sdn uses root handler formatting
if not logger.hasHandlers():
    logger.propagate = True