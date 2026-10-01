"""Background reminder polling and direct alert dispatcher scheduler for Todo-list by LDR."""

from __future__ import annotations

import html
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Set
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import get_supabase_client
from utils.dates import utc_to_local
from utils.formatters import format_relative_date, format_time

logger = logging.getLogger(__name__)

# In-memory tracking to guarantee alerts never spam faster than per 5 minutes
# and that dispatched reminders are never duplicated within a process lifetime
_last_overdue_alert_time: Dict[str, datetime] = {}
_dispatched_reminders: Set[str] = set()


def reset_task_alert_state(task_id: str) -> None:
    """Reset the alert throttle state for a task when it is completed, snoozed, or rescheduled."""
    _last_overdue_alert_time.pop(task_id, None)
    logger.debug("Reset alert throttle state for task %s", task_id)


def format_reminder_message(task: dict, user_timezone: str, reminder_record: Optional[dict] = None) -> str:
    """Format a highly readable HTML alert for task reminders, indicating 1st or 2nd Alert."""
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

    alert_header = "🔔 <b>TASK REMINDER</b>"
    if reminder_record and due_at_str:
        try:
            due_dt = datetime.fromisoformat(due_at_str.replace("Z", "+00:00"))
            rem_str = reminder_record.get("remind_at")
            if rem_str:
                rem_dt = datetime.fromisoformat(rem_str.replace("Z", "+00:00"))
                local_due = utc_to_local(due_dt, user_timezone)
                local_rem = utc_to_local(rem_dt, user_timezone)
                if local_due and local_rem and local_due.date() == local_rem.date():
                    alert_header = "🔔 <b>DUE DATE ALERT (2nd Reminder)</b>"
                else:
                    alert_header = "🔔 <b>ADVANCE ALERT (1st Reminder)</b>"
        except Exception:
            pass

    msg = (
        f"{alert_header}\n"
        "────────────────\n\n"
        f"📝 <b>Name:</b> {html.escape(title)}\n"
        f"📁 <b>Category:</b> {html.escape(category)}\n"
        f"🚩 <b>Priority:</b> {prio_icon}\n"
        f"📅 <b>Due At:</b> {due_display}\n\n"
        "<i>Don't forget to complete your task! You can manage it with the buttons below:</i>"
    )
    return msg


