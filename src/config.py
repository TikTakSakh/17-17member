"""Configuration module for the 17/17 bar Telegram bot."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from beartype import beartype
from dotenv import load_dotenv


@beartype
@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment variables."""

    telegram_bot_token: str
    openai_api_key: str
    google_drive_file_id: str
    google_service_account_json: Path
    
    # Optional settings with defaults
    openai_base_url: str | None = None
    max_history_messages: int = 20
    knowledge_base_cache_path: Path = Path("data/knowledge_base.md")
    mini_app_url: str | None = None
    db_path: Path = Path("data/bar1717.db")
    admin_user_ids: list[int] | None = None
    whisper_model: str = "small"


@beartype
def load_config() -> Config:
    """Load configuration from environment variables.
    
    Returns:
        Config object with all settings.
        
    Raises:
        ValueError: If required environment variables are missing.
    """
    load_dotenv()
    
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not telegram_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
    
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
    drive_file_id = os.getenv("GOOGLE_DRIVE_FILE_ID")
    if not drive_file_id:
        raise ValueError("GOOGLE_DRIVE_FILE_ID environment variable is required")
    
    service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not service_account_json:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON environment variable is required")
    
    return Config(
        telegram_bot_token=telegram_token,
        openai_api_key=openai_key,
        google_drive_file_id=drive_file_id,
        google_service_account_json=Path(service_account_json),
        openai_base_url=os.getenv("OPENAI_BASE_URL") or None,
        max_history_messages=int(os.getenv("MAX_HISTORY_MESSAGES", "20")),
        knowledge_base_cache_path=Path(
            os.getenv("KNOWLEDGE_BASE_CACHE_PATH", "data/knowledge_base.md")
        ),
        mini_app_url=os.getenv("MINI_APP_URL") or None,
        db_path=Path(os.getenv("DB_PATH", "data/vanilka.db")),
        admin_user_ids=_parse_admin_ids(os.getenv("ADMIN_USER_IDS")),
        whisper_model=os.getenv("WHISPER_MODEL", "small"),
    )


def _parse_admin_ids(raw: str | None) -> list[int] | None:
    """Parse comma-separated admin user IDs."""
    if not raw:
        return None
    try:
        return [int(uid.strip()) for uid in raw.split(",") if uid.strip()]
    except ValueError:
        return None
