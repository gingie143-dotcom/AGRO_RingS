from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app import models as m
from app.main import app
from app.domain import dispatch_one, apply_event, in_schedule, eligible
from app.schemas import EventIn
from app.imports import parse_contacts


def create(client, path, data):
    response = client.post("/api/" + path, json=data)
    assert response.status_code == 201, response.text
    return response.json()


def setup_campaign(client):
    contact = create(
        client,
        "contacts",
        {"name": "Тест", "phone": "+79990000001", "consent_basis": "Тестовое согласие"},
    )
    scenario = create(client, "scenarios", {"name": "Проверка", "goal": "Проверить диалог"})
    agent = create(client, "agents", {"name": "Агент"})
    campaign = create(
        client,
        "campaigns",
        {
            "name": "Тест",
            "scenario_id": scenario["id"],
            "agent_id": agent["id"],
            "start_hour": 0,
            "end_hour": 24,
            "weekdays": list(range(7)),
        },
    )
    assert (
        client.post(
            "/api/campaigns/" + campaign["id"] + "/contacts", json={"contact_ids": [contact["id"]]}
        ).status_code
        == 200
    )
    assert client.post("/api/campaigns/" + campaign["id"] + "/start").status_code == 200
    return contact, campaign


def test_auth_and_csrf(client):
    assert TestClient(app).get("/api/contacts").status_code == 401
    assert (
        client.post(
            "/api/contacts",
            headers={"x-csrf-token": "wrong"},
            json={"name": "A", "phone": "+79990000000"},
        ).status_code
        == 403
    )
    assert (
        client.post("/api/auth/logout", headers={"origin": "https://evil.example"}).status_code
        == 403
    )


def test_viewer_cannot_mutate(client):
    create(client, "users", {"username": "read", "password": "long-password-123", "role": "viewer"})
    r = client.post("/api/auth/login", json={"username": "read", "password": "long-password-123"})
    assert r.status_code == 200
    client.headers["x-csrf-token"] = client.cookies["csrf"]
    assert client.get("/api/contacts").status_code == 200
    assert client.post("/api/companies", json={"name": "No"}).status_code == 403
    assert client.get("/api/settings").status_code == 403


def test_call_lifecycle_idempotent_and_terminal(client, db):
    contact, campaign = setup_campaign(client)
    call = dispatch_one(db)
    db.commit()
    assert dispatch_one(db) is None  # global concurrency
    for event in [
        EventIn(event_id="1", kind="ringing"),
        EventIn(event_id="2", kind="answered"),
        EventIn(event_id="3", kind="transcript", role="user", text="Здравствуйте"),
        EventIn(event_id="4", kind="completed", result={"simulation": True}),
    ]:
        assert apply_event(db, call, event)
        db.commit()
        assert not apply_event(db, call, event)
    assert not apply_event(db, call, EventIn(event_id="late", kind="answered"))
    db.commit()
    result = client.get("/api/calls/" + call.id).json()
    assert result["call"]["status"] == "completed"
    assert len(result["messages"]) == 1
    assert db.scalar(select(func.count()).select_from(m.CallEvent)) == 4


def test_opt_out_survives_delete_reimport(client, db):
    obj = create(
        client, "contacts", {"name": "Тест", "phone": "+79990000001", "consent_basis": "test"}
    )
    assert client.post("/api/contacts/" + obj["id"] + "/opt-out").status_code == 200
    assert client.delete("/api/contacts/" + obj["id"]).status_code == 200
    obj2 = create(
        client, "contacts", {"name": "Другой", "phone": "+79990000001", "consent_basis": "test"}
    )
    assert not eligible(db, db.get(m.Contact, obj2["id"]))


def test_import_all_or_nothing(client):
    data = "name,phone,consent_basis\nА,+79990000001,test\nБ,invalid,test\n".encode()
    r = client.post(
        "/api/import/contacts?commit=true", files={"file": ("test.csv", data, "text/csv")}
    )
    assert r.status_code == 422
    assert client.get("/api/contacts").json() == []
    assert parse_contacts(data, "test.csv")["valid_count"] == 1


def test_duplicate_numbers_and_normalization(client):
    create(client, "contacts", {"name": "A", "phone": "+7 (999) 000-00-01"})
    assert (
        client.post("/api/contacts", json={"name": "B", "phone": "+79990000001"}).status_code == 409
    )


def test_schedule_timezone():
    campaign = m.Campaign(timezone="Europe/Madrid", start_hour=9, end_hour=18, weekdays=[0])
    assert in_schedule(campaign, datetime(2026, 9, 14, 8, tzinfo=timezone.utc))
    assert not in_schedule(campaign, datetime(2026, 9, 13, 8, tzinfo=timezone.utc))
    assert not in_schedule(campaign, datetime(2026, 9, 14, 20, tzinfo=timezone.utc))


def test_no_consent_cannot_enroll(client):
    contact, campaign = setup_campaign(client)
    other = create(client, "contacts", {"name": "Без согласия", "phone": "+79990000002"})
    client.post("/api/campaigns/" + campaign["id"] + "/pause")
    assert (
        client.post(
            "/api/campaigns/" + campaign["id"] + "/contacts", json={"contact_ids": [other["id"]]}
        ).status_code
        == 422
    )


def test_pause_stop_and_live_gate(client, db):
    contact, campaign = setup_campaign(client)
    assert client.post("/api/campaigns/" + campaign["id"] + "/pause").status_code == 200
    assert dispatch_one(db) is None
    assert client.post("/api/campaigns/" + campaign["id"] + "/stop").status_code == 200
    assert client.post("/api/campaigns/" + campaign["id"] + "/start").status_code == 409
    obj = db.get(m.Campaign, campaign["id"])
    obj.status = "draft"
    obj.mode = "live"
    db.commit()
    assert client.post("/api/campaigns/" + campaign["id"] + "/start").status_code == 409


def test_internal_events_protected(client, db):
    _, _ = setup_campaign(client)
    call = dispatch_one(db)
    db.commit()
    data = {"event_id": "first", "kind": "answered"}
    assert client.post("/internal/calls/" + call.id + "/events", json=data).status_code == 401
    assert (
        client.post(
            "/internal/calls/" + call.id + "/events",
            json=data,
            headers={"Authorization": "Bearer test-service-token-000000000000000000000000"},
        ).status_code
        == 200
    )


def test_delete_erases_history(client, db):
    contact, _ = setup_campaign(client)
    call = dispatch_one(db)
    db.commit()
    assert client.delete("/api/contacts/" + contact["id"]).status_code == 409
    apply_event(db, call, EventIn(event_id="1", kind="answered"))
    apply_event(db, call, EventIn(event_id="2", kind="transcript", role="user", text="Personal"))
    apply_event(db, call, EventIn(event_id="3", kind="completed"))
    db.commit()
    assert client.delete("/api/contacts/" + contact["id"]).status_code == 200
    assert db.scalar(select(func.count()).select_from(m.Message)) == 0
    assert db.scalar(select(func.count()).select_from(m.Call)) == 0
