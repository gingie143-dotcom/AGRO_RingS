from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://caller:caller@postgres/caller"
    redis_url: str = "redis://redis:6379/0"
    secret_key: str = Field(min_length=32)
    service_token: str = Field(min_length=32)
    admin_username: str = "admin"
    admin_password: str = Field(min_length=12)
    gateway_url: str = "http://voice-gateway:8001"
    call_mode: str = "simulation"
    live_calls_enabled: bool = False
    live_test_number: str = ""
    max_concurrent_calls: int = Field(default=1, ge=1, le=20)
    max_call_seconds: int = Field(default=300, ge=30, le=3600)
    retention_days: int = Field(default=90, ge=1)
    cookie_secure: bool = False
    trusted_origin: str = "http://localhost:3000"
    backup_dir: str = "/backups"
    backup_key: str = ""


@lru_cache
def settings():
    return Settings()
