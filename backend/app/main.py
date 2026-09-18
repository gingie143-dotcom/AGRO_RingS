import hashlib
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from redis import Redis
from redis.exceptions import RedisError
from .config import settings
from .db import session, SessionLocal
from . import models as m, schemas as s
from .security import (
    current_user,
    operator,
    admin,
    service,
    token,
    verify_password,
    bootstrap,
    hasher,
)
from .domain import audit, suppress, eligible, apply_event, ACTIVE
from .imports import parse_contacts, MAX_BYTES


@asynccontextmanager
async def lifespan(app):
    with SessionLocal() as db:
        bootstrap(db)
    yield


app = FastAPI(title="AI Caller", version="0.1.0", lifespan=lifespan)


def row(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def get(db, model, id):
    obj = db.get(model, id)
    if not obj:
        raise HTTPException(404, "Запись не найдена")
    return obj


@app.middleware("http")
async def guards(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS") and not request.url.path.startswith(
        "/internal/"
    ):
        origin = request.headers.get("origin")
        if origin and origin != settings().trusted_origin:
            return JSONResponse({"detail": "Недопустимый Origin"}, 403)
        if request.url.path != "/api/auth/login":
            cookie = request.cookies.get("csrf", "")
            header = request.headers.get("x-csrf-token", "")
            if not cookie or not secrets.compare_digest(cookie, header):
                return JSONResponse({"detail": "CSRF-проверка не пройдена"}, 403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse({"detail": "Дубликат записи или нарушена связь данных"}, 409)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready(db=Depends(session)):
    try:
        db.execute(text("SELECT 1"))
        Redis.from_url(settings().redis_url, socket_connect_timeout=2, socket_timeout=2).ping()
    except Exception:
        raise HTTPException(503, "Dependency unavailable")
    return {"status": "ready"}


def login_limit(request: Request):
    key = hashlib.sha256(
        (request.client.host if request.client else "unknown").encode()
    ).hexdigest()
    try:
        client = Redis.from_url(settings().redis_url, socket_connect_timeout=2, socket_timeout=2)
        # Atomic rate counter with expiry even if the caller disconnects.
        count = client.eval(
            "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],60) end; return n",
            1,
            "login:" + key,
        )
    except RedisError:
        raise HTTPException(503, "Сервис ограничения входа недоступен")
    if count > 10:
        raise HTTPException(429, "Слишком много попыток входа")


@app.post("/api/auth/login", dependencies=[Depends(login_limit)])
def login(data: s.LoginIn, response: Response, db=Depends(session)):
    user = db.scalar(select(m.User).where(m.User.username == data.username))
    valid = (
        verify_password(user.password_hash, data.password)
        if user
        else verify_password(hasher.hash("invalid-user-placeholder"), data.password)
    )
    if not user or not user.active or not valid:
        raise HTTPException(401, "Неверный логин или пароль")
    response.set_cookie(
        "session",
        token(user),
        httponly=True,
        samesite="strict",
        secure=settings().cookie_secure,
        max_age=28800,
    )
    response.set_cookie(
        "csrf",
        secrets.token_urlsafe(32),
        samesite="strict",
        secure=settings().cookie_secure,
        max_age=28800,
    )
    audit(db, user.id, "login", user.id)
    db.commit()
    return {"username": user.username, "role": user.role}


@app.post("/api/auth/logout")
def logout(response: Response, user=Depends(current_user)):
    response.delete_cookie("session")
    response.delete_cookie("csrf")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return {"id": user.id, "username": user.username, "role": user.role}


@app.post("/api/users", status_code=201)
def create_user(data: s.UserIn, user=Depends(admin), db=Depends(session)):
    obj = m.User(username=data.username, password_hash=hasher.hash(data.password), role=data.role)
    db.add(obj)
    db.flush()
    audit(db, user.id, "user.create", obj.id)
    db.commit()
    return {"id": obj.id, "username": obj.username, "role": obj.role}


# Each generated endpoint retains a concrete Pydantic request schema in OpenAPI.
def crud(path, model, schema):
    def listing(
        q: str = "",
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
        user=Depends(current_user),
        db=Depends(session),
    ):
        statement = select(model)
        if q:
            statement = statement.where(model.name.ilike("%" + q[:200] + "%"))
        return [
            row(x)
            for x in db.scalars(
                statement.order_by(model.created_at.desc()).offset(offset).limit(limit)
            )
        ]

    def create(data, user=Depends(operator), db=Depends(session)):
        obj = model(**data.model_dump())
        db.add(obj)
        db.flush()
        audit(db, user.id, path + ".create", obj.id)
        db.commit()
        return row(obj)

    create.__annotations__["data"] = schema

    def edit(id: str, data, user=Depends(operator), db=Depends(session)):
        obj = get(db, model, id)
        if model is m.Contact:
            if data.phone != obj.phone:
                raise HTTPException(409, "Для другого номера создайте отдельный контакт")
            if db.scalar(
                select(m.Call.id).where(m.Call.contact_id == id, m.Call.status.in_(ACTIVE))
            ):
                raise HTTPException(409, "Дождитесь завершения звонка")
        for key, value in data.model_dump().items():
            setattr(obj, key, value)
        audit(db, user.id, path + ".update", obj.id)
        db.commit()
        return row(obj)

    edit.__annotations__["data"] = schema
    app.get("/api/" + path, name=path + "_list")(listing)
    app.post("/api/" + path, status_code=201, name=path + "_create")(create)
    app.put("/api/" + path + "/{id}", name=path + "_update")(edit)


for path, model, schema in [
    ("companies", m.Company, s.CompanyIn),
    ("contacts", m.Contact, s.ContactIn),
    ("scenarios", m.Scenario, s.ScenarioIn),
    ("agents", m.Agent, s.AgentIn),
]:
    crud(path, model, schema)


@app.get("/api/contacts/{id}")
def contact_detail(id: str, user=Depends(current_user), db=Depends(session)):
    obj = get(db, m.Contact, id)
    return {
        "contact": row(obj),
        "calls": [
            row(x)
            for x in db.scalars(
                select(m.Call).where(m.Call.contact_id == id).order_by(m.Call.created_at.desc())
            )
        ],
        "callbacks": [
            row(x) for x in db.scalars(select(m.Callback).where(m.Callback.contact_id == id))
        ],
    }


@app.post("/api/contacts/{id}/opt-out")
def opt_out(id: str, user=Depends(operator), db=Depends(session)):
    obj = get(db, m.Contact, id)
    suppress(db, obj)
    audit(db, user.id, "contact.opt_out", id)
    db.commit()
    return {"ok": True}


@app.delete("/api/contacts/{id}")
def delete_contact(id: str, user=Depends(admin), db=Depends(session)):
    obj = get(db, m.Contact, id)
    if db.scalar(select(m.Call.id).where(m.Call.contact_id == id, m.Call.status.in_(ACTIVE))):
        raise HTTPException(409, "Сначала завершите активный звонок")
    suppress(db, obj)
    db.flush()
    for call in db.scalars(select(m.Call).where(m.Call.contact_id == id)).all():
        db.delete(call)
    db.flush()
    audit(db, user.id, "contact.delete", id)
    db.delete(obj)
    db.commit()
    return {"ok": True}


@app.post("/api/import/contacts")
async def import_contacts(
    file: UploadFile, commit: bool = False, user=Depends(operator), db=Depends(session)
):
    content = await file.read(MAX_BYTES + 1)
    try:
        parsed = parse_contacts(content, file.filename or "")
    except Exception:
        raise HTTPException(422, "Не удалось прочитать CSV/XLSX: проверьте формат и размер")
    for contact in parsed["contacts"]:
        if db.scalar(select(m.Contact.id).where(m.Contact.phone == contact["phone"])):
            parsed["errors"].append({"error": "Номер уже существует в базе"})
    if commit:
        if parsed["errors"]:
            raise HTTPException(
                422, {"message": "Импорт отменён целиком", "errors": parsed["errors"]}
            )
        for contact in parsed["contacts"]:
            db.add(m.Contact(**contact))
        audit(db, user.id, "contacts.import", "batch", count=parsed["valid_count"])
        db.commit()
    return parsed


@app.get("/api/campaigns")
def campaigns(user=Depends(current_user), db=Depends(session)):
    result = []
    for campaign in db.scalars(
        select(m.Campaign).order_by(m.Campaign.created_at.desc()).limit(500)
    ):
        item = row(campaign)
        item["counts"] = dict(
            db.execute(
                select(m.CampaignContact.status, func.count())
                .where(m.CampaignContact.campaign_id == campaign.id)
                .group_by(m.CampaignContact.status)
            ).all()
        )
        result.append(item)
    return result


@app.post("/api/campaigns", status_code=201)
def campaign_create(data: s.CampaignIn, user=Depends(operator), db=Depends(session)):
    get(db, m.Scenario, data.scenario_id)
    get(db, m.Agent, data.agent_id)
    obj = m.Campaign(**data.model_dump())
    db.add(obj)
    db.flush()
    audit(db, user.id, "campaign.create", obj.id)
    db.commit()
    return row(obj)


@app.post("/api/campaigns/{id}/contacts")
def enroll(id: str, data: s.Enrollment, user=Depends(operator), db=Depends(session)):
    campaign = get(db, m.Campaign, id)
    if campaign.status not in ("draft", "paused"):
        raise HTTPException(409, "Добавляйте контакты до запуска или на паузе")
    added = 0
    for contact_id in set(data.contact_ids):
        obj = get(db, m.Contact, contact_id)
        if not eligible(db, obj):
            raise HTTPException(422, "Есть контакт без основания для звонка или с отказом")
        if not db.scalar(
            select(m.CampaignContact.id).where(
                m.CampaignContact.campaign_id == id, m.CampaignContact.contact_id == contact_id
            )
        ):
            db.add(m.CampaignContact(campaign_id=id, contact_id=contact_id))
            added += 1
    audit(db, user.id, "campaign.enroll", id, count=added)
    db.commit()
    return {"added": added}


@app.post("/api/campaigns/{id}/{action}")
def campaign_action(id: str, action: str, user=Depends(operator), db=Depends(session)):
    campaign = db.scalar(select(m.Campaign).where(m.Campaign.id == id).with_for_update())
    if not campaign:
        raise HTTPException(404, "Кампания не найдена")
    transitions = {
        "start": (("draft", "paused"), "running"),
        "pause": (("running",), "paused"),
        "stop": (("running", "paused", "draft"), "stopped"),
    }
    if action not in transitions:
        raise HTTPException(404, "Неизвестное действие")
    before, after = transitions[action]
    if campaign.status not in before:
        raise HTTPException(409, "Недопустимый переход состояния")
    if action == "start":
        if campaign.mode == "live":
            raise HTTPException(
                409, "Реальные кампании заблокированы до приёмки одиночного SIP/AI-звонка"
            )
        if not db.scalar(
            select(m.CampaignContact.id).where(
                m.CampaignContact.campaign_id == id, m.CampaignContact.status == "queued"
            )
        ):
            raise HTTPException(422, "Нет контактов в очереди")
        campaign.error_count = 0
    campaign.status = after
    if action == "stop":
        for entry in db.scalars(
            select(m.CampaignContact).where(
                m.CampaignContact.campaign_id == id, m.CampaignContact.status == "queued"
            )
        ):
            entry.status = "cancelled"
    audit(db, user.id, "campaign." + action, id)
    db.commit()
    return row(campaign)


@app.get("/api/calls")
def calls(
    status: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    user=Depends(current_user),
    db=Depends(session),
):
    query = select(m.Call).order_by(m.Call.created_at.desc()).limit(limit)
    if status:
        query = query.where(m.Call.status == status)
    return [row(x) for x in db.scalars(query)]


@app.get("/api/calls/{id}")
def call_detail(id: str, user=Depends(current_user), db=Depends(session)):
    obj = get(db, m.Call, id)
    messages = db.scalars(
        select(m.Message)
        .join(m.Conversation, m.Conversation.id == m.Message.conversation_id)
        .where(m.Conversation.call_id == id)
        .order_by(m.Message.created_at, m.Message.id)
    ).all()
    return {"call": row(obj), "messages": [row(x) for x in messages]}


@app.post("/internal/calls/{id}/events", dependencies=[Depends(service)])
def events(id: str, data: s.EventIn, db=Depends(session)):
    call = db.scalar(select(m.Call).where(m.Call.id == id).with_for_update())
    if not call:
        raise HTTPException(404, "Call not found")
    applied = apply_event(db, call, data)
    db.commit()
    return {"applied": applied}


@app.get("/api/callbacks")
def callbacks(user=Depends(current_user), db=Depends(session)):
    return [
        row(x) for x in db.scalars(select(m.Callback).order_by(m.Callback.scheduled_at).limit(500))
    ]


@app.post("/api/callbacks", status_code=201)
def callback_create(data: s.CallbackIn, user=Depends(operator), db=Depends(session)):
    contact = get(db, m.Contact, data.contact_id)
    if not eligible(db, contact):
        raise HTTPException(422, "Контакт исключён из обзвона")
    obj = m.Callback(**data.model_dump())
    contact.next_contact_at = data.scheduled_at
    db.add(obj)
    db.flush()
    audit(db, user.id, "callback.create", obj.id)
    db.commit()
    return row(obj)


@app.get("/api/dashboard")
def dashboard(user=Depends(current_user), db=Depends(session)):
    today = m.now().replace(hour=0, minute=0, second=0, microsecond=0)
    counts = dict(db.execute(select(m.Call.status, func.count()).group_by(m.Call.status)).all())
    return {
        "contacts": db.scalar(select(func.count()).select_from(m.Contact)),
        "calls_today": db.scalar(
            select(func.count()).select_from(m.Call).where(m.Call.created_at >= today)
        ),
        "active_calls": sum(counts.get(k, 0) for k in ACTIVE),
        "average_duration": db.scalar(
            select(func.avg(m.Call.duration_seconds)).where(m.Call.status == "completed")
        )
        or 0,
        "statuses": counts,
        "simulation": True,
    }


@app.get("/api/settings")
def configuration(user=Depends(admin)):
    cfg = settings()
    return {
        "call_mode": cfg.call_mode,
        "live_campaigns_enabled": False,
        "max_concurrent_calls": cfg.max_concurrent_calls,
        "retention_days": cfg.retention_days,
        "audio_recording": False,
        "configuration": "env",
        "backup_encryption_configured": bool(cfg.backup_key),
    }


@app.get("/api/audit")
def audit_list(user=Depends(admin), db=Depends(session)):
    return [
        row(x)
        for x in db.scalars(select(m.AuditLog).order_by(m.AuditLog.created_at.desc()).limit(200))
    ]


@app.get("/api/backups")
def backup_list(user=Depends(admin), db=Depends(session)):
    return [
        row(x)
        for x in db.scalars(select(m.BackupJob).order_by(m.BackupJob.created_at.desc()).limit(30))
    ]


@app.post("/api/backups", status_code=202)
def backup_create(user=Depends(admin), db=Depends(session)):
    if not settings().backup_key:
        raise HTTPException(409, "Сначала задайте BACKUP_KEY")
    if db.scalar(select(m.BackupJob.id).where(m.BackupJob.status.in_(("queued", "running")))):
        raise HTTPException(409, "Резервное копирование уже запланировано")
    job = m.BackupJob()
    db.add(job)
    db.flush()
    audit(db, user.id, "backup.request", job.id)
    db.commit()
    return row(job)


@app.post("/api/test-call", status_code=202)
def single_live_test(data: s.TestCallIn, user=Depends(admin), db=Depends(session)):
    import httpx
    from .db import engine
    from .domain import finish

    cfg = settings()
    if not cfg.live_calls_enabled or not cfg.live_test_number:
        raise HTTPException(
            409, "Задайте LIVE_CALLS_ENABLED и LIVE_TEST_NUMBER для одиночного теста"
        )
    if engine.dialect.name != "postgresql":
        raise HTTPException(503, "Одиночный реальный тест требует PostgreSQL")
    with engine.connect() as lock:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(481726)")):
            raise HTTPException(409, "Остановите worker перед одиночным тестом")
        try:
            if db.scalar(select(m.Call.id).where(m.Call.status.in_(ACTIVE))):
                raise HTTPException(409, "Уже есть активный звонок")
            contact = get(db, m.Contact, data.contact_id)
            if contact.phone != cfg.live_test_number or not eligible(db, contact):
                raise HTTPException(
                    422, "Номер не совпадает с разрешённым тестовым или контакт исключён"
                )
            scenario = get(db, m.Scenario, data.scenario_id)
            agent = get(db, m.Agent, data.agent_id)
            call = m.Call(contact_id=contact.id, mode="live")
            db.add(call)
            db.flush()
            db.add(m.Conversation(call_id=call.id))
            audit(db, user.id, "test_call.request", call.id)
            db.commit()
            instructions = (
                "Ты AI-помощник. Представься как AI. Это согласованный технический тест. Говори кратко по-русски. Не заявляй, что умеешь определять мысли или эмоции.\n"
                + scenario.goal
                + "\n"
                + scenario.instructions
                + "\n"
                + agent.instructions
            )
            try:
                response = httpx.post(
                    cfg.gateway_url + "/sessions",
                    json={
                        "call_id": call.id,
                        "mode": "live",
                        "number": contact.phone,
                        "instructions": instructions,
                        "voice": agent.voice,
                    },
                    headers={"Authorization": "Bearer " + cfg.service_token},
                    timeout=15,
                )
                response.raise_for_status()
            except httpx.HTTPError:
                db.refresh(call)
                if call.status in ACTIVE:
                    finish(db, call, "failed", "dispatch_uncertain", {})
                    db.commit()
                raise HTTPException(
                    502, "Не удалось подтвердить запуск. Не повторяйте звонок до проверки Asterisk."
                )
            return row(call)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(481726)"))
