"""User service module managing profile registration and settings in Supabase."""

from __future__ import annotations

import logging
from typing import Dict, Any, Optional
from telegram import User
from database import get_supabase_client
from utils.dates import get_timezone

logger = logging.getLogger(__name__)


def get_or_create_user(telegram_user: Any) -> Dict[str, Any]:
    """Retrieve existing user or register them instantly on /start command.

    Maintains accurate profile data (username, first name) in Supabase.
    Safely accepts telegram.User instance, integer user_id, or dictionary.
    """
    client = get_supabase_client()
    
    # Extract identity fields safely
    if isinstance(telegram_user, int):
        tg_id = telegram_user
        username = None
        first_name = None
    elif hasattr(telegram_user, "id"):
        tg_id = telegram_user.id
        username = getattr(telegram_user, "username", None)
        first_name = getattr(telegram_user, "first_name", None)
    elif isinstance(telegram_user, dict):
        tg_id = telegram_user.get("id") or telegram_user.get("telegram_user_id") or 0
        username = telegram_user.get("username") or telegram_user.get("telegram_username")
        first_name = telegram_user.get("first_name")
    else:
        try:
            tg_id = int(telegram_user)
            username = None
            first_name = None
        except Exception:
            tg_id = 0
            username = None
            first_name = None

    try:
        # Check if user already exists
        res = client.table("users").select("*").eq("telegram_user_id", tg_id).limit(1).execute()
        
        if res.data:
            user_row = res.data[0]
            # Proactively update username/first_name if they changed
            update_fields = {}
            if username and user_row.get("telegram_username") != username:
                update_fields["telegram_username"] = username
            if first_name and user_row.get("first_name") != first_name:
                update_fields["first_name"] = first_name
            if update_fields:
                update_res = (
                    client.table("users")
                    .update(update_fields)
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
