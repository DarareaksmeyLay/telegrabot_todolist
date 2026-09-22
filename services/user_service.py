"""User service module managing profile registration and settings in Supabase."""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional
from telegram import User
from database import get_supabase_client
from utils.dates import get_timezone

logger = logging.getLogger(__name__)


def get_or_create_user(telegram_user: User) -> Dict[str, Any]:
    """Retrieve existing user or register them instantly on /start command.

    Maintains accurate profile data (username, first name) in Supabase.
    """
    client = get_supabase_client()
    tg_id = telegram_user.id
    username = telegram_user.username
    first_name = telegram_user.first_name

    try:
        # Check if user already exists
        res = client.table("users").select("*").eq("telegram_user_id", tg_id).limit(1).execute()
        
        if res.data:
            user_row = res.data[0]
            # Proactively update username/first_name if they changed
            if user_row.get("telegram_username") != username or user_row.get("first_name") != first_name:
                update_res = (
                    client.table("users")
                    .update({"telegram_username": username, "first_name": first_name})
                    .eq("telegram_user_id", tg_id)
                    .execute()
                )
                if update_res.data:
                    return update_res.data[0]
            return user_row

        # Otherwise, register new user
        new_user = {
            "telegram_user_id": tg_id,
            "telegram_username": username,
            "first_name": first_name,
            "timezone": "Asia/Phnom_Penh"  # Default startup timezone
        }
        insert_res = client.table("users").insert(new_user).execute()
        if not insert_res.data:
            raise RuntimeError("Database insertion yielded no results.")
            
        logger.info("Registered new user telegram_id=%s (username=@%s)", tg_id, username or "none")
        return insert_res.data[0]

    except Exception as exc:
        logger.error("Failed in get_or_create_user for telegram_id=%s: %s", tg_id, exc)
        # Return local fallback in case of temporary database snags so the user experience doesn't crash
        return {
            "telegram_user_id": tg_id,
            "telegram_username": username,
            "first_name": first_name,
            "timezone": "Asia/Phnom_Penh"
        }


def update_user_timezone(telegram_user_id: int, new_timezone: str) -> bool:
    """Update the user's customized timezone. Validates IANA timezone name before updating."""
    client = get_supabase_client()
    try:
        # Verify timezone validation
        get_timezone(new_timezone)

        res = (
            client.table("users")
            .update({"timezone": new_timezone})
            .eq("telegram_user_id", telegram_user_id)
            .execute()
        )
        if res.data:
            logger.info("Updated timezone to '%s' for user=%s", new_timezone, telegram_user_id)
            return True
        return False
    except Exception as exc:
        logger.error("Error updating timezone for user=%s: %s", telegram_user_id, exc)
        return False
