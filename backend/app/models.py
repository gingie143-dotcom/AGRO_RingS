from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(default=now)


class User(Record, Base):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(default="operator")
    active: Mapped[bool] = mapped_column(default=True)


class Company(Record, Base):
    __tablename__ = "companies"
    name: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str] = mapped_column(Text, default="")


class Contact(Record, Base):
    __tablename__ = "contacts"
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"))
    position: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(default="new")
    consent_basis: Mapped[str] = mapped_column(Text, default="")
    opted_out: Mapped[bool] = mapped_column(default=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    last_contact_at: Mapped[datetime | None]
    next_contact_at: Mapped[datetime | None]


class Suppression(Record, Base):
    __tablename__ = "suppressions"
    phone_hash: Mapped[str] = mapped_column(String(64), unique=True)
    reason: Mapped[str] = mapped_column(default="opt_out")


class Scenario(Record, Base):
    __tablename__ = "scenarios"
    name: Mapped[str] = mapped_column(String(200))
    goal: Mapped[str] = mapped_column(Text)
    instructions: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(default="ru")
    required_questions: Mapped[list] = mapped_column(JSON, default=list)
    optional_questions: Mapped[list] = mapped_column(JSON, default=list)
    allowed_topics: Mapped[list] = mapped_column(JSON, default=list)
    forbidden_topics: Mapped[list] = mapped_column(JSON, default=list)
    transfer_conditions: Mapped[str] = mapped_column(Text, default="По просьбе собеседника")
    end_conditions: Mapped[str] = mapped_column(Text, default="Отказ от дальнейшего общения")
    objection_rules: Mapped[str] = mapped_column(Text, default="Не давить на собеседника")
    interest_criteria: Mapped[str] = mapped_column(Text, default="Явно выраженный интерес")


class Agent(Record, Base):
    __tablename__ = "agents"
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(default="Помощник")
    voice: Mapped[str] = mapped_column(default="marin")
    instructions: Mapped[str] = mapped_column(
        Text, default="Говори кратко и естественно по-русски."
    )


class Campaign(Record, Base):
    __tablename__ = "campaigns"
    name: Mapped[str] = mapped_column(String(200))
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    status: Mapped[str] = mapped_column(default="draft", index=True)
    mode: Mapped[str] = mapped_column(default="simulation")
    max_concurrent: Mapped[int] = mapped_column(default=1)
    delay_seconds: Mapped[int] = mapped_column(default=10)
    max_attempts: Mapped[int] = mapped_column(default=2)
    max_errors: Mapped[int] = mapped_column(default=3)
    error_count: Mapped[int] = mapped_column(default=0)
    timezone: Mapped[str] = mapped_column(default="UTC")
    start_hour: Mapped[int] = mapped_column(default=9)
    end_hour: Mapped[int] = mapped_column(default=18)
    weekdays: Mapped[list] = mapped_column(JSON, default=lambda: [0, 1, 2, 3, 4])
    last_dispatch_at: Mapped[datetime | None]


class CampaignContact(Record, Base):
    __tablename__ = "campaign_contacts"
    __table_args__ = (UniqueConstraint("campaign_id", "contact_id"),)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(default="queued", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    retry_at: Mapped[datetime | None]


class Call(Record, Base):
    __tablename__ = "calls"
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"))
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    campaign_contact_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaign_contacts.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(default="queued", index=True)
    mode: Mapped[str] = mapped_column(default="simulation")
    started_at: Mapped[datetime | None]
    ended_at: Mapped[datetime | None]
    duration_seconds: Mapped[float] = mapped_column(default=0)
    end_reason: Mapped[str] = mapped_column(default="")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    provider_id: Mapped[str | None]


class Conversation(Record, Base):
    __tablename__ = "conversations"
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), unique=True)


class Message(Record, Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("conversation_id", "event_id"),)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    event_id: Mapped[str] = mapped_column(String(200))
    role: Mapped[str]
    text: Mapped[str] = mapped_column(Text)


class Callback(Record, Base):
    __tablename__ = "callbacks"
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"))
    scheduled_at: Mapped[datetime]
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(default="pending")


class AuditLog(Record, Base):
    __tablename__ = "audit_logs"
    actor: Mapped[str]
    action: Mapped[str]
    resource_id: Mapped[str]
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class CallEvent(Record, Base):
    __tablename__ = "call_events"
    __table_args__ = (UniqueConstraint("call_id", "event_id"),)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"))
    event_id: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str]


class BackupJob(Record, Base):
    __tablename__ = "backup_jobs"
    status: Mapped[str] = mapped_column(default="queued")
    filename: Mapped[str] = mapped_column(default="")
    error: Mapped[str] = mapped_column(default="")
