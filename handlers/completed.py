"""Completed task history and pagination handler for Todo-list by LDR."""

from __future__ import annotations

import logging
import math
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, ContextTypes

from services import get_or_create_user, get_completed_tasks
from utils.security import authorized_only
from utils.formatters import format_relative_date, format_time

logger = logging.getLogger(__name__)

COMPLETED_PER_PAGE = 5


def _generate_completed_text_and_markup(
    tasks: list,
    page: int,
    user_tz: str
) -> tuple[str, InlineKeyboardMarkup]:
    """Format and paginate the completed tasks list with selection buttons."""
    total_tasks = len(tasks)
    total_pages = max(1, math.ceil(total_tasks / COMPLETED_PER_PAGE))
    current_page = max(1, min(page, total_pages))

    header = "✅ <b>Completed Tasks</b>\n"
    header += "────────────────\n\n"

    if not tasks:
        body = "<i>You haven't completed any tasks yet. Keep going!</i>\n\n"
        markup_buttons = []
    else:
        start_idx = (current_page - 1) * COMPLETED_PER_PAGE
        end_idx = start_idx + COMPLETED_PER_PAGE
        page_tasks = tasks[start_idx:end_idx]

        lines = []
        num_buttons = []
        for i, task in enumerate(page_tasks, start=1):
            title = task.get("title", "Untitled")
            completed_at = task.get("completed_at")
            
            if completed_at:
                comp_date = format_relative_date(completed_at, user_tz)
                comp_time = format_time(completed_at, user_tz)
                comp_display = f"{comp_date} • {comp_time}"
            else:
                comp_display = "Unknown"

            lines.append(f"{i}. 🎉 <b>{title}</b>\n   Completed: {comp_display}")
            
            # Select button for viewing individual completed task
            task_id = task.get("id")
            num_buttons.append(InlineKeyboardButton(f"{i}", callback_data=f"task:view:{task_id}"))

        body = "\n\n".join(lines) + f"\n\nPage {current_page} of {total_pages}\n\n"
        markup_buttons = [num_buttons]

    # Add pagination row
    pagination_row = []
    if current_page > 1:
        pagination_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"comp_page:{current_page - 1}"))
    if current_page < total_pages:
        pagination_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"comp_page:{current_page + 1}"))
    
    if pagination_row:
        markup_buttons.append(pagination_row)

    # Return buttons
    markup_buttons.append([
        InlineKeyboardButton("🏠 Main Menu", callback_data="menu:main")
    ])

    return header + body, InlineKeyboardMarkup(markup_buttons)


@authorized_only
async def view_completed_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render the completed tasks history log with custom pagination."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    completed_tasks = get_completed_tasks(user.id)
    text, markup = _generate_completed_text_and_markup(completed_tasks, 1, user_tz)

    try:
        await query.edit_message_text(text=text, reply_markup=markup, parse_mode="HTML")
    except Exception as exc:
        logger.debug("View completed edit failed: %s", exc)


@authorized_only
async def completed_pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle pagination navigation within completed task lists."""
    query = update.callback_query
    await query.answer()

    # Data format: comp_page:<page_number>
    page = int(query.data.split(":")[1])

    user = update.effective_user
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    completed_tasks = get_completed_tasks(user.id)
    text, markup = _generate_completed_text_and_markup(completed_tasks, page, user_tz)

    try:
        await query.edit_message_text(text=text, reply_markup=markup, parse_mode="HTML")
    except Exception as exc:
        logger.debug("Completed pagination edit failed: %s", exc)


def get_completed_handlers() -> list[CallbackQueryHandler]:
    """Return callback query handlers for viewing completed task history logs."""
    return [
        CallbackQueryHandler(view_completed_history_callback, pattern="^menu:completed$"),
        CallbackQueryHandler(completed_pagination_callback, pattern="^comp_page:\\d+$")
    ]
