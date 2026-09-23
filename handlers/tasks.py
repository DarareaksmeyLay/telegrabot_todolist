"""Task navigation and detail handlers for Todo-list by LDR."""

from __future__ import annotations

import logging
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from services import (
    get_or_create_user,
    get_pending_tasks,
    get_overdue_tasks,
    get_task_by_id
)
from database import get_supabase_client
from keyboards import get_tasks_list_keyboard, get_task_details_keyboard
from utils.security import authorized_only
from utils.formatters import (
    get_category_display,
    get_priority_display,
    format_relative_date,
    format_time,
    format_task_detail_card
)

logger = logging.getLogger(__name__)

TASKS_PER_PAGE = 5


def _generate_tasks_text_and_markup(
    tasks_list: list,
    category: str,
    page: int,
    user_tz: str
) -> tuple[str, Any]:
    """Internal helper to construct a beautifully formatted text listing and keyboard."""
    total_tasks = len(tasks_list)
    total_pages = max(1, (total_tasks + TASKS_PER_PAGE - 1) // TASKS_PER_PAGE)
    current_page = max(1, min(page, total_pages))

    # Header definition
    if category == "overdue":
        header_text = "🔴 <b>Overdue Tasks</b>"
    elif category == "all":
        header_text = "📚 <b>All Tasks</b>"
    else:
        header_text = f"{get_category_display(category)} <b>Tasks</b>"

    header = f"{header_text}\n{'─' * 20}\n\n"

    if not tasks_list:
        body = "<i>No pending tasks found in this category.</i>\n\n"
    else:
        start_idx = (current_page - 1) * TASKS_PER_PAGE
        end_idx = start_idx + TASKS_PER_PAGE
        page_tasks = tasks_list[start_idx:end_idx]

        lines = []
        for i, task in enumerate(page_tasks, start=1):
            title = task.get("title", "Untitled")
            priority = get_priority_display(task.get("priority", "medium"))
            due_at = task.get("due_at")
            
            if due_at:
                due_date_str = format_relative_date(due_at, user_tz)
                due_time_str = format_time(due_at, user_tz)
                due_display = f"{due_date_str} • {due_time_str}"
            else:
                due_display = "No Due Date"

            lines.append(f"{i}. {priority} <b>{title}</b>\n   {due_display}")
        
        body = "\n\n".join(lines) + f"\n\nPage {current_page} of {total_pages}\n\n"

    # Construct complete paginated keyboard
    markup = get_tasks_list_keyboard(tasks_list, category, current_page)
    return header + body, markup


@authorized_only
async def view_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Load tasks for the selected category and display a paginated list with numbered selectors."""
    query = update.callback_query
    await query.answer()

    category = query.data.split(":")[1]
    user = update.effective_user
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    # Fetch corresponding data
    if category == "overdue":
        tasks = get_overdue_tasks(user.id)
    else:
        tasks = get_pending_tasks(user.id, category)

    text, markup = _generate_tasks_text_and_markup(tasks, category, 1, user_tz)

    try:
        await query.edit_message_text(text=text, reply_markup=markup, parse_mode="HTML")
    except Exception as exc:
        logger.debug("View category edit failed (benign): %s", exc)


@authorized_only
async def pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle page transitions dynamically by reloading and rendering the appropriate slice of tasks."""
    query = update.callback_query
    await query.answer()

    # Data format: page:<category>:<page_number>
    parts = query.data.split(":")
    category = parts[1]
    page = int(parts[2])

    user = update.effective_user
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    if category == "overdue":
        tasks = get_overdue_tasks(user.id)
    else:
        tasks = get_pending_tasks(user.id, category)

    text, markup = _generate_tasks_text_and_markup(tasks, category, page, user_tz)

    try:
        await query.edit_message_text(text=text, reply_markup=markup, parse_mode="HTML")
    except Exception as exc:
        logger.debug("Pagination edit failed: %s", exc)


@authorized_only
async def view_task_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Query and present full detail card for an individual task with contextual action controls."""
    query = update.callback_query
    await query.answer()

    # Data format: task:view:<id>
    task_id = query.data.split(":")[-1]
    user = update.effective_user
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    task = get_task_by_id(task_id, user.id)
    if not task:
        await query.edit_message_text(
            "⚠️ <b>Task Not Found</b>\n\nThis task does not exist or you do not have permission to view it.",
            reply_markup=get_tasks_list_keyboard([], "all", 1),
            parse_mode="HTML"
        )
        return

    reminders = None
    try:
        client = get_supabase_client()
        rem_res = client.table("reminders").select("*").eq("task_id", task_id).eq("status", "pending").order("remind_at", desc=False).execute()
        reminders = rem_res.data or []
    except Exception as exc:
        logger.debug("Failed to fetch reminders for task card: %s", exc)

    text = format_task_detail_card(task, user_tz, reminders=reminders)
    markup = get_task_details_keyboard(task_id)


    try:
        await query.edit_message_text(text=text, reply_markup=markup, parse_mode="HTML")
    except Exception as exc:
        logger.debug("Task details edit failed: %s", exc)


def get_tasks_handlers() -> list[CallbackQueryHandler]:
    """Return list of handlers for task list, category loading, and details views."""
    return [
        CallbackQueryHandler(view_category_callback, pattern="^cat:(personal|work|school|all|overdue)$"),
        CallbackQueryHandler(pagination_callback, pattern="^page:(personal|work|school|all|overdue):\\d+$"),
        CallbackQueryHandler(view_task_details_callback, pattern="^task:view:[0-9a-fA-F\\-]+$")
    ]
