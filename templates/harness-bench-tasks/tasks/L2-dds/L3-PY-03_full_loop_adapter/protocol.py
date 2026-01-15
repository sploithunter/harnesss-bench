#!/usr/bin/env python3
"""Simple Binary Protocol Definition.

Protocol format:
- 4 bytes: message length (big-endian uint32)
- N bytes: JSON payload

Message types:
- Heartbeat: {"type": "heartbeat", "seq": int, "timestamp": float}
- Position: {"type": "position", "id": int, "x": float, "y": float, "z": float}
- Command: {"type": "command", "id": int, "action": str, "params": dict}
"""

import json
import struct
import time
from dataclasses import dataclass
from typing import Union


@dataclass
class Heartbeat:
    seq: int
    timestamp: float
    
    def to_dict(self) -> dict:
        return {"type": "heartbeat", "seq": self.seq, "timestamp": self.timestamp}
    
    @classmethod
    def from_dict(cls, d: dict) -> "Heartbeat":
        return cls(seq=d["seq"], timestamp=d["timestamp"])


@dataclass
class Position:
    id: int
    x: float
    y: float
    z: float
    
    def to_dict(self) -> dict:
        return {"type": "position", "id": self.id, "x": self.x, "y": self.y, "z": self.z}
    
    @classmethod
    def from_dict(cls, d: dict) -> "Position":
        return cls(id=d["id"], x=d["x"], y=d["y"], z=d["z"])


@dataclass
class Command:
    id: int
    action: str
    params: dict
    
    def to_dict(self) -> dict:
        return {"type": "command", "id": self.id, "action": self.action, "params": self.params}
    
    @classmethod
    def from_dict(cls, d: dict) -> "Command":
        return cls(id=d["id"], action=d["action"], params=d.get("params", {}))


Message = Union[Heartbeat, Position, Command]


def encode_message(msg: Message) -> bytes:
    """Encode a message to binary format."""
    payload = json.dumps(msg.to_dict()).encode("utf-8")
    length = struct.pack(">I", len(payload))
    return length + payload


def decode_message(data: bytes) -> tuple[Message, bytes]:
    """Decode a message from binary format.
    
    Returns: (message, remaining_data)
    """
    if len(data) < 4:
        raise ValueError("Incomplete message: need at least 4 bytes for length")
    
    length = struct.unpack(">I", data[:4])[0]
    
    if len(data) < 4 + length:
        raise ValueError(f"Incomplete message: need {4 + length} bytes, have {len(data)}")
    
    payload = data[4:4 + length]
    remaining = data[4 + length:]
    
    d = json.loads(payload.decode("utf-8"))
    msg_type = d.get("type")
    
    if msg_type == "heartbeat":
        return Heartbeat.from_dict(d), remaining
    elif msg_type == "position":
        return Position.from_dict(d), remaining
    elif msg_type == "command":
        return Command.from_dict(d), remaining
    else:
        raise ValueError(f"Unknown message type: {msg_type}")


def generate_test_messages(count: int = 10) -> list[Message]:
    """Generate a sequence of test messages."""
    messages = []
    
    for i in range(count):
        seq = i + 1
        
        # Every 3rd is heartbeat, every 3rd+1 is position, every 3rd+2 is command
        if i % 3 == 0:
            messages.append(Heartbeat(seq=seq, timestamp=time.time()))
        elif i % 3 == 1:
            messages.append(Position(id=seq, x=float(i), y=float(i * 2), z=100.0))
        else:
            messages.append(Command(id=seq, action="move", params={"speed": i * 0.5}))
    
    return messages