async def poll_and_dispatch_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check Supabase for pending reminders, deliver direct alerts, and flag them as sent."""
    logger.debug("Executing background reminder polling check...")
    client = get_supabase_client()
    now_utc_dt = datetime.now(timezone.utc)
    now_utc = now_utc_dt.isoformat()

    try:
        # Fetch pending reminders scheduled for now or in the past
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

        # Normalize Postgrest relation results
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

        task_id = task_data.get("id")
        task_status = task_data.get("status", "pending")

        # If task is already completed, do not send reminder
        if task_status == "completed":
            logger.info("Task %s is already completed. Cancelling reminder %s.", task_id, reminder_id)
            try:
                client.table("reminders").update({"status": "cancelled"}).eq("id", reminder_id).execute()
            except Exception:
                pass
            continue

        # Prevent duplicate in-memory dispatch in case of tight polling loops
        if reminder_id in _dispatched_reminders:
            continue
        _dispatched_reminders.add(reminder_id)

        # Extract Telegram delivery targets
        telegram_user_id = user_data.get("telegram_user_id")
        user_timezone = user_data.get("timezone", "Asia/Phnom_Penh")

        if not telegram_user_id:
            logger.warning("User entry for reminder %s lacks telegram_user_id. Skipping.", reminder_id)
            continue

        # Format message content
        text = format_reminder_message(task_data, user_timezone, reminder_record=item)

        # Inline action buttons: Mark Completed, Snooze 5 min, Change Date, Change Hour, Main Menu
        keyboard = [
            [
                InlineKeyboardButton("✅ Mark Completed", callback_data=f"task:done:{task_id}"),
                InlineKeyboardButton("⏰ Snooze (5 min)", callback_data=f"task:snooze:{task_id}:5")
            ],
            [
                InlineKeyboardButton("📅 Change Date", callback_data=f"edit:field:date:{task_id}"),
                InlineKeyboardButton("⏰ Change Hour", callback_data=f"edit:field:time:{task_id}")
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
            logger.info("Successfully delivered reminder %s to telegram user %s", reminder_id, telegram_user_id)

            # Flag reminder as successfully delivered in Supabase
            try:
                client.table("reminders").update({
                    "status": "sent",
                    "sent_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", reminder_id).execute()
            except Exception as upd_err:
                logger.error("Failed to mark reminder %s as sent in database: %s", reminder_id, upd_err)

        except Exception as exc:
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
    """Format a highly readable HTML alert for overdue tasks."""
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
        f"📝 <b>Name:</b> {html.escape(title)}\n"
        f"📁 <b>Category:</b> {html.escape(category)}\n"
        f"🚩 <b>Priority:</b> {prio_icon}\n"
        f"📅 <b>Due At:</b> {due_display}\n\n"
        "⚠️ <i>This task has passed its due time and is now marked as overdue. "
        "Please complete it or reschedule the date and hour using the buttons below:</i>"
    )
    return msg


async def check_pending_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check Supabase for overdue tasks and remind the user every 5 minutes until completed or rescheduled.
    
    Guarantees reminders repeat per 5 minutes (300 seconds), preventing repeated 1-minute alert loops.
    Provides direct action buttons for Mark Completed, Snooze (5 min), Change Date, and Change Hour.
    """
    logger.debug("Executing 5-minute overdue reminder check...")
    client = get_supabase_client()
    now_utc_dt = datetime.now(timezone.utc)
    now_utc = now_utc_dt.isoformat()

    try:
        # Fetch pending or overdue tasks whose due_at has passed
        res = (
            client.table("tasks")
            .select("*, users(*)")
            .in_("status", ["pending", "overdue"])
            .lt("due_at", now_utc)
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to query overdue tasks in check_pending_reminders: %s", exc)
        return

    overdue_tasks = res.data or []
    if not overdue_tasks:
        return

    for task in overdue_tasks:
        task_id = task.get("id")
        user_data = task.get("users")
        due_at = task.get("due_at")

        if not due_at or not task_id:
            continue

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

        # THROTTLE: Enforce exact 5-minute reminder interval
        # If an alert was sent less than 5 minutes (300 seconds) ago, skip
        last_alert = _last_overdue_alert_time.get(task_id)
        if last_alert:
            elapsed = (now_utc_dt - last_alert).total_seconds()
            if elapsed < 300:  # 5 minutes
                logger.debug("Throttling overdue alert for task %s (sent %.0fs ago, waiting for 300s)", task_id, elapsed)
                continue

        # Record this dispatch time to enforce the 5-minute reminder interval
        _last_overdue_alert_time[task_id] = now_utc_dt

        # Attempt to transition status to 'overdue' in Supabase
        try:
            client.table("tasks").update({"status": "overdue"}).eq("id", task_id).execute()
        except Exception as exc:
            logger.debug("Could not update task %s to 'overdue' in DB (may need constraint update): %s", task_id, exc)

        # Cancel any obsolete pending reminders for this passed task
        try:
            client.table("reminders").update({"status": "cancelled"}).eq("task_id", task_id).eq("status", "pending").execute()
        except Exception as exc:
            logger.debug("Failed to cancel pending reminders for overdue task %s: %s", task_id, exc)

        # Deliver overdue notification message with full reschedule and snooze controls
        text = format_overdue_alert_message(task, user_timezone)

        keyboard = [
            [
                InlineKeyboardButton("✅ Mark Completed", callback_data=f"task:done:{task_id}"),
                InlineKeyboardButton("⏰ Snooze (5 min)", callback_data=f"task:snooze:{task_id}:5")
            ],
            [
                InlineKeyboardButton("📅 Change Date", callback_data=f"edit:field:date:{task_id}"),
                InlineKeyboardButton("⏰ Change Hour", callback_data=f"edit:field:time:{task_id}")
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
            logger.info("Delivered 5-minute overdue reminder for task %s to user %s", task_id, telegram_user_id)
        except Exception as exc:
            logger.error("Failed to deliver overdue alert for task %s to user %s: %s", task_id, telegram_user_id, exc)
