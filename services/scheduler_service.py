"""Background reminder polling and direct alert dispatcher scheduler for Todo-list by LDR."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import get_supabase_client
from utils.formatters import format_relative_date, format_time

logger = logging.getLogger(__name__)


def format_reminder_message(task: dict, user_timezone: str) -> str:
    """Format a highly readable Markdown alert for task reminders."""
    title = task.get("title", "Untitled")
    category = task.get("category", "personal").capitalize()
    priority = task.get("priority", "medium")
    due_at_str = task.get("due_at")

    # Priority Icon mapping
    prio_icon = "🟢 Low"
    if priority == "high":
        prio_icon = "🔴 High"
    elif priority == "medium":
        prio_icon = "🟡 Medium"

    due_display = "🚫 No Due Date"
    if due_at_str:
        try:
            due_display_date = format_relative_date(due_at_str, user_timezone)
            due_display_time = format_time(due_at_str, user_timezone)
            due_display = f"{due_display_date} • {due_display_time}"
        except Exception:
            due_display = "Date/Time Error"

    msg = (
        "🔔 <b>TASK REMINDER</b>\n"
        "────────────────\n\n"
        f"📝 <b>Name:</b> {title}\n"
        f"📁 <b>Category:</b> {category}\n"
        f"🚩 <b>Priority:</b> {prio_icon}\n"
        f"📅 <b>Due At:</b> {due_display}\n\n"
        "<i>Don't forget to complete your task! You can manage it with the buttons below:</i>"
    )
    return msg


async def poll_and_dispatch_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check Supabase for pending reminders, deliver direct alerts, and flag them as sent."""
    logger.info("Executing background reminder polling check...")
    client = get_supabase_client()
    now_utc = datetime.now(timezone.utc).isoformat()

    try:
        # Fetch pending reminders scheduled for now or in the past
        # We perform a relational joined query to fetch the associated tasks and users
        res = (
            client.table("reminders")
            .select("*, tasks(*), users(*)")
            .eq("status", "pending")
            .lte("remind_at", now_utc)
            .execute()
        )
    except Exception as exc:
        logger.error("Database query failed inside reminder scheduler: %s", exc)
        return

    reminders = res.data or []
    if not reminders:
        return

    logger.info("Found %d pending reminders to dispatch.", len(reminders))

    for item in reminders:
        reminder_id = item.get("id")
        task_data = item.get("tasks")
        user_data = item.get("users")

        # Normalize Postgrest relation results (which can occasionally be lists or single dicts)
        if isinstance(task_data, list) and task_data:
            task_data = task_data[0]
        if isinstance(user_data, list) and user_data:
            user_data = user_data[0]

        if not task_data or not user_data:
            logger.warning("Reminder %s had missing task or user relation. Marking as cancelled.", reminder_id)
            try:
                client.table("reminders").update({"status": "cancelled"}).eq("id", reminder_id).execute()
            except Exception:
                pass
            continue

        # Extract Telegram delivery targets and preferences
        telegram_user_id = user_data.get("telegram_user_id")
        user_timezone = user_data.get("timezone", "Asia/Phnom_Penh")
        task_id = task_data.get("id")

        if not telegram_user_id:
            logger.warning("User entry for reminder %s lacks telegram_user_id. Skipping.", reminder_id)
            continue

        # Format message content
        text = format_reminder_message(task_data, user_timezone)

        # Build inline action buttons for immediate, non-intrusive alert handling
        keyboard = [
            [
                InlineKeyboardButton("✅ Mark Completed", callback_data=f"task:done:{task_id}"),
                InlineKeyboardButton("📅 Reschedule", callback_data=f"task:resched:{task_id}")
            ],
            [
                InlineKeyboardButton("🏠 Main Menu", callback_data="menu:main")
            ]
        ]
        markup = InlineKeyboardMarkup(keyboard)

        # Dispatch direct message
        try:
            await context.bot.send_message(
                chat_id=telegram_user_id,
                text=text,
                reply_markup=markup,
                parse_mode="HTML"
            )
            # Flag reminder as successfully delivered
            client.table("reminders").update({
                "status": "sent",
                "sent_at": datetime.utcnow().isoformat()
            }).eq("id", reminder_id).execute()
            logger.info("Successfully delivered reminder %s to telegram user %s", reminder_id, telegram_user_id)

        except Exception as exc:
            # Handle user blocks or chats deleted gracefully
            logger.error(
                "Failed to deliver reminder %s to user %s. Flagging as cancelled. Error: %s",
                reminder_id,
                telegram_user_id,
                exc
            )
            try:
                client.table("reminders").update({"status": "cancelled"}).eq("id", reminder_id).execute()
            except Exception as update_exc:
                logger.error("Failed to mark failed reminder as cancelled: %s", update_exc)


