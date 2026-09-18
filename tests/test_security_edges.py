import pytest
from fastapi import HTTPException
from starlette.requests import Request
from redis.exceptions import ConnectionError
from app.main import login_limit, app


def test_login_has_no_accidental_query_parameter():
    parameters = app.openapi()["paths"]["/api/auth/login"]["post"].get("parameters", [])
    assert not any(p["name"] == "request" for p in parameters)


def test_login_rate_limit_fails_closed(monkeypatch):
    class Unavailable:
        def eval(self, *args):
            raise ConnectionError("offline")

    monkeypatch.setattr("app.main.Redis.from_url", lambda *a, **kw: Unavailable())
    req = Request({"type": "http", "client": ("127.0.0.1", 1), "headers": []})
    with pytest.raises(HTTPException) as exc:
        login_limit(req)
    assert exc.value.status_code == 503


def test_login_rate_limit_blocks_excess(monkeypatch):
    class Limit:
        def eval(self, *args):
            return 11

    monkeypatch.setattr("app.main.Redis.from_url", lambda *a, **kw: Limit())
    req = Request({"type": "http", "client": ("127.0.0.1", 1), "headers": []})
    with pytest.raises(HTTPException) as exc:
        login_limit(req)
    assert exc.value.status_code == 429
