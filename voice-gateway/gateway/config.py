from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    service_token: str = Field(min_length=32)
    backend_url: str = "http://backend:8000"
    redis_url: str = "redis://redis:6379/0"
    openai_api_key: str = ""
    openai_analysis_model: str = ""
    openai_realtime_model: str = "gpt-realtime-2.1"
    ari_url: str = "http://asterisk:8088/ari"
    ari_username: str = "caller"
    ari_password: str = ""
    live_calls_enabled: bool = False
    live_test_number: str = ""
    sip_endpoint: str = "trunk"
    media_host: str = "voice-gateway"
    max_call_seconds: int = 300
    max_concurrent_calls: int = 1


@lru_cache
def config():
    return Config()
