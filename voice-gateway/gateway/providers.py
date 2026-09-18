from typing import Protocol
import base64
import json
from urllib.parse import urlencode
from websockets.asyncio.client import connect
from .config import config


class AIProvider(Protocol):
    async def send_audio(self, audio: bytes): ...
    async def interrupt(self, item_id: str, played_ms: int): ...
    async def close(self): ...


class TelephonyProvider(Protocol):
    async def originate(self, number: str, call_id: str): ...
    async def hangup(self, call_id: str): ...
    async def dtmf(self, call_id: str, digits: str): ...


class OpenAIRealtime:
    def __init__(self):
        self.ws = None

    async def start(self, instructions, voice):
        cfg = config()
        if not cfg.openai_api_key:
            raise ValueError("OPENAI_API_KEY missing")
        self.ws = await connect(
            "wss://api.openai.com/v1/realtime?" + urlencode({"model": cfg.openai_realtime_model}),
            additional_headers={"Authorization": "Bearer " + cfg.openai_api_key},
            open_timeout=15,
            max_size=2**22,
        )
        await self.send(
            {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "instructions": instructions,
                    "output_modalities": ["audio"],
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcmu"},
                            "transcription": {"model": "gpt-4o-mini-transcribe", "language": "ru"},
                            "turn_detection": {
                                "type": "server_vad",
                                "interrupt_response": True,
                                "create_response": True,
                            },
                        },
                        "output": {"format": {"type": "audio/pcmu"}, "voice": voice},
                    },
                },
            }
        )

    async def send(self, event):
        await self.ws.send(json.dumps(event))

    async def send_audio(self, audio):
        await self.send(
            {"type": "input_audio_buffer.append", "audio": base64.b64encode(audio).decode()}
        )

    async def interrupt(self, item_id, played_ms):
        if item_id:
            await self.send(
                {
                    "type": "conversation.item.truncate",
                    "item_id": item_id,
                    "content_index": 0,
                    "audio_end_ms": played_ms,
                }
            )

    async def events(self):
        async for message in self.ws:
            yield json.loads(message)

    async def close(self):
        if self.ws:
            await self.ws.close()
