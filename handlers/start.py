"""Start command handler for Todo-list by LDR.

Performs automatic user registration/sync and displays the primary visual dashboard.
"""

from __future__ import annotations

import logging
from datetime import datetime
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from services import get_or_create_user, count_dashboard_stats
from keyboards import get_main_menu_keyboard
from utils.security import authorized_only
from utils.dates import utc_to_local

logger = logging.getLogger(__name__)


@authorized_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command. Registers user and renders Dashboard."""
    user = update.effective_user
    if not user:
        return

    # Ensure profile registration/sync in Supabase
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    # Fetch real counts from Supabase
    stats = count_dashboard_stats(user.id)

    # Localized date and time string
    local_now = utc_to_local(datetime.utcnow(), user_tz)
    date_display = local_now.strftime("%d %B %Y") if local_now else datetime.utcnow().strftime("%d %B %Y")
    time_display = local_now.strftime("%I:%M %p") if local_now else datetime.utcnow().strftime("%I:%M %p")

    welcome_message = (
        f"👋 Welcome, <b>{user.first_name}</b>!\n\n"
        "📝 <b>Personal To-Do Assistant</b>\n\n"
        f"📅 Today: <code>{date_display}</code>\n"
        f"🕒 Refreshed: <code>{time_display}</code>\n\n"
        f"⏳ Pending: <code>{stats['pending']}</code>\n"
        f"🔴 Overdue: <code>{stats['overdue']}</code>\n"
        f"✅ Completed: <code>{stats['completed']}</code>"
    )

    await update.message.reply_text(
        text=welcome_message,
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML"
    )


def get_start_handler() -> CommandHandler:
    """Return configured CommandHandler for start."""
    return CommandHandler("start", start_command)
