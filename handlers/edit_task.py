"""Conversation and Callback handlers for editing, completing, deleting, and rescheduling tasks in Todo-list by LDR.

Provides rich edit submenus (Title, Category, Due Date, Due Time, Priority, Reminder, Repeat)
with full validations, safe back-navigation, and null-safe parameter handling.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime, date, time, timedelta
from typing import Optional, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    CommandHandler,
    filters
)

from services import (
    get_or_create_user,
    get_task_by_id,
    complete_task_by_id,
    delete_task_by_id,
    update_task
)
from database import get_supabase_client
from utils.dates import (
    parse_date_string,
    parse_time_string,
    local_to_utc,
    utc_to_local,
    get_timezone,
    parse_advance_alert_input,
    format_reminder_label
)
from utils.formatters import (
    get_category_display,
    get_priority_display,
    format_relative_date,
    format_time,
    format_task_detail_card
)

logger = logging.getLogger(__name__)

# Conversation States
(
    WAITING_EDIT_TITLE_TEXT,
    WAITING_EDIT_DATE_TEXT,
    WAITING_EDIT_TIME_TEXT,
    WAITING_EDIT_REMIND1_TEXT,
    WAITING_EDIT_REMIND2_TEXT
) = range(5)



# ====================================================================
# UTILITIES & REUSABLE KEYBOARDS
# ====================================================================

def get_edit_cancel_keyboard(task_id: str) -> InlineKeyboardMarkup:
    """Return a keyboard with Back and Cancel buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 Back to Edit Menu", callback_data=f"task:edit:{task_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"task:view:{task_id}")
        ]
    ])


# ====================================================================
# 1. TASK ACTIONS: COMPLETE & DELETE
# ====================================================================

