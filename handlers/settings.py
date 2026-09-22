"""Settings callback query handlers for Todo-list by LDR."""

from __future__ import annotations

import logging
from datetime import datetime
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from services.user_service import get_or_create_user, update_user_timezone
from keyboards.settings import get_settings_keyboard, get_timezone_keyboard
from utils.security import authorized_only

logger = logging.getLogger(__name__)


@authorized_only
async def settings_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the settings profile configuration screen."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    db_user = get_or_create_user(user)
    
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")
    created_at_raw = db_user.get("created_at")
    
    # Try parsing registered date cleanly
    member_since = "Recent"
    if created_at_raw:
        try:
            # Handle standard ISO timestamp
            dt = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
            member_since = dt.strftime("%d %B %Y")
        except Exception:
            pass

    settings_message = (
        "⚙️ <b>PREFERENCES & SETTINGS</b>\n"
        "──────────────────────\n"
        f"👤 <b>Name:</b> {user.first_name}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>\n"
        f"🌐 <b>Current Timezone:</b> <code>{user_tz}</code>\n"
        f"📅 <b>Registered On:</b> <code>{member_since}</code>\n\n"
        "Configure your preferred localized settings below:"
    )

    try:
        await query.edit_message_text(
            text=settings_message,
            reply_markup=get_settings_keyboard(),
            parse_mode="HTML"
        )
    except Exception as exc:
        logger.error("Failed to render settings dashboard: %s", exc)


@authorized_only
async def settings_timezone_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display a choice of common timezones for localized due-date scheduling."""
    query = update.callback_query
    await query.answer()

    message_text = (
        "🌐 <b>CONFIGURE TIMEZONE</b>\n"
        "──────────────────────\n"
        "Select your local timezone. This ensures your tasks, upcoming summaries, "
        "and scheduled reminders are delivered with complete timing accuracy.\n\n"
        "Select an option below:"
    )

    try:
        await query.edit_message_text(
            text=message_text,
            reply_markup=get_timezone_keyboard(),
            parse_mode="HTML"
        )
    except Exception as exc:
        logger.error("Failed to render timezone list selection: %s", exc)


@authorized_only
async def settings_timezone_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set the user's timezone to the selected option and return to settings."""
    query = update.callback_query
    
    # Extract the timezone from callback data: settings:timezone:set:<tz>
    data = query.data or ""
    prefix = "settings:timezone:set:"
    if not data.startswith(prefix):
        await query.answer("Invalid request data.", show_alert=True)
        return
        
    target_tz = data[len(prefix):]
    user = update.effective_user
    
    success = update_user_timezone(user.id, target_tz)
    if success:
        await query.answer(f"✅ Timezone successfully updated to {target_tz}!", show_alert=True)
    else:
        await query.answer("❌ Failed to update timezone in database.", show_alert=True)

    # Re-render settings dashboard to show updated values
    # We pass a fake context & trigger settings_main_callback
    await settings_main_callback(update, context)


def get_settings_handlers() -> list[CallbackQueryHandler]:
    """Return callback query handlers for all Settings routes."""
    return [
        CallbackQueryHandler(settings_main_callback, pattern="^menu:settings$"),
        CallbackQueryHandler(settings_timezone_list_callback, pattern="^settings:timezone:list$"),
        CallbackQueryHandler(settings_timezone_set_callback, pattern="^settings:timezone:set:")
    ]