def format_overdue_alert_message(task: dict, user_timezone: str) -> str:
    """Format a highly readable Markdown alert for overdue tasks."""
    title = task.get("title", "Untitled")
    category = task.get("category", "personal").capitalize()
    priority = task.get("priority", "medium")
    due_at_str = task.get("due_at")

    # Priority Icon mapping
    prio_icon = "🟢 Low"
    if priority == "high":
        prio_icon = "🔴 High"
    elif priority == "medium":
        prio_icon = "🟡 Medium"

    due_display = "🚫 No Due Date"
    if due_at_str:
        try:
            due_display_date = format_relative_date(due_at_str, user_timezone)
            due_display_time = format_time(due_at_str, user_timezone)
            due_display = f"{due_display_date} • {due_display_time}"
        except Exception:
            due_display = "Date/Time Error"

    msg = (
        "🚨 <b>OVERDUE TASK ALERT</b>\n"
        "──────────────────\n\n"
        f"📝 <b>Name:</b> {title}\n"
        f"📁 <b>Category:</b> {category}\n"
        f"🚩 <b>Priority:</b> {prio_icon}\n"
        f"📅 <b>Due At:</b> {due_display}\n\n"
        "⚠️ <i>This task has passed its due time and is now marked as overdue. Please complete or reschedule it!</i>"
    )
    return msg


async def check_pending_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check Supabase for overdue tasks with status 'pending' every minute, update their status to 'overdue', and trigger direct alerts immediately."""
    logger.info("Executing periodic check for overdue tasks (check_pending_reminders)...")
    client = get_supabase_client()
    now_utc_dt = datetime.now(timezone.utc)
    now_utc = now_utc_dt.isoformat()

    try:
        # Fetch tasks with 'pending' status whose due_at has passed
        res = (
            client.table("tasks")
            .select("*, users(*)")
            .eq("status", "pending")
            .lt("due_at", now_utc)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to query overdue tasks in check_pending_reminders: %s", exc)
        return

    overdue_tasks = res.data or []
    if not overdue_tasks:
        return

    logger.info("Found %d pending overdue tasks to transition and alert.", len(overdue_tasks))

    for task in overdue_tasks:
        task_id = task.get("id")
        user_data = task.get("users")

        # Normalize relation formats
        if isinstance(user_data, list) and user_data:
            user_data = user_data[0]

        if not user_data:
            logger.warning("Overdue task %s is missing its user relation. Skipping.", task_id)
            continue

        telegram_user_id = user_data.get("telegram_user_id")
        user_timezone = user_data.get("timezone", "Asia/Phnom_Penh")

        if not telegram_user_id:
            logger.warning("User for overdue task %s has no telegram_user_id. Skipping.", task_id)
            continue

        # 1. Update status to 'overdue' in Supabase to avoid double alerting
        try:
            client.table("tasks").update({"status": "overdue"}).eq("id", task_id).execute()
            logger.info("Successfully transitioned task %s to 'overdue' in Supabase.", task_id)
        except Exception as exc:
            logger.error("Could not update task %s to 'overdue' status in Supabase (check DB constraints): %s", task_id, exc)

        # 2. Automatically cancel any general scheduled reminders for this task
        try:
            client.table("reminders").update({"status": "cancelled"}).eq("task_id", task_id).eq("status", "pending").execute()
        except Exception as exc:
            logger.error("Failed to cancel pending reminders for overdue task %s: %s", task_id, exc)

        # 3. Deliver immediate overdue notification message to the Telegram user
        text = format_overdue_alert_message(task, user_timezone)

        keyboard = [
            [
                InlineKeyboardButton("✅ Mark Completed", callback_data=f"task:done:{task_id}"),
                InlineKeyboardButton("📅 Reschedule", callback_data=f"task:resched:{task_id}")
            ],
            [
                InlineKeyboardButton("🏠 Main Menu", callback_data="menu:main")
            ]
        ]
        markup = InlineKeyboardMarkup(keyboard)

        try:
            await context.bot.send_message(
                chat_id=telegram_user_id,
                text=text,
                reply_markup=markup,
                parse_mode="HTML"
            )
            logger.info("Successfully triggered immediate overdue alert for task %s to user %s", task_id, telegram_user_id)
        except Exception as exc:
            logger.error("Failed to deliver immediate overdue alert for task %s to user %s: %s", task_id, telegram_user_id, exc)

