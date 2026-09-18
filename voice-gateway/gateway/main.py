import asyncio
import contextlib
import hmac
import logging
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID
import httpx
from fastapi import FastAPI, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from .config import config
from .live import live_session
from .analysis import OpenAIAnalysis

log = logging.getLogger("gateway")
tasks = set()
session_lock = asyncio.Lock()


class SessionIn(BaseModel):
    call_id: UUID
    mode: Literal["simulation", "live"] = "simulation"
    instructions: str = Field(default="", max_length=20000)
    voice: str = "marin"
    number: str = ""


async def auth(request: Request):
    if not hmac.compare_digest(
        request.headers.get("authorization", ""), "Bearer " + config().service_token
    ):
        raise HTTPException(401, "Unauthorized")


@asynccontextmanager
async def lifespan(app):
    yield
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="Voice Gateway", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "active_sessions": len(tasks)}


async def run_session(data):
    transcript = []
    transcript_event_ids = set()
    cfg = config()
    async with httpx.AsyncClient(
        base_url=cfg.backend_url,
        headers={"Authorization": "Bearer " + cfg.service_token},
        timeout=10,
    ) as client:

        async def emit(kind, event_id, **fields):
            if kind == "transcript" and event_id not in transcript_event_ids:
                transcript.append({"role": fields.get("role"), "text": fields.get("text", "")})
                transcript_event_ids.add(event_id)
            if kind in ("completed", "transferred") and data.mode == "live":
                try:
                    analysis = await OpenAIAnalysis().analyze(transcript)
                except Exception:
                    analysis = {"analysis_status": "failed"}
                fields["result"] = {**fields.get("result", {}), **analysis}
            # Retrying a persisted event id is safe; redialing is not.
            for attempt in range(3):
                try:
                    result = await client.post(
                        f"/internal/calls/{data.call_id}/events",
                        json={"kind": kind, "event_id": event_id, **fields},
                    )
                    result.raise_for_status()
                    return
                except httpx.HTTPError:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.3 * (attempt + 1))

        try:
            if data.mode == "live":
                await live_session(data, emit)
            else:
                await emit("ringing", "ringing")
                await asyncio.sleep(0.2)
                await emit("answered", "answered")
                for i, (role, text) in enumerate(
                    [
                        ("assistant", "Это симуляция звонка для проверки системы."),
                        ("user", "Тестовая реплика, не запись реального человека."),
                        ("assistant", "Проверка завершена. История будет сохранена."),
                    ]
                ):
                    await emit("transcript", f"message-{i}", role=role, text=text)
                    await asyncio.sleep(0.2)
                await emit(
                    "completed",
                    "completed",
                    reason="simulation_finished",
                    result={
                        "simulation": True,
                        "conversation_summary": "Техническая симуляция. AI и SIP не использовались.",
                        "analysis_status": "simulation",
                    },
                )
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await emit("failed", "shutdown", reason="gateway_shutdown")
            raise
        except Exception as exc:
            log.error("session_failed call_id=%s type=%s", data.call_id, type(exc).__name__)
            with contextlib.suppress(Exception):
                await emit("failed", "error", reason="gateway_error")


@app.post("/sessions", status_code=202, dependencies=[Depends(auth)])
async def create_session(data: SessionIn):
    async with session_lock:
        return await claim_session(data)


async def claim_session(data: SessionIn):
    cfg = config()
    if data.mode == "live" and (
        not cfg.live_calls_enabled
        or not cfg.live_test_number
        or data.number != cfg.live_test_number
    ):
        raise HTTPException(409, "Only explicitly configured single test number is permitted")
    if len(tasks) >= cfg.max_concurrent_calls:
        raise HTTPException(429, "Concurrency limit")
    try:
        async with Redis.from_url(
            cfg.redis_url, socket_connect_timeout=2, socket_timeout=2
        ) as redis:
            claimed = await redis.set("voice:once:" + str(data.call_id), "1", nx=True, ex=86400)
    except Exception:
        raise HTTPException(503, "Idempotency store unavailable")
    if not claimed:
        return {"accepted": False, "reason": "already_seen"}
    task = asyncio.create_task(run_session(data))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return {"accepted": True, "call_id": str(data.call_id)}
