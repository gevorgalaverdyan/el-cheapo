"""Environment-derived settings."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    telegram_bot_token: str
    gemini_api_key: str = ""
    telegram_webhook_secret: str = ""
    allowed_chat_ids: set[int] = Field(default_factory=set)

    spreadsheet_id: str = ""
    currency: str = "CAD"
    timezone: str = "Africa/Cairo"

    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    gemini_model: str = "gemini-3.5-flash-lite"

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
