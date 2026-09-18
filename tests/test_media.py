import struct
import pytest
from gateway.media import Playback, decode_rtp, RTPReceiver


def test_barge_in_discards_queued_and_late_audio():
    output = Playback()
    output.append("old", b"\x7f" * 480)
    assert len(decode_rtp(output.packet())) == 160
    assert output.interrupt() == ("old", 20)
    assert output.packet() is None
    output.append("old", b"\x7f" * 160)
    assert output.packet() is None
    output.append("new", b"\x00" * 160)
    assert decode_rtp(output.packet()) == b"\x00" * 160


def test_rtp_extensions_and_padding():
    packet = (
        struct.pack("!BBHII", 0xB1, 0, 1, 2, 3)
        + b"\x00" * 4
        + struct.pack("!HH", 1, 1)
        + b"\x00" * 4
        + b"abc"
        + b"\x00\x02"
    )
    assert decode_rtp(packet) == b"abc"
    for invalid in [b"", b"\x80" * 3, b"\x00" * 12, b"\x90" + b"\x00" * 11]:
        with pytest.raises(ValueError):
            decode_rtp(invalid)


def test_receiver_rejects_unknown_source():
    r = RTPReceiver()
    p = Playback()
    p.append("one", b"\x7f" * 160)
    packet = p.packet()
    r.expected_peer = ("127.0.0.1", 10000)
    r.datagram_received(packet, ("127.0.0.1", 10001))
    assert r.audio.empty()
    r.datagram_received(packet, ("127.0.0.1", 10000))
    assert r.audio.qsize() == 1


def test_queue_is_bounded():
    p = Playback()
    with pytest.raises(ValueError, match="overflow"):
        p.append("huge", b"\x7f" * (160 * 1501))