async def handle_complete_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mark task as completed, cancel reminders, and display success card."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[-1]
    user = update.effective_user

    completed_task = complete_task_by_id(task_id, user.id)
    if not completed_task:
        await query.edit_message_text(
            "⚠️ <b>Error</b>\n\nCould not mark task as completed or you do not have permission.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="menu:main")]]),
            parse_mode="HTML"
        )
        return

    title = completed_task.get("title") or "Untitled"
    next_task = completed_task.get("next_task")
    if next_task:
        db_user = get_or_create_user(user)
        user_tz = db_user.get("timezone", "Asia/Phnom_Penh")
        next_due_date = format_relative_date(next_task.get("due_at"), user_tz)
        next_due_time = format_time(next_task.get("due_at"), user_tz)
        rep_rule = (completed_task.get("repeat_rule") or "repeat").capitalize()
        if rep_rule == "Weekdays":
            rep_rule = "Weekdays (Mon–Fri)"
        
        success_text = (
            f"✅ <b>Task Completed!</b>\n\n"
            f"🎉 Great job completing:\n\"<b>{html.escape(title)}</b>\"\n\n"
            f"🔁 <b>{rep_rule} Recurrence:</b>\n"
            f"Next occurrence automatically scheduled for <b>{next_due_date} at {next_due_time}</b>! 💪"
        )
    else:
        success_text = (
            f"✅ <b>Task Completed!</b>\n\n"
            f"🎉 Great job completing:\n\"<b>{html.escape(title)}</b>\"\n\n"
            f"Keep up the excellent work! 💪"
        )

    keyboard = [
        [
            InlineKeyboardButton("📋 Show Tasks", callback_data="menu:tasks"),
            InlineKeyboardButton("✅ Completed Log", callback_data="menu:completed")
        ],
        [
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu:main")
        ]
    ]
    await query.edit_message_text(text=success_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def handle_delete_request_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display delete confirmation dialogue with security safety boundaries."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[-1]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task:
        await query.edit_message_text("⚠️ Task not found.", parse_mode="HTML")
        return

    title = task.get("title") or "Untitled"
    prompt = (
        "⚠️ <b>Delete Task?</b>\n\n"
        f"Are you sure you want to delete \"<b>{html.escape(title)}</b>\"?\n"
        "This action is permanent and cannot be undone."
    )

    keyboard = [
        [
            InlineKeyboardButton("🗑 Yes, Delete", callback_data=f"task:del_confirm:{task_id}")
        ],
        [
            InlineKeyboardButton("❌ Cancel", callback_data=f"task:view:{task_id}")
        ]
    ]
    await query.edit_message_text(text=prompt, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def handle_delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commit permanent deletion from database and acknowledge."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[-1]
    user = update.effective_user

    success = delete_task_by_id(task_id, user.id)
    if not success:
        await query.edit_message_text(
            "⚠️ <b>Deletion Failed</b>\n\nCould not delete the task. It may have already been removed.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="menu:main")]]),
            parse_mode="HTML"
        )
        return

    text = "🗑 <b>Task Deleted Successfully.</b>"
    keyboard = [
        [
            InlineKeyboardButton("📋 Show Tasks", callback_data="menu:tasks"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu:main")
        ]
    ]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


# ====================================================================
# 2. MAIN EDIT MENU & RENDERING HELPER
# ====================================================================

async def render_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: str) -> None:
    """Render or re-render the edit dashboard menu for a given task ID."""
    user = update.effective_user
    task = get_task_by_id(task_id, user.id)
    if not task:
        if update.callback_query:
            await update.callback_query.edit_message_text("⚠️ Task not found.", parse_mode="HTML")
        elif update.effective_message:
            await update.effective_message.reply_text("⚠️ Task not found.", parse_mode="HTML")
        return

    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    title = task.get("title") or "Untitled"
    category = get_category_display(task.get("category") or "personal")
    priority = get_priority_display(task.get("priority") or "medium")
    
    repeat_raw = (task.get("repeat_rule") or "none").lower()
    if repeat_raw == "none":
        repeat_display = "🚫 None"
    elif repeat_raw == "weekdays":
        repeat_display = "💼 Weekdays (Mon–Fri)"
    else:
        repeat_display = f"📅 {repeat_raw.capitalize()}"

    due_at = task.get("due_at")
    if due_at:
        due_str = f"{format_relative_date(due_at, user_tz)} • {format_time(due_at, user_tz)}"
    else:
        due_str = "🚫 No Due Date"

    # Fetch alerts summary
    alerts_summary = "🔕 None"
    try:
        client = get_supabase_client()
        rem_res = client.table("reminders").select("*").eq("task_id", task_id).eq("status", "pending").order("remind_at", desc=False).execute()
        rems = rem_res.data or []
        if rems:
            if len(rems) >= 2:
                alerts_summary = "🔔 2 Alerts (Advance & Due Date)"
            elif len(rems) == 1:
                alerts_summary = "🔔 1 Alert scheduled"
    except Exception:
        pass

    text = (
        "✏️ <b>Edit Task Details</b>\n"
        "────────────────────\n"
        f"📝 <b>Title:</b> {html.escape(title)}\n"
        f"📁 <b>Category:</b> {category}\n"
        f"🚩 <b>Priority:</b> {priority}\n"
        f"⏰ <b>Due:</b> {due_str}\n"
        f"🔁 <b>Repeat:</b> {repeat_display}\n"
        f"🔔 <b>Alerts:</b> {alerts_summary}\n\n"
        "Select what you would like to edit:"
    )

    keyboard = [
        [
            InlineKeyboardButton("📝 Name / Title", callback_data=f"edit:field:title:{task_id}"),
            InlineKeyboardButton("📁 Category", callback_data=f"edit:field:cat:{task_id}")
        ],
        [
            InlineKeyboardButton("📅 Due Date", callback_data=f"edit:field:date:{task_id}"),
            InlineKeyboardButton("⏰ Due Time", callback_data=f"edit:field:time:{task_id}")
        ],
        [
            InlineKeyboardButton("🚩 Priority", callback_data=f"edit:field:priority:{task_id}"),
            InlineKeyboardButton("🔔 Reminder", callback_data=f"edit:field:reminder:{task_id}")
        ],
        [
            InlineKeyboardButton("🔁 Repeat Rule", callback_data=f"edit:field:repeat:{task_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back to Details", callback_data=f"task:view:{task_id}")
        ]
    ]
    markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=markup, parse_mode="HTML")
    elif update.effective_message:
        await update.effective_message.reply_text(text=text, reply_markup=markup, parse_mode="HTML")


async def handle_edit_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display edit dashboard options for the selected task."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[-1]
    await render_edit_menu(update, context, task_id)


# ====================================================================
# 3. FIELD SUBMENUS & INLINE WRITES
# ====================================================================

async def handle_edit_cat_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render Category edit choices."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[-1]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task:
        return

    title = task.get("title") or "Untitled"
    text = f"📁 <b>Edit Category</b> for:\n\"{html.escape(title)}\"\n\nChoose a category:"
    keyboard = [
        [
            InlineKeyboardButton("👤 Personal", callback_data=f"edit:save_cat:personal:{task_id}"),
            InlineKeyboardButton("💼 Work", callback_data=f"edit:save_cat:work:{task_id}")
        ],
        [
            InlineKeyboardButton("🎓 School", callback_data=f"edit:save_cat:school:{task_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=f"task:edit:{task_id}")
        ]
    ]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def handle_save_cat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commit Category change directly and return to edit menu."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    category = parts[2]
    task_id = parts[-1]
    user = update.effective_user

    update_task(task_id, user.id, {"category": category})
    await render_edit_menu(update, context, task_id)


async def handle_edit_priority_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render Priority edit choices."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[-1]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task:
        return

    title = task.get("title") or "Untitled"
    text = f"🚩 <b>Edit Priority</b> for:\n\"{html.escape(title)}\"\n\nSelect Priority rating:"
    keyboard = [
        [
            InlineKeyboardButton("🔴 High", callback_data=f"edit:save_priority:high:{task_id}")
        ],
        [
            InlineKeyboardButton("🟡 Medium", callback_data=f"edit:save_priority:medium:{task_id}")
        ],
        [
            InlineKeyboardButton("🟢 Low", callback_data=f"edit:save_priority:low:{task_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=f"task:edit:{task_id}")
        ]
    ]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def handle_save_priority_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commit Priority change directly and return to edit menu."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    priority = parts[2]
    task_id = parts[-1]
    user = update.effective_user

    update_task(task_id, user.id, {"priority": priority})
    await render_edit_menu(update, context, task_id)


async def handle_edit_repeat_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render Repeat Rule edit choices."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[-1]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task:
        return

    title = task.get("title") or "Untitled"
    repeat_raw = (task.get("repeat_rule") or "none").lower()
    if repeat_raw == "none":
        cur_repeat = "🚫 None"
    elif repeat_raw == "weekdays":
        cur_repeat = "💼 Weekdays (Mon–Fri)"
    else:
        cur_repeat = f"📅 {repeat_raw.capitalize()}"

    text = (
        f"🔁 <b>Edit Repeat Rule</b> for:\n"
        f"\"<b>{html.escape(title)}</b>\"\n\n"
        f"Current: <b>{cur_repeat}</b>\n\n"
        f"Choose how often this task recurs:"
    )
    keyboard = [
        [
            InlineKeyboardButton("🚫 Do Not Repeat", callback_data=f"edit:save_repeat:none:{task_id}")
        ],
        [
            InlineKeyboardButton("📅 Daily", callback_data=f"edit:save_repeat:daily:{task_id}"),
            InlineKeyboardButton("💼 Weekdays (Mon–Fri)", callback_data=f"edit:save_repeat:weekdays:{task_id}")
        ],
        [
            InlineKeyboardButton("🗓 Weekly", callback_data=f"edit:save_repeat:weekly:{task_id}"),
            InlineKeyboardButton("📆 Monthly", callback_data=f"edit:save_repeat:monthly:{task_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back to Edit Menu", callback_data=f"task:edit:{task_id}")
        ]
    ]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def handle_save_repeat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commit Repeat rule change directly and return to edit menu."""
    query = update.callback_query

    parts = query.data.split(":")
    repeat = parts[2]
    task_id = parts[-1]
    user = update.effective_user

    update_task(task_id, user.id, {"repeat_rule": repeat})
    
    rep_label = repeat.capitalize() if repeat != "weekdays" else "Weekdays (Mon–Fri)"
    await query.answer(f"🔁 Repeat rule set to: {rep_label}", show_alert=False)
    await render_edit_menu(update, context, task_id)


async def handle_edit_date_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render Date reschedule choices. Supports both edit:field:date and direct task:resched."""
    query = update.callback_query
    await query.answer()

    # Supports either edit:field:date:<id> or task:resched:<id>
    task_id = query.data.split(":")[-1]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task:
        await query.edit_message_text("⚠️ Task not found.", parse_mode="HTML")
        return

    title = task.get("title") or "Untitled"
    text = f"📅 <b>Reschedule Due Date</b> for:\n\"{html.escape(title)}\"\n\nSelect a new due date:"
    keyboard = [
        [
            InlineKeyboardButton("Today", callback_data=f"edit:save_date:today:{task_id}"),
            InlineKeyboardButton("Tomorrow", callback_data=f"edit:save_date:tomorrow:{task_id}")
        ],
        [
            InlineKeyboardButton("📅 Choose Date", callback_data=f"edit:save_date:custom:{task_id}"),
            InlineKeyboardButton("🚫 No Due Date", callback_data=f"edit:save_date:none:{task_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back to Task", callback_data=f"task:view:{task_id}")
        ]
    ]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def handle_save_preset_date_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commit Preset Date choice, updating task due_at, resetting overdue to pending, and shifting reminders."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    choice = parts[2]
    task_id = parts[-1]
    user = update.effective_user

    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")
    local_tz = get_timezone(user_tz)
    today_local = datetime.now(local_tz).date()

    task = get_task_by_id(task_id, user.id)
    if not task:
        await query.edit_message_text("⚠️ Task not found.", parse_mode="HTML")
        return

    orig_due_at = task.get("due_at")
    if orig_due_at:
        try:
            clean_str = orig_due_at.replace("Z", "+00:00")
            orig_dt = datetime.fromisoformat(clean_str)
            import pytz
            local_dt = orig_dt.astimezone(local_tz)
            orig_time = local_dt.time()
        except Exception:
            orig_time = time(9, 0)
    else:
        orig_time = time(9, 0)

    if choice == "none":
        # Remove due date and reset overdue status to pending
        update_task(task_id, user.id, {"due_at": None, "status": "pending"})
        try:
            client = get_supabase_client()
            client.table("reminders").update({"status": "cancelled"}).eq("task_id", task_id).eq("status", "pending").execute()
        except Exception as exc:
            logger.error("Error cancelling reminders on remove due date: %s", exc)

        # Show updated task details card
        updated_task = get_task_by_id(task_id, user.id)
        from keyboards import get_task_details_keyboard
        success_text = f"✅ <b>Due Date Removed</b>\n\n{format_task_detail_card(updated_task or task, user_tz)}"
        await query.edit_message_text(text=success_text, reply_markup=get_task_details_keyboard(task_id), parse_mode="HTML")
        return

    elif choice == "today":
        target_date = today_local
    elif choice == "tomorrow":
        target_date = today_local + timedelta(days=1)
    else:
        return

    naive_local_dt = datetime.combine(target_date, orig_time)
    due_at_utc = local_to_utc(naive_local_dt, user_tz)

    # When rescheduled, reset status to 'pending' to clear any 'overdue' state
    update_task(task_id, user.id, {"due_at": due_at_utc.isoformat(), "status": "pending"})
    
    old_due_at_utc = None
    if orig_due_at:
        try:
            clean_str = orig_due_at.replace("Z", "+00:00")
            old_due_at_utc = datetime.fromisoformat(clean_str)
        except Exception:
            pass

    # Recalculate and update any pending reminders
    await recalculate_reminders_for_task(task_id, due_at_utc, old_due_at_utc)

    # Return updated task details card with success header
    updated_task = get_task_by_id(task_id, user.id)
    from keyboards import get_task_details_keyboard
    success_text = f"✅ <b>Task Rescheduled Successfully!</b>\n\n{format_task_detail_card(updated_task or task, user_tz)}"
    await query.edit_message_text(text=success_text, reply_markup=get_task_details_keyboard(task_id), parse_mode="HTML")


async def handle_edit_time_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render Time reschedule choices."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[-1]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task:
        return

    # Checking if there is a due date
    if not task.get("due_at"):
        await query.edit_message_text(
            "⚠️ <b>Due Date Required</b>\n\nYou must set a Due Date before configuring a Due Time.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📅 Set Due Date", callback_data=f"edit:field:date:{task_id}")]]) ,
            parse_mode="HTML"
        )
        return

    title = task.get("title") or "Untitled"
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")
    current_time_str = format_time(task.get("due_at"), user_tz) if task.get("due_at") else "Not set"

    text = (
        f"⏰ <b>Reschedule Due Time</b>\n\n"
        f"📝 <b>{html.escape(title)}</b>\n"
        f"Current Time: <b>{current_time_str}</b>\n\n"
        "Select a preset time or enter a custom time:"
    )
    keyboard = [
        [
            InlineKeyboardButton("08:00 AM", callback_data=f"edit:save_time:08:00 AM:{task_id}"),
            InlineKeyboardButton("09:00 AM", callback_data=f"edit:save_time:09:00 AM:{task_id}")
        ],
        [
            InlineKeyboardButton("12:00 PM (Noon)", callback_data=f"edit:save_time:12:00 PM:{task_id}"),
            InlineKeyboardButton("03:00 PM", callback_data=f"edit:save_time:03:00 PM:{task_id}")
        ],
        [
            InlineKeyboardButton("05:00 PM", callback_data=f"edit:save_time:05:00 PM:{task_id}"),
            InlineKeyboardButton("07:00 PM", callback_data=f"edit:save_time:07:00 PM:{task_id}")
        ],
        [
            InlineKeyboardButton("⌨️ Custom Time", callback_data=f"edit:save_time:custom:{task_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back to Edit Menu", callback_data=f"task:edit:{task_id}")
        ]
    ]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def handle_save_preset_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commit Preset Time choice, reassembling due_at and rescheduling reminders."""
    query = update.callback_query
    user = update.effective_user

    import re
    m = re.match(r"^edit:save_time:(.+):([0-9a-fA-F\-]+)$", query.data)
    if not m:
        await query.answer()
        return

    time_str = m.group(1)
    task_id = m.group(2)

    parsed_time = parse_time_string(time_str) or time(9, 0)
    await commit_time_change(task_id, user.id, parsed_time)
    formatted_t = parsed_time.strftime("%I:%M %p").lstrip("0")
    await query.answer(f"⏰ Due time updated to {formatted_t}", show_alert=False)
    await render_edit_menu(update, context, task_id)


def _get_task_reminders(task_id: str, user_tz: str, due_at_utc: Optional[datetime] = None):
    """Retrieve and categorize pending reminders for a task into 1st Alert and 2nd Alert."""
    client = get_supabase_client()
    try:
        rem_res = client.table("reminders").select("*").eq("task_id", task_id).eq("status", "pending").order("remind_at", desc=False).execute()
        rems = rem_res.data or []
    except Exception as exc:
        logger.error("Error fetching reminders: %s", exc)
        rems = []

    rem1 = None
    rem2 = None

    if len(rems) >= 2:
        rem1 = rems[0]
        rem2 = rems[1]
    elif len(rems) == 1:
        r = rems[0]
        if due_at_utc:
            local_r = utc_to_local(r.get("remind_at"), user_tz)
            local_due = utc_to_local(due_at_utc, user_tz)
            if local_r and local_due and local_r.date() == local_due.date():
                rem2 = r
            else:
                rem1 = r
        else:
            rem1 = r

    return rems, rem1, rem2


async def handle_edit_reminder_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render the main dual-reminder management hub for the task."""
    query = update.callback_query
    if query:
        await query.answer()
        task_id = query.data.split(":")[-1]
    else:
        task_id = context.user_data.get("edit_task_id")

    user = update.effective_user
    task = get_task_by_id(task_id, user.id)
    if not task:
        if query:
            await query.edit_message_text("⚠️ Task not found.", parse_mode="HTML")
        return

    if not task.get("due_at"):
        btn = InlineKeyboardButton("📅 Set Due Date", callback_data=f"edit:field:date:{task_id}")
        msg = "⚠️ <b>Due Date Required</b>\n\nYou must set a Due Date before scheduling reminders."
        if query:
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[btn]]), parse_mode="HTML")
        return

    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    due_at_str = task.get("due_at").replace("Z", "+00:00")
    due_at_utc = datetime.fromisoformat(due_at_str)
    due_display = f"{format_relative_date(due_at_str, user_tz)} • {format_time(due_at_str, user_tz)}"

    rems, rem1, rem2 = _get_task_reminders(task_id, user_tz, due_at_utc)

    # Format 1st alert display
    if rem1:
        rem1_dt = datetime.fromisoformat(rem1.get("remind_at").replace("Z", "+00:00"))
        rem1_str = format_reminder_label(rem1_dt, due_at_utc, user_tz)
    else:
        rem1_str = "🔕 Not set"

    # Format 2nd alert display
    if rem2:
        rem2_dt = datetime.fromisoformat(rem2.get("remind_at").replace("Z", "+00:00"))
        rem2_local = utc_to_local(rem2_dt, user_tz)
        rem2_time = rem2_local.strftime("%I:%M %p").lstrip("0") if rem2_local else ""
        rem2_str = f"Due Date at {rem2_time}"
    else:
        rem2_str = "🔕 Not set"

    title = task.get("title") or "Untitled"
    text = (
        "🔔 <b>Manage Task Alerts</b>\n"
        "────────────────────\n"
        f"📝 <b>{html.escape(title)}</b>\n"
        f"📅 <b>Due:</b> {due_display}\n\n"
        "<b>Active Alerts:</b>\n"
        f"• 1st Alert (Advance): <b>{rem1_str}</b>\n"
        f"• 2nd Alert (Due Date): <b>{rem2_str}</b>\n\n"
        "Select an alert option below to configure or update:"
    )

    keyboard = [
        [
            InlineKeyboardButton("🔔 Configure 1st Alert (Advance)", callback_data=f"edit:menu:rem1:{task_id}")
        ],
        [
            InlineKeyboardButton("🔔 Configure 2nd Alert (Due Date)", callback_data=f"edit:menu:rem2:{task_id}")
        ],
        [
            InlineKeyboardButton("🔕 Clear All Alerts", callback_data=f"edit:save_remind:clear:{task_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back to Edit Menu", callback_data=f"task:edit:{task_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"task:view:{task_id}")
        ]
    ]

    markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.edit_message_text(text=text, reply_markup=markup, parse_mode="HTML")
    elif update.effective_message:
        await update.effective_message.reply_text(text=text, reply_markup=markup, parse_mode="HTML")


async def handle_edit_rem1_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render 1st Alert (Advance Reminder) options: 1-4 days, 1 week, custom, or none."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[-1]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task:
        await query.edit_message_text("⚠️ Task not found.", parse_mode="HTML")
        return

    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    due_at_str = task.get("due_at").replace("Z", "+00:00")
    due_at_utc = datetime.fromisoformat(due_at_str)
    due_display = f"{format_relative_date(due_at_str, user_tz)} • {format_time(due_at_str, user_tz)}"

    rems, rem1, rem2 = _get_task_reminders(task_id, user_tz, due_at_utc)
    if rem1:
        rem1_dt = datetime.fromisoformat(rem1.get("remind_at").replace("Z", "+00:00"))
        current_status = format_reminder_label(rem1_dt, due_at_utc, user_tz)
    else:
        current_status = "🔕 Not set"

    title = task.get("title") or "Untitled"
    text = (
        "🔔 <b>Configure 1st Alert (Advance Reminder)</b>\n"
        "────────────────────\n"
        f"📝 Task: <b>{html.escape(title)}</b>\n"
        f"📅 Due: <b>{due_display}</b>\n"
        f"Current: <b>{current_status}</b>\n\n"
        "Choose an advance alert time before your task is due:"
    )

    keyboard = [
        [
            InlineKeyboardButton("1 day before", callback_data=f"edit:save_rem1:1440:{task_id}"),
            InlineKeyboardButton("2 days before", callback_data=f"edit:save_rem1:2880:{task_id}")
        ],
        [
            InlineKeyboardButton("3 days before", callback_data=f"edit:save_rem1:4320:{task_id}"),
            InlineKeyboardButton("4 days before", callback_data=f"edit:save_rem1:5760:{task_id}")
        ],
        [
            InlineKeyboardButton("1 week before", callback_data=f"edit:save_rem1:10080:{task_id}"),
            InlineKeyboardButton("1 hour before", callback_data=f"edit:save_rem1:60:{task_id}")
        ],
        [
            InlineKeyboardButton("⌨️ Custom Advance Alert", callback_data=f"edit:save_rem1:custom:{task_id}"),
            InlineKeyboardButton("🔕 Turn Off 1st Alert", callback_data=f"edit:save_rem1:none:{task_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back to Alerts", callback_data=f"edit:field:reminder:{task_id}")
        ]
    ]

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def handle_edit_rem2_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render 2nd Alert (Due Date Reminder) options: Morning, Afternoon, Evening, Due Time, Custom, or none."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[-1]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task:
        await query.edit_message_text("⚠️ Task not found.", parse_mode="HTML")
        return

    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    due_at_str = task.get("due_at").replace("Z", "+00:00")
    due_at_utc = datetime.fromisoformat(due_at_str)
    due_display = f"{format_relative_date(due_at_str, user_tz)} • {format_time(due_at_str, user_tz)}"

    rems, rem1, rem2 = _get_task_reminders(task_id, user_tz, due_at_utc)
    if rem2:
        rem2_dt = datetime.fromisoformat(rem2.get("remind_at").replace("Z", "+00:00"))
        rem2_local = utc_to_local(rem2_dt, user_tz)
        rem2_time = rem2_local.strftime("%I:%M %p").lstrip("0") if rem2_local else ""
        current_status = f"Due Date at {rem2_time}"
    else:
        current_status = "🔕 Not set"

    title = task.get("title") or "Untitled"
    text = (
        "🔔 <b>Configure 2nd Alert (Due Date Alert)</b>\n"
        "────────────────────\n"
        f"📝 Task: <b>{html.escape(title)}</b>\n"
        f"📅 Due: <b>{due_display}</b>\n"
        f"Current: <b>{current_status}</b>\n\n"
        "Choose an alert time on your due date:"
    )

    keyboard = [
        [
            InlineKeyboardButton("🌅 Morning (08:00 AM)", callback_data=f"edit:save_rem2:morning:{task_id}"),
            InlineKeyboardButton("☀️ Afternoon (01:00 PM)", callback_data=f"edit:save_rem2:afternoon:{task_id}")
        ],
        [
            InlineKeyboardButton("🌙 Evening (06:00 PM)", callback_data=f"edit:save_rem2:evening:{task_id}"),
            InlineKeyboardButton("⏰ At Due Time", callback_data=f"edit:save_rem2:duetime:{task_id}")
        ],
        [
            InlineKeyboardButton("⌨️ Custom Time on Due Date", callback_data=f"edit:save_rem2:custom:{task_id}"),
            InlineKeyboardButton("🔕 Turn Off 2nd Alert", callback_data=f"edit:save_rem2:none:{task_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back to Alerts", callback_data=f"edit:field:reminder:{task_id}")
        ]
    ]

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def handle_save_rem1_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save or remove the 1st alert (advance reminder)."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    choice = parts[2]
    task_id = parts[-1]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task or not task.get("due_at"):
        return

    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")
    client = get_supabase_client()

    due_at_str = task.get("due_at").replace("Z", "+00:00")
    due_at_utc = datetime.fromisoformat(due_at_str)

    # Cancel old 1st alert if present
    rems, old_rem1, old_rem2 = _get_task_reminders(task_id, user_tz, due_at_utc)
    if old_rem1:
        try:
            client.table("reminders").update({"status": "cancelled"}).eq("id", old_rem1["id"]).execute()
        except Exception as exc:
            logger.error("Error cancelling previous 1st reminder: %s", exc)

    if choice != "none":
        offset_minutes = int(choice)
        remind_at_utc = due_at_utc - timedelta(minutes=offset_minutes)

        from datetime import timezone
        if remind_at_utc <= datetime.now(timezone.utc):
            await query.answer("⚠️ This alert time has already passed! Please select a later alert.", show_alert=True)
            return

        db_user_uuid = task.get("user_id")
        try:
            client.table("reminders").insert({
                "task_id": task_id,
                "user_id": db_user_uuid,
                "remind_at": remind_at_utc.isoformat(),
                "status": "pending"
            }).execute()
            logger.info("Saved 1st alert for task %s at %s", task_id, remind_at_utc)
        except Exception as exc:
            logger.error("Error inserting 1st reminder: %s", exc)

    await handle_edit_reminder_menu(update, context)


async def handle_save_rem2_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save or remove the 2nd alert (due date reminder)."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    choice = parts[2]
    task_id = parts[-1]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task or not task.get("due_at"):
        return

    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")
    client = get_supabase_client()

    due_at_str = task.get("due_at").replace("Z", "+00:00")
    due_at_utc = datetime.fromisoformat(due_at_str)
    local_due = utc_to_local(due_at_utc, user_tz)

    # Cancel old 2nd alert if present
    rems, old_rem1, old_rem2 = _get_task_reminders(task_id, user_tz, due_at_utc)
    if old_rem2:
        try:
            client.table("reminders").update({"status": "cancelled"}).eq("id", old_rem2["id"]).execute()
        except Exception as exc:
            logger.error("Error cancelling previous 2nd reminder: %s", exc)

    if choice != "none":
        if choice == "morning":
            target_time = time(8, 0)
        elif choice == "afternoon":
            target_time = time(13, 0)
        elif choice == "evening":
            target_time = time(18, 0)
        elif choice == "duetime":
            target_time = local_due.time() if local_due else time(9, 0)
        else:
            target_time = time(9, 0)

        naive_alert = datetime.combine(local_due.date(), target_time)
        remind_at_utc = local_to_utc(naive_alert, user_tz)

        from datetime import timezone
        if remind_at_utc <= datetime.now(timezone.utc):
            await query.answer("⚠️ This time has already passed today! Please select a later time.", show_alert=True)
            return

        db_user_uuid = task.get("user_id")
        try:
            client.table("reminders").insert({
                "task_id": task_id,
                "user_id": db_user_uuid,
                "remind_at": remind_at_utc.isoformat(),
                "status": "pending"
            }).execute()
            logger.info("Saved 2nd alert for task %s at %s", task_id, remind_at_utc)
        except Exception as exc:
            logger.error("Error inserting 2nd reminder: %s", exc)

    await handle_edit_reminder_menu(update, context)


async def handle_clear_reminders_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear all scheduled alerts for a task."""
    query = update.callback_query
    await query.answer("All alerts cleared.")

    task_id = query.data.split(":")[-1]
    client = get_supabase_client()
    try:
        client.table("reminders").update({"status": "cancelled"}).eq("task_id", task_id).eq("status", "pending").execute()
        logger.info("Cleared all pending alerts for task %s", task_id)
    except Exception as exc:
        logger.error("Error clearing alerts: %s", exc)

    await handle_edit_reminder_menu(update, context)


async def handle_save_reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Legacy compatibility callback routing to handle_save_rem1_callback."""
    await handle_save_rem1_callback(update, context)



# ====================================================================
# UTILITIES FOR TIMESTAMPS
# ====================================================================

async def commit_time_change(task_id: str, telegram_user_id: int, target_time: time) -> None:
    """Assemble date and new time into localized due_at, then push to Supabase."""
    task = get_task_by_id(task_id, telegram_user_id)
    if not task or not task.get("due_at"):
        return

    db_user = get_or_create_user(telegram_user_id)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")
    local_tz = get_timezone(user_tz)

    due_at_str = task.get("due_at").replace("Z", "+00:00")
    due_dt_utc = datetime.fromisoformat(due_at_str)
    local_dt = due_dt_utc.astimezone(local_tz)

    # Re-combine local date with new local time
    new_local_dt = datetime.combine(local_dt.date(), target_time)
    new_utc_dt = local_to_utc(new_local_dt, user_tz)

    update_task(task_id, telegram_user_id, {"due_at": new_utc_dt.isoformat(), "status": "pending"})
    await recalculate_reminders_for_task(task_id, new_utc_dt, due_dt_utc)


async def recalculate_reminders_for_task(
    task_id: str,
    due_at_utc: datetime,
    old_due_at_utc: Optional[datetime] = None
) -> None:
    """Sync any active pending reminders with the newly updated task due date/time."""
    client = get_supabase_client()
    try:
        rem_res = client.table("reminders").select("*").eq("task_id", task_id).eq("status", "pending").execute()
        if not rem_res.data:
            return

        for reminder in rem_res.data:
            try:
                remind_at_str = reminder.get("remind_at").replace("Z", "+00:00")
                remind_at_dt = datetime.fromisoformat(remind_at_str)

                offset = timedelta(0)
                if old_due_at_utc:
                    if old_due_at_utc.tzinfo and not remind_at_dt.tzinfo:
                        remind_at_dt = remind_at_dt.replace(tzinfo=old_due_at_utc.tzinfo)
                    elif not old_due_at_utc.tzinfo and remind_at_dt.tzinfo:
                        old_due_at_utc = old_due_at_utc.replace(tzinfo=remind_at_dt.tzinfo)
                    offset = old_due_at_utc - remind_at_dt

                new_remind_at = due_at_utc - offset
                if due_at_utc.tzinfo and not new_remind_at.tzinfo:
                    new_remind_at = new_remind_at.replace(tzinfo=due_at_utc.tzinfo)

                client.table("reminders").update({
                    "remind_at": new_remind_at.isoformat()
                }).eq("id", reminder["id"]).execute()
                logger.info("Recalculated reminder %s to trigger at %s", reminder["id"], new_remind_at)
            except Exception as item_exc:
                logger.error("Error updating single reminder %s: %s", reminder.get("id"), item_exc)

    except Exception as exc:
        logger.error("Error recalculating reminder: %s", exc)


# ====================================================================
# CONVERSATION STEPS: TEXT INPUT & WRITES
# ====================================================================

async def start_edit_title_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to write a new task name."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[-1]
    context.user_data["edit_task_id"] = task_id

    text = "📝 <b>Edit Task Title</b>\n\nPlease type a new name for your task:"
    await query.edit_message_text(text=text, reply_markup=get_edit_cancel_keyboard(task_id), parse_mode="HTML")
    return WAITING_EDIT_TITLE_TEXT


async def handle_edit_title_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store new task title name in database and return to details log."""
    text = update.message.text.strip()
    task_id = context.user_data.get("edit_task_id")

    if not text:
        await update.message.reply_text("⚠️ Title cannot be empty. Please enter a valid name:")
        return WAITING_EDIT_TITLE_TEXT

    if task_id:
        user = update.effective_user
        update_task(task_id, user.id, {"title": text})
        
        db_user = get_or_create_user(user)
        user_tz = db_user.get("timezone", "Asia/Phnom_Penh")
        task = get_task_by_id(task_id, user.id)
        
        from keyboards import get_task_details_keyboard
        await update.message.reply_text(
            f"✅ <b>Task Title Updated Successfully!</b>\n\n{format_task_detail_card(task, user_tz)}",
            reply_markup=get_task_details_keyboard(task_id),
            parse_mode="HTML"
        )

    context.user_data.pop("edit_task_id", None)
    return ConversationHandler.END


async def start_edit_date_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to write a custom due date."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[-1]
    context.user_data["edit_task_id"] = task_id

    text = (
        "📅 <b>Custom Due Date</b>\n\n"
        "Please type a due date in <b>DD/MM/YYYY</b> format (e.g. <code>25/09/2026</code>):"
    )
    await query.edit_message_text(text=text, reply_markup=get_edit_cancel_keyboard(task_id), parse_mode="HTML")
    return WAITING_EDIT_DATE_TEXT


async def handle_edit_date_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parse custom date text, save to database, and load details."""
    text = update.message.text.strip()
    task_id = context.user_data.get("edit_task_id")
    parsed_date = parse_date_string(text)

    if not parsed_date:
        await update.message.reply_text(
            "⚠️ <b>Invalid Date format</b>\n\n"
            "Please ensure the date format is exactly <b>DD/MM/YYYY</b>, and is a valid future date (e.g., 25/09/2026):",
            reply_markup=get_edit_cancel_keyboard(task_id),
            parse_mode="HTML"
        )
        return WAITING_EDIT_DATE_TEXT

    user = update.effective_user
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")
    local_tz = get_timezone(user_tz)
    today_local = datetime.now(local_tz).date()

    if parsed_date < today_local:
        await update.message.reply_text(
            "⚠️ <b>Past Date</b>\n\nDue date cannot be in the past. Please enter a valid future date:",
            reply_markup=get_edit_cancel_keyboard(task_id),
            parse_mode="HTML"
        )
        return WAITING_EDIT_DATE_TEXT

    if task_id:
        task = get_task_by_id(task_id, user.id)
        if task:
            orig_due_at = task.get("due_at")
            if orig_due_at:
                try:
                    clean_str = orig_due_at.replace("Z", "+00:00")
                    orig_dt = datetime.fromisoformat(clean_str)
                    orig_time = orig_dt.astimezone(local_tz).time()
                except Exception:
                    orig_time = time(9, 0)
            else:
                orig_time = time(9, 0)

            naive_local_dt = datetime.combine(parsed_date, orig_time)
            due_at_utc = local_to_utc(naive_local_dt, user_tz)

            update_task(task_id, user.id, {"due_at": due_at_utc.isoformat(), "status": "pending"})
            await recalculate_reminders_for_task(task_id, due_at_utc)

            updated_task = get_task_by_id(task_id, user.id)
            from keyboards import get_task_details_keyboard
            await update.message.reply_text(
                f"✅ <b>Due Date Updated Successfully!</b>\n\n{format_task_detail_card(updated_task or task, user_tz)}",
                reply_markup=get_task_details_keyboard(task_id),
                parse_mode="HTML"
            )

    context.user_data.pop("edit_task_id", None)
    return ConversationHandler.END


async def start_edit_time_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to write a custom due time."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[-1]
    context.user_data["edit_task_id"] = task_id

    text = (
        "⏰ <b>Custom Due Time</b>\n\n"
        "Please enter a time in HH:MM format or 12-hour format (e.g. <code>14:30</code> or <code>2:30 PM</code>):"
    )
    await query.edit_message_text(text=text, reply_markup=get_edit_cancel_keyboard(task_id), parse_mode="HTML")
    return WAITING_EDIT_TIME_TEXT


async def handle_edit_time_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parse custom time text, save, and return updated details."""
    text = update.message.text.strip()
    task_id = context.user_data.get("edit_task_id")
    parsed_time = parse_time_string(text)

    if not parsed_time:
        await update.message.reply_text(
            "⚠️ <b>Invalid Time format</b>\n\n"
            "Please ensure the format is valid (e.g. <code>14:30</code>, <code>2:30 PM</code>, or <code>9:00 AM</code>):",
            reply_markup=get_edit_cancel_keyboard(task_id),
            parse_mode="HTML"
        )
        return WAITING_EDIT_TIME_TEXT

    if task_id:
        user = update.effective_user
        await commit_time_change(task_id, user.id, parsed_time)

        db_user = get_or_create_user(user)
        user_tz = db_user.get("timezone", "Asia/Phnom_Penh")
        updated_task = get_task_by_id(task_id, user.id)
        
        from keyboards import get_task_details_keyboard
        await update.message.reply_text(
            f"✅ <b>Due Time Updated Successfully!</b>\n\n{format_task_detail_card(updated_task, user_tz)}",
            reply_markup=get_task_details_keyboard(task_id),
            parse_mode="HTML"
        )

    context.user_data.pop("edit_task_id", None)
    return ConversationHandler.END


async def start_edit_rem1_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user for custom advance alert text during task edit."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[-1]
    context.user_data["edit_task_id"] = task_id

    text = (
        "⌨️ <b>Custom First Alert (Advance Reminder)</b>\n\n"
        "Type how long before your task is due (e.g. <code>2 days</code>, <code>3d</code>, <code>5 days</code>, <code>12 hours</code>, <code>30 mins</code>)\n"
        "or enter a specific date/time (e.g. <code>24/09/2026 09:00 AM</code>):"
    )
    await query.edit_message_text(text=text, reply_markup=get_edit_cancel_keyboard(task_id), parse_mode="HTML")
    return WAITING_EDIT_REMIND1_TEXT


async def handle_edit_rem1_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parse custom advance alert, save to database, and update UI."""
    text = update.message.text.strip()
    task_id = context.user_data.get("edit_task_id")
    user = update.effective_user

    if not task_id:
        context.user_data.pop("edit_task_id", None)
        return ConversationHandler.END

    task = get_task_by_id(task_id, user.id)
    if not task or not task.get("due_at"):
        context.user_data.pop("edit_task_id", None)
        return ConversationHandler.END

    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    due_at_str = task.get("due_at").replace("Z", "+00:00")
    due_at_utc = datetime.fromisoformat(due_at_str)
    local_due = utc_to_local(due_at_utc, user_tz)

    parsed_local_dt = parse_advance_alert_input(text, local_due)
    if not parsed_local_dt:
        await update.message.reply_text(
            "⚠️ <b>Invalid Alert Format</b>\n\n"
            "Please enter a valid format (e.g. <code>2 days</code>, <code>3d</code>, <code>12 hours</code>, or <code>24/09/2026 09:00 AM</code>):",
            reply_markup=get_edit_cancel_keyboard(task_id),
            parse_mode="HTML"
        )
        return WAITING_EDIT_REMIND1_TEXT

    remind_at_utc = local_to_utc(parsed_local_dt, user_tz)
    from datetime import timezone
    now_utc = datetime.now(timezone.utc)

    if remind_at_utc >= due_at_utc:
        await update.message.reply_text(
            "⚠️ <b>Alert Must Be Before Due Time</b>\n\n"
            "The 1st alert is an advance reminder and must be set before the due date/time. Please try again:",
            reply_markup=get_edit_cancel_keyboard(task_id),
            parse_mode="HTML"
        )
        return WAITING_EDIT_REMIND1_TEXT

    if remind_at_utc <= now_utc:
        await update.message.reply_text(
            "⚠️ <b>Past Alert Time</b>\n\n"
            "This alert time has already passed. Please enter a future time before your task is due:",
            reply_markup=get_edit_cancel_keyboard(task_id),
            parse_mode="HTML"
        )
        return WAITING_EDIT_REMIND1_TEXT

    client = get_supabase_client()
    rems, old_rem1, old_rem2 = _get_task_reminders(task_id, user_tz, due_at_utc)
    if old_rem1:
        try:
            client.table("reminders").update({"status": "cancelled"}).eq("id", old_rem1["id"]).execute()
        except Exception as exc:
            logger.error("Error cancelling old 1st reminder: %s", exc)

    db_user_uuid = task.get("user_id")
    try:
        client.table("reminders").insert({
            "task_id": task_id,
            "user_id": db_user_uuid,
            "remind_at": remind_at_utc.isoformat(),
            "status": "pending"
        }).execute()
        logger.info("Saved custom 1st alert for task %s at %s", task_id, remind_at_utc)
    except Exception as exc:
        logger.error("Error inserting custom 1st reminder: %s", exc)

    from keyboards import get_task_details_keyboard
    updated_task = get_task_by_id(task_id, user.id)
    await update.message.reply_text(
        f"✅ <b>1st Alert Updated Successfully!</b>\n\n{format_task_detail_card(updated_task, user_tz)}",
        reply_markup=get_task_details_keyboard(task_id),
        parse_mode="HTML"
    )

    context.user_data.pop("edit_task_id", None)
    return ConversationHandler.END


async def start_edit_rem2_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user for custom due date alert time during task edit."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[-1]
    context.user_data["edit_task_id"] = task_id

    text = (
        "⌨️ <b>Custom Second Alert (Due Date Time)</b>\n\n"
        "Enter the alert time on your task's due date (e.g. <code>10:30 AM</code>, <code>2:45 PM</code>, or <code>15:00</code>):"
    )
    await query.edit_message_text(text=text, reply_markup=get_edit_cancel_keyboard(task_id), parse_mode="HTML")
    return WAITING_EDIT_REMIND2_TEXT


async def handle_edit_rem2_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parse custom due date time, save to database, and update UI."""
    text = update.message.text.strip()
    task_id = context.user_data.get("edit_task_id")
    user = update.effective_user

    if not task_id:
        context.user_data.pop("edit_task_id", None)
        return ConversationHandler.END

    task = get_task_by_id(task_id, user.id)
    if not task or not task.get("due_at"):
        context.user_data.pop("edit_task_id", None)
        return ConversationHandler.END

    parsed_time = parse_time_string(text)
    if not parsed_time:
        await update.message.reply_text(
            "⚠️ <b>Invalid Time format</b>\n\n"
            "Please enter a valid time (e.g. <code>10:30 AM</code>, <code>2:30 PM</code>, or <code>15:00</code>):",
            reply_markup=get_edit_cancel_keyboard(task_id),
            parse_mode="HTML"
        )
        return WAITING_EDIT_REMIND2_TEXT

    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    due_at_str = task.get("due_at").replace("Z", "+00:00")
    due_at_utc = datetime.fromisoformat(due_at_str)
    local_due = utc_to_local(due_at_utc, user_tz)

    naive_alert = datetime.combine(local_due.date(), parsed_time)
    remind_at_utc = local_to_utc(naive_alert, user_tz)

    from datetime import timezone
    now_utc = datetime.now(timezone.utc)
    if remind_at_utc <= now_utc:
        await update.message.reply_text(
            "⚠️ <b>Past Time</b>\n\n"
            "This time has already passed today. Please enter a future time on your due date:",
            reply_markup=get_edit_cancel_keyboard(task_id),
            parse_mode="HTML"
        )
        return WAITING_EDIT_REMIND2_TEXT

    client = get_supabase_client()
    rems, old_rem1, old_rem2 = _get_task_reminders(task_id, user_tz, due_at_utc)
    if old_rem2:
        try:
            client.table("reminders").update({"status": "cancelled"}).eq("id", old_rem2["id"]).execute()
        except Exception as exc:
            logger.error("Error cancelling old 2nd reminder: %s", exc)

    db_user_uuid = task.get("user_id")
    try:
        client.table("reminders").insert({
            "task_id": task_id,
            "user_id": db_user_uuid,
            "remind_at": remind_at_utc.isoformat(),
            "status": "pending"
        }).execute()
        logger.info("Saved custom 2nd alert for task %s at %s", task_id, remind_at_utc)
    except Exception as exc:
        logger.error("Error inserting custom 2nd reminder: %s", exc)

    from keyboards import get_task_details_keyboard
    updated_task = get_task_by_id(task_id, user.id)
    await update.message.reply_text(
        f"✅ <b>2nd Alert Updated Successfully!</b>\n\n{format_task_detail_card(updated_task, user_tz)}",
        reply_markup=get_task_details_keyboard(task_id),
        parse_mode="HTML"
    )

    context.user_data.pop("edit_task_id", None)
    return ConversationHandler.END


async def handle_edit_cancellation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Safely abort current text input and load the details card."""
    if update.callback_query:
        try:
            await update.callback_query.answer()
        except Exception:
            pass
        task_id = context.user_data.get("edit_task_id") or update.callback_query.data.split(":")[-1]
    else:
        task_id = context.user_data.get("edit_task_id")

    context.user_data.pop("edit_task_id", None)

    if task_id:
        user = update.effective_user
        db_user = get_or_create_user(user)
        user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

        task = get_task_by_id(task_id, user.id)
        if task:
            from keyboards import get_task_details_keyboard
            markup = get_task_details_keyboard(task_id)
            card_text = format_task_detail_card(task, user_tz)
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    text=card_text,
                    reply_markup=markup,
                    parse_mode="HTML"
                )
            elif update.effective_message:
                await update.effective_message.reply_text(
                    text=card_text,
                    reply_markup=markup,
                    parse_mode="HTML"
                )

    return ConversationHandler.END


