"""Configuration module for Todo-list by LDR Telegram Bot.

Loads, validates, and securely stores application settings from environment variables.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Set
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dotenv import load_dotenv

# Load .env file at module import time
load_dotenv()

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    """Application configuration with strict validation and secret masking."""

    telegram_bot_token: str
    supabase_url: str
    supabase_key: str
    allowed_telegram_user_ids: Set[int]
    default_timezone: str = "Asia/Phnom_Penh"
    bot_name: str = "Todo-list by LDR"
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        """Validate timezone string on initialization."""
        try:
            ZoneInfo(self.default_timezone)
        except ZoneInfoNotFoundError:
            raise ValueError(
                f"Invalid DEFAULT_TIMEZONE '{self.default_timezone}'. "
                "Must be a valid IANA time zone identifier (e.g. 'Asia/Phnom_Penh', 'UTC')."
            )

    @property
    def tz(self) -> ZoneInfo:
        """Return the default ZoneInfo object."""
        return ZoneInfo(self.default_timezone)

    def is_user_allowed(self, user_id: int) -> bool:
        """Check if a numeric Telegram user ID is present in the allowlist."""
        # If no allowed users are specified, reject all for safety
        if not self.allowed_telegram_user_ids:
            return False
        return user_id in self.allowed_telegram_user_ids

    def __repr__(self) -> str:
        """Safe representation that guarantees tokens and credentials are never logged."""
        masked_token = (
            f"{self.telegram_bot_token[:4]}...{self.telegram_bot_token[-4:]}"
            if len(self.telegram_bot_token) > 8
            else "***"
        )
        masked_key = (
            f"{self.supabase_key[:4]}...{self.supabase_key[-4:]}"
            if len(self.supabase_key) > 8
            else "***"
        )
        return (
            f"Config("
            f"bot_name='{self.bot_name}', "
            f"default_timezone='{self.default_timezone}', "
            f"telegram_bot_token='{masked_token}', "
            f"supabase_url='{self.supabase_url}', "
            f"supabase_key='{masked_key}', "
            f"allowed_users_count={len(self.allowed_telegram_user_ids)}"
            f")"
        )


def _parse_allowed_user_ids(raw_ids: str) -> Set[int]:
    """Parse comma-separated Telegram user IDs into a set of integers."""
    allowed: Set[int] = set()
    if not raw_ids or not raw_ids.strip():
        return allowed

    parts = raw_ids.split(",")
    for part in parts:
        cleaned = part.strip()
        if not cleaned:
            continue
        try:
            allowed.add(int(cleaned))
        except ValueError:
            logger.warning("Ignoring invalid telegram user ID in ALLOWED_TELEGRAM_USER_IDS: '%s'", cleaned)
    return allowed


def load_config() -> Config:
    """Load configuration from environment with thorough validation."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = os.getenv("SUPABASE_KEY", "").strip()
    raw_allowed_ids = os.getenv("ALLOWED_TELEGRAM_USER_IDS", "").strip()
    default_tz = os.getenv("DEFAULT_TIMEZONE", "Asia/Phnom_Penh").strip()
    bot_name = os.getenv("BOT_NAME", "Todo-list by LDR").strip()
    log_level = os.getenv("LOG_LEVEL", "INFO").strip()

    missing_vars = []
    if not token:
        missing_vars.append("TELEGRAM_BOT_TOKEN")
    if not supabase_url:
        missing_vars.append("SUPABASE_URL")
    if not supabase_key:
        missing_vars.append("SUPABASE_KEY")

    if missing_vars:
        error_msg = (
            f"Missing required environment variables: {', '.join(missing_vars)}. "
            f"Please check your .env file."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)

    allowed_ids = _parse_allowed_user_ids(raw_allowed_ids)
    if not allowed_ids:
        logger.warning(
            "ALLOWED_TELEGRAM_USER_IDS is empty. No Telegram user will be able to access the bot!"
        )

    return Config(
        telegram_bot_token=token,
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        allowed_telegram_user_ids=allowed_ids,
        default_timezone=default_tz,
        bot_name=bot_name,
        log_level=log_level,
    )


# Global configuration instance
config = load_config()
