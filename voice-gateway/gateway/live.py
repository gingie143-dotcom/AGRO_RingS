import asyncio
import base64
import contextlib
import json
import socket
from urllib.parse import urlencode
from websockets.asyncio.client import connect
from .config import config
from .ari import AsteriskARI
from .providers import OpenAIRealtime
from .media import RTPReceiver, Playback


async def live_session(data, emit):
    cfg = config()
    ari = AsteriskARI()
    ai = OpenAIRealtime()
    receiver = RTPReceiver()
    playback = Playback()
    bridge = "bridge-" + str(data.call_id)
    media = "media-" + str(data.call_id)
    channel = str(data.call_id)
    tasks = []
    transport = None
    ended = asyncio.Event()
    answered = False
    try:
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: receiver, local_addr=("0.0.0.0", 0)
        )
        port = transport.get_extra_info("sockname")[1]
        url = (
            cfg.ari_url.replace("http://", "ws://").replace("https://", "wss://")
            + "/events?"
            + urlencode({"app": "ai-caller", "api_key": cfg.ari_username + ":" + cfg.ari_password})
        )
        async with connect(url, open_timeout=10) as events:
            await ari.originate(data.number, channel)
            await emit("ringing", event_id="ringing")

            async def read_ari():
                nonlocal answered
                async for raw in events:
                    event = json.loads(raw)
                    if event.get("channel", {}).get("id") != channel:
                        continue
                    if event["type"] == "StasisStart" and not answered:
                        answered = True
                        await emit("answered", event_id="answered")
                        await ari.request("POST", "bridges", type="mixing", bridgeId=bridge)
                        await ari.request("POST", f"bridges/{bridge}/addChannel", channel=channel)
                        await ari.request(
                            "POST",
                            "channels/externalMedia",
                            channelId=media,
                            app="ai-caller",
                            external_host=f"{cfg.media_host}:{port}",
                            format="ulaw",
                            transport="udp",
                            encapsulation="rtp",
                            direction="both",
                        )
                        addr = await ari.request(
                            "GET", f"channels/{media}/variable", variable="UNICASTRTP_LOCAL_ADDRESS"
                        )
                        media_port = await ari.request(
                            "GET", f"channels/{media}/variable", variable="UNICASTRTP_LOCAL_PORT"
                        )
                        resolved = socket.gethostbyname(addr["value"])
                        receiver.expected_peer = (resolved, int(media_port["value"]))
                        await ari.request("POST", f"bridges/{bridge}/addChannel", channel=media)
                        await ai.start(data.instructions, data.voice)
                        tasks.extend(
                            [
                                asyncio.create_task(send_input()),
                                asyncio.create_task(read_ai()),
                                asyncio.create_task(play_audio()),
                            ]
                        )
                    if event["type"] in ("StasisEnd", "ChannelDestroyed"):
                        ended.set()
                        return
                raise ConnectionError("ARI event stream ended")

            async def send_input():
                while True:
                    await ai.send_audio(await receiver.audio.get())

            async def play_audio():
                while True:
                    if receiver.expected_peer:
                        packet = playback.packet()
                        if packet:
                            transport.sendto(packet, receiver.expected_peer)
                    await asyncio.sleep(0.02)

            async def read_ai():
                async for event in ai.events():
                    kind = event["type"]
                    if kind == "session.updated":
                        await ai.send({"type": "response.create"})
                    elif kind == "response.output_audio.delta":
                        playback.append(event["item_id"], base64.b64decode(event["delta"]))
                    elif kind == "response.output_audio.done":
                        playback.finish()
                    elif kind == "input_audio_buffer.speech_started":
                        item, played_ms = playback.interrupt()
                        await ai.interrupt(item, played_ms)
                    elif kind in (
                        "conversation.item.input_audio_transcription.completed",
                        "response.output_audio_transcript.done",
                    ):
                        await emit(
                            "transcript",
                            event_id=event["event_id"],
                            role="user" if kind.startswith("conversation") else "assistant",
                            text=event.get("transcript", ""),
                        )
                    elif kind == "error":
                        raise RuntimeError("AI provider error")
                raise ConnectionError("AI stream ended")

            tasks.append(asyncio.create_task(read_ari()))
            async with asyncio.timeout(cfg.max_call_seconds):
                while not ended.is_set():
                    for task in tasks:
                        if task.done():
                            task.result()
                    await asyncio.sleep(0.05)
            await emit(
                "completed" if answered else "failed",
                event_id="end",
                reason="hangup" if answered else "no_answer",
                result={
                    "simulation": False,
                    "analysis_status": "not_implemented",
                    "rtp_input_dropped": receiver.dropped,
                },
            )
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for path in ["channels/" + channel, "channels/" + media, "bridges/" + bridge]:
            with contextlib.suppress(Exception):
                await ari.request("DELETE", path)
        await ai.close()
        await ari.close()
        if transport:
            transport.close()