# ====================================================================
# HANDLER ROUTER EXPORT
# ====================================================================

def get_edit_task_handlers() -> list:
    """Return all callback handlers and the edit conversation handler."""
    
    # 1. Conversation Handler for text-based modifications
    edit_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_edit_title_conversation, pattern="^edit:field:title:[0-9a-fA-F\\-]+$"),
            CallbackQueryHandler(start_edit_date_conversation, pattern="^edit:save_date:custom:[0-9a-fA-F\\-]+$"),
            CallbackQueryHandler(start_edit_time_conversation, pattern="^edit:save_time:custom:[0-9a-fA-F\\-]+$"),
            CallbackQueryHandler(start_edit_rem1_conversation, pattern="^edit:save_rem1:custom:[0-9a-fA-F\\-]+$"),
            CallbackQueryHandler(start_edit_rem2_conversation, pattern="^edit:save_rem2:custom:[0-9a-fA-F\\-]+$")
        ],
        states={
            WAITING_EDIT_TITLE_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_title_text)
            ],
            WAITING_EDIT_DATE_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_date_text)
            ],
            WAITING_EDIT_TIME_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_time_text)
            ],
            WAITING_EDIT_REMIND1_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_rem1_text)
            ],
            WAITING_EDIT_REMIND2_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_rem2_text)
            ]
        },
        fallbacks=[
            CallbackQueryHandler(handle_edit_cancellation, pattern="^task:view:[0-9a-fA-F\\-]+$"),
            CommandHandler("cancel", handle_edit_cancellation),
            CommandHandler("start", handle_edit_cancellation)
        ],
        per_message=False
    )

    # 2. General CallbackQueryHandlers for direct inline updates
    callbacks = [
        CallbackQueryHandler(handle_complete_task_callback, pattern="^task:done:[0-9a-fA-F\\-]+$"),
        CallbackQueryHandler(handle_delete_request_callback, pattern="^task:delete:[0-9a-fA-F\\-]+$"),
        CallbackQueryHandler(handle_delete_confirm_callback, pattern="^task:del_confirm:[0-9a-fA-F\\-]+$"),
        
        CallbackQueryHandler(handle_edit_menu_callback, pattern="^task:edit:[0-9a-fA-F\\-]+$"),
        
        # Category sub-routines
        CallbackQueryHandler(handle_edit_cat_menu, pattern="^edit:field:cat:[0-9a-fA-F\\-]+$"),
        CallbackQueryHandler(handle_save_cat_callback, pattern="^edit:save_cat:(personal|work|school):[0-9a-fA-F\\-]+$"),
        
        # Priority sub-routines
        CallbackQueryHandler(handle_edit_priority_menu, pattern="^edit:field:priority:[0-9a-fA-F\\-]+$"),
        CallbackQueryHandler(handle_save_priority_callback, pattern="^edit:save_priority:(high|medium|low):[0-9a-fA-F\\-]+$"),
        
        # Repeat Rule sub-routines
        CallbackQueryHandler(handle_edit_repeat_menu, pattern="^edit:field:repeat:[0-9a-fA-F\\-]+$"),
        CallbackQueryHandler(handle_save_repeat_callback, pattern="^edit:save_repeat:(none|daily|weekdays|weekly|monthly):[0-9a-fA-F\\-]+$"),
        
        # Due Date sub-routines
        CallbackQueryHandler(handle_edit_date_menu, pattern="^edit:field:date:[0-9a-fA-F\\-]+$"),
        CallbackQueryHandler(handle_edit_date_menu, pattern="^task:resched:[0-9a-fA-F\\-]+$"),  # Direct reschedule alias
        CallbackQueryHandler(handle_save_preset_date_callback, pattern="^edit:save_date:(today|tomorrow|none):[0-9a-fA-F\\-]+$"),
        
        # Due Time sub-routines
        CallbackQueryHandler(handle_edit_time_menu, pattern="^edit:field:time:[0-9a-fA-F\\-]+$"),
        CallbackQueryHandler(handle_save_preset_time_callback, pattern="^edit:save_time:(?!custom)(.+):([0-9a-fA-F\\-]+)$"),

        # Reminder sub-routines
        CallbackQueryHandler(handle_edit_reminder_menu, pattern="^edit:field:reminder:[0-9a-fA-F\\-]+$"),
        CallbackQueryHandler(handle_edit_reminder_menu, pattern="^task:remind:[0-9a-fA-F\\-]+$"),  # Direct reminder alias
        CallbackQueryHandler(handle_edit_rem1_menu, pattern="^edit:menu:rem1:[0-9a-fA-F\\-]+$"),
        CallbackQueryHandler(handle_edit_rem2_menu, pattern="^edit:menu:rem2:[0-9a-fA-F\\-]+$"),
        CallbackQueryHandler(handle_save_rem1_callback, pattern="^edit:save_rem1:(none|\\d+):[0-9a-fA-F\\-]+$"),
        CallbackQueryHandler(handle_save_rem2_callback, pattern="^edit:save_rem2:(none|morning|afternoon|evening|duetime):[0-9a-fA-F\\-]+$"),
        CallbackQueryHandler(handle_clear_reminders_callback, pattern="^edit:save_remind:clear:[0-9a-fA-F\\-]+$"),
        CallbackQueryHandler(handle_save_reminder_callback, pattern="^edit:save_remind:(none|\\d+):[0-9a-fA-F\\-]+$")
    ]

    return [edit_conv_handler] + callbacks

