"""G.711 mu-law RTP framing and bounded, paced playback with interruption."""

import asyncio
import secrets
import struct
from collections import deque


def decode_rtp(packet):
    if len(packet) < 12 or packet[0] >> 6 != 2 or packet[1] & 0x7F != 0:
        raise ValueError("Expected RTP v2 PCMU")
    offset = 12 + 4 * (packet[0] & 0x0F)
    if len(packet) < offset:
        raise ValueError("Truncated CSRC list")
    if packet[0] & 0x10:
        if len(packet) < offset + 4:
            raise ValueError("Truncated RTP extension")
        words = struct.unpack("!H", packet[offset + 2 : offset + 4])[0]
        offset += 4 + words * 4
    end = len(packet)
    if packet[0] & 0x20:
        padding = packet[-1]
        if padding == 0 or padding > end - offset:
            raise ValueError("Invalid RTP padding")
        end -= padding
    if offset > end:
        raise ValueError("Truncated RTP payload")
    return packet[offset:end]


class Playback:
    def __init__(self):
        self.frames = deque()
        self.remainder = b""
        self.item_id = None
        self.played_bytes = 0
        self.blocked_items = set()
        self.sequence = secrets.randbelow(65536)
        self.timestamp = secrets.randbelow(2**32)
        self.ssrc = secrets.randbelow(2**32)

    def append(self, item_id, audio):
        if item_id in self.blocked_items:
            return
        if self.item_id != item_id:
            if self.frames or self.remainder:
                raise ValueError("Overlapping audio items")
            self.item_id = item_id
            self.played_bytes = 0
        self.remainder += audio
        while len(self.remainder) >= 160:
            if len(self.frames) >= 1500:  # at most 30 seconds; fail instead of unbounded buffering
                raise ValueError("Audio buffer overflow")
            self.frames.append(self.remainder[:160])
            self.remainder = self.remainder[160:]

    def finish(self):
        if self.remainder:
            self.frames.append(self.remainder.ljust(160, b"\xff"))
            self.remainder = b""

    def interrupt(self):
        item = self.item_id
        elapsed = self.played_bytes // 8
        if item:
            self.blocked_items.add(item)
        self.frames.clear()
        self.remainder = b""
        return item, elapsed

    def packet(self):
        if not self.frames:
            return None
        payload = self.frames.popleft()
        result = struct.pack("!BBHII", 0x80, 0, self.sequence, self.timestamp, self.ssrc) + payload
        self.sequence = (self.sequence + 1) % 65536
        self.timestamp = (self.timestamp + 160) % (2**32)
        self.played_bytes += len(payload)
        return result


class RTPReceiver(asyncio.DatagramProtocol):
    def __init__(self):
        self.audio = asyncio.Queue(maxsize=500)
        self.peer = None
        self.expected_peer = None
        self.transport = None
        self.dropped = 0

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if self.expected_peer is None or addr != self.expected_peer:
            return
        try:
            payload = decode_rtp(data)
        except ValueError:
            return
        self.peer = addr
        if self.audio.full():
            self.audio.get_nowait()
            self.dropped += 1
        self.audio.put_nowait(payload)
