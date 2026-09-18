import re
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CompanyIn(Input):
    name: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=5000)


class ContactIn(Input):
    name: str = Field(min_length=1, max_length=200)
    phone: str
    company_id: str | None = None
    position: str = Field(default="", max_length=200)
    consent_basis: str = Field(default="", max_length=2000)
    extra: dict = Field(default_factory=dict)

    @field_validator("phone")
    @classmethod
    def phone_number(cls, value):
        value = re.sub(r"[\s()\-]", "", value)
        if not re.fullmatch(r"\+[1-9]\d{7,14}", value):
            raise ValueError("Номер должен быть в формате +79991234567")
        return value


class ScenarioIn(Input):
    name: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=5000)
    instructions: str = Field(default="", max_length=10000)
    language: str = Field(default="ru", max_length=10)
    required_questions: list[str] = Field(default_factory=list, max_length=30)
    optional_questions: list[str] = Field(default_factory=list, max_length=30)
    allowed_topics: list[str] = Field(default_factory=list, max_length=30)
    forbidden_topics: list[str] = Field(default_factory=list, max_length=30)
    transfer_conditions: str = "По просьбе собеседника"
    end_conditions: str = "Отказ от дальнейшего общения"
    objection_rules: str = "Не давить на собеседника"
    interest_criteria: str = "Явно выраженный интерес"


class AgentIn(Input):
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(default="Помощник", max_length=200)
    voice: str = Field(default="marin", max_length=50)
    instructions: str = Field(default="Говори кратко и естественно по-русски.", max_length=10000)


class CampaignIn(Input):
    name: str = Field(min_length=1, max_length=200)
    scenario_id: str
    agent_id: str
    mode: Literal["simulation", "live"] = "simulation"
    max_concurrent: int = Field(default=1, ge=1, le=20)
    delay_seconds: int = Field(default=10, ge=1, le=3600)
    max_attempts: int = Field(default=2, ge=1, le=5)
    max_errors: int = Field(default=3, ge=1, le=100)
    timezone: str = "UTC"
    start_hour: int = Field(default=9, ge=0, le=23)
    end_hour: int = Field(default=18, ge=1, le=24)
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], min_length=1, max_length=7)

    @model_validator(mode="after")
    def schedule(self):
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError:
            raise ValueError("Неизвестный часовой пояс")
        if self.start_hour >= self.end_hour or any(d < 0 or d > 6 for d in self.weekdays):
            raise ValueError("Некорректное расписание")
        return self


class LoginIn(Input):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class UserIn(LoginIn):
    role: Literal["admin", "operator", "viewer"] = "operator"

    @field_validator("password")
    @classmethod
    def strong_password(cls, value):
        if len(value) < 12:
            raise ValueError("Минимум 12 символов")
        return value


class CallbackIn(Input):
    contact_id: str
    scheduled_at: datetime
    notes: str = Field(default="", max_length=2000)

    @field_validator("scheduled_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Укажите часовой пояс")
        return value


class EventIn(Input):
    event_id: str = Field(min_length=1, max_length=200)
    kind: Literal[
        "ringing", "answered", "transcript", "completed", "failed", "opt_out", "transferred"
    ]
    role: Literal["user", "assistant"] | None = None
    text: str = Field(default="", max_length=20000)
    reason: str = Field(default="", max_length=200)
    result: dict = Field(default_factory=dict)


class Enrollment(Input):
    contact_ids: list[str] = Field(min_length=1, max_length=1000)


class TestCallIn(Input):
    contact_id: str
    scenario_id: str
    agent_id: str
