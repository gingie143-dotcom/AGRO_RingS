"""In-process backend/gateway integration. Real HTTP ASGI boundary, simulated telephony."""

import asyncio
import httpx
from app.domain import dispatch_one
from app.main import app
from gateway.main import run_session, SessionIn
from test_core import setup_campaign


def test_gateway_simulation_persists_transcript(client, db, monkeypatch):
    _, _ = setup_campaign(client)
    call = dispatch_one(db)
    db.commit()
    original = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.ASGITransport(app=app)
        return original(*args, **kwargs)

    monkeypatch.setattr("gateway.main.httpx.AsyncClient", client_factory)
    asyncio.run(run_session(SessionIn(call_id=call.id)))
    data = client.get("/api/calls/" + call.id).json()
    assert data["call"]["status"] == "completed"
    assert data["call"]["result"]["simulation"] is True
    assert len(data["messages"]) == 3
    assert [x["role"] for x in data["messages"]] == ["assistant", "user", "assistant"]
