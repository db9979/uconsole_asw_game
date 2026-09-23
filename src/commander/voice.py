"""Bounded wire format for transient Remote Crew voice WebSockets."""

from collections import deque


PCM_BYTES = 1920  # 20 ms, 48 kHz mono signed 16-bit little-endian.
MAX_FRAME_BYTES = 2048


class VoicePeer:
    def __init__(self, digest, session, station, lease_generation, active_generation):
        self.digest = digest
        self.session = session
        self.station = station
        self.lease_generation = lease_generation
        self.active_generation = active_generation
        self.incoming = bytearray()
        self.outgoing = deque(maxlen=8)

    def enqueue(self, opcode, payload):
        self.outgoing.append((opcode, payload))


def read_frames(buffer):
    """Consume complete, masked, unfragmented browser frames from a bytearray."""
    while len(buffer) >= 2:
        first, second = buffer[:2]
        opcode = first & 15
        if first & 0xF0 != 0x80 or not second & 0x80 or opcode not in (1, 2, 8, 9, 10):
            raise ValueError("invalid voice frame")
        length = second & 127
        header = 2
        if length == 126:
            if len(buffer) < 4:
                return
            length = int.from_bytes(buffer[2:4], "big")
            header = 4
        elif length == 127:
            raise ValueError("oversized voice frame")
        if length > MAX_FRAME_BYTES or (opcode >= 8 and length > 125):
            raise ValueError("oversized voice frame")
        if len(buffer) < header + 4 + length:
            return
        mask = buffer[header:header + 4]
        payload = bytes(value ^ mask[index % 4] for index, value in
                        enumerate(buffer[header + 4:header + 4 + length]))
        del buffer[:header + 4 + length]
        yield opcode, payload
