"""Environment-derived settings."""

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    telegram_bot_token: str
    gemini_api_key: str = ""
    telegram_webhook_secret: str = ""
    # NoDecode stops pydantic-settings JSON-decoding the raw value, which it
    # does before validators run -- "111,222" is not JSON, so loading a .env
    # file with two ids failed outright.
    allowed_chat_ids: Annotated[set[int], NoDecode] = Field(default_factory=set)

    database_url: str = (
        "postgresql+pg8000://elcheapo:elcheapo@127.0.0.1:5433/elcheapo"
    )
    currency: str = "CAD"
    timezone: str = "America/Toronto"

    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    gemini_model: str = "gemini-3.5-flash-lite"
    # Minutes of silence after which a chat starts a fresh conversation.
    session_idle_minutes: int = 15

    @field_validator("allowed_chat_ids", mode="before")
    @classmethod
    def _split_chat_ids(cls, value):
        """Accept a comma-separated list, since env vars are strings.

        A lone id reaches us as an int, not a str: pydantic-settings tries to
        JSON-decode env values for complex fields, and a bare number decodes
        successfully. Two or more ids fail that decode and arrive as the raw
        string.
        """
        if isinstance(value, int):
            return {value}
        if isinstance(value, str):
            return {int(part) for part in value.split(",") if part.strip()}
        return value
