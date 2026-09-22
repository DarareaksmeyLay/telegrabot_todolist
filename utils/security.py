"""Security and authorization module for Todo-list by LDR.

Guarantees strict Telegram user ID validation, callback authorization,
and database ownership verification to prevent ID spoofing and horizontal privilege escalation.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Coroutine, Optional, Dict
from telegram import Update
from telegram.ext import ContextTypes
from supabase import Client

from config import config

logger = logging.getLogger(__name__)


def is_user_authorized(telegram_user_id: int) -> bool:
    """Return True if telegram_user_id exists in the configured whitelist."""
    return config.is_user_allowed(telegram_user_id)


def authorized_only(
    handler_func: Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, Any]]
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, Any]]:
    """Decorator to enforce Telegram user authorization on commands and callbacks.

    Rejects unauthorized users before executing any handler logic, preventing unauthorized access.
    """

    @functools.wraps(handler_func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        user = update.effective_user
        if not user:
            logger.warning("Received update without effective_user; rejecting request.")
            return None

        if not is_user_authorized(user.id):
            logger.warning(
                "Unauthorized access attempt blocked for user_id=%s (username=@%s)",
                user.id,
                user.username or "none",
            )
            # Notify the user politely
            message_text = (
                "⛔ <b>Access Restricted</b>\n\n"
                "This is a private personal To-Do bot for authorized users only.\n"
                f"Your Telegram ID: <code>{user.id}</code>"
            )
            if update.callback_query:
                await update.callback_query.answer("⛔ Access Denied. You are not authorized.", show_alert=True)
                try:
                    await update.callback_query.edit_message_text(message_text, parse_mode="HTML")
                except Exception:
                    pass
            elif update.effective_message:
                await update.effective_message.reply_text(message_text, parse_mode="HTML")
            return None

        return await handler_func(update, context, *args, **kwargs)

    return wrapper


def verify_task_ownership(
    supabase_client: Client,
    task_id: str,
    telegram_user_id: int
) -> Optional[Dict[str, Any]]:
    """Verify that a task belongs to the authenticated Telegram user.

    Ensures that callback_data manipulation cannot allow a user to view, edit,
    or delete tasks belonging to other users.

    Args:
        supabase_client: Connected Supabase Client instance.
        task_id: UUID of the task from callback data or user input.
        telegram_user_id: Authenticated numeric Telegram user ID.

    Returns:
        The task dictionary if valid and owned by user, otherwise None.
    """
    try:
        # First lookup internal user UUID from telegram_user_id
        user_res = (
            supabase_client.table("users")
            .select("id")
            .eq("telegram_user_id", telegram_user_id)
            .limit(1)
            .execute()
        )
        if not user_res.data:
            logger.warning("No user found in database for telegram_user_id=%s", telegram_user_id)
            return None

        internal_user_id = user_res.data[0]["id"]

        # Fetch task strictly filtering by both task.id AND user_id
        task_res = (
            supabase_client.table("tasks")
            .select("*")
            .eq("id", task_id)
            .eq("user_id", internal_user_id)
            .limit(1)
            .execute()
        )

        if not task_res.data:
            logger.warning(
                "Security alert: User %s attempted to access non-owned or non-existent task %s",
                telegram_user_id,
                task_id,
            )
            return None

        return task_res.data[0]

    except Exception as exc:
        logger.error("Error during verify_task_ownership: %s", exc)
        return None
