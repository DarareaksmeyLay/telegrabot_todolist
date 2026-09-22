"""Main menu callback query handlers for Todo-list by LDR."""

from __future__ import annotations

import logging
from datetime import datetime
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from services import get_or_create_user, count_dashboard_stats
from keyboards import get_main_menu_keyboard, get_categories_keyboard
from utils.security import authorized_only
from utils.dates import utc_to_local

logger = logging.getLogger(__name__)


@authorized_only
async def menu_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to the main menu dashboard by editing the current active message."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    # Fetch fresh dashboard counts
    stats = count_dashboard_stats(user.id)

    # Localized date string
    local_now = utc_to_local(datetime.utcnow(), user_tz)
    date_display = local_now.strftime("%d %B %Y") if local_now else datetime.utcnow().strftime("%d %B %Y")

    welcome_message = (
        f"👋 Welcome, <b>{user.first_name}</b>!\n\n"
        "📝 <b>Personal To-Do Assistant</b>\n\n"
        f"📅 Today: <code>{date_display}</code>\n\n"
        f"⏳ Pending: <code>{stats['pending']}</code>\n"
        f"🔴 Overdue: <code>{stats['overdue']}</code>\n"
        f"✅ Completed: <code>{stats['completed']}</code>"
    )

    try:
        await query.edit_message_text(
            text=welcome_message,
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML"
        )
    except Exception as exc:
        # Gracefully handle telegram "message is not modified"
        logger.debug("Main menu edit failed (benign): %s", exc)


@authorized_only
async def menu_tasks_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display category options to show filtered lists of tasks."""
    query = update.callback_query
    await query.answer()

    message_text = (
        "📋 <b>Show Tasks</b>\n\n"
        "Which category would you like to view?"
    )

    try:
        await query.edit_message_text(
            text=message_text,
            reply_markup=get_categories_keyboard(),
            parse_mode="HTML"
        )
    except Exception as exc:
        logger.debug("Tasks menu edit failed: %s", exc)


def get_menu_handlers() -> list[CallbackQueryHandler]:
    """Return list of callback handlers for main menu routes."""
    return [
        CallbackQueryHandler(menu_main_callback, pattern="^menu:main$"),
        CallbackQueryHandler(menu_tasks_callback, pattern="^menu:tasks$")
    ]
