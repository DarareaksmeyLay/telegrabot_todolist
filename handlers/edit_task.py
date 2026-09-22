"""Conversation and Callback handlers for editing, completing, deleting, and rescheduling tasks in Todo-list by LDR.

Provides rich edit submenus (Title, Category, Due Date, Due Time, Priority, Reminder, Repeat)
with full validations and safe back-navigation.
"""

from __future__ import annotations

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
    get_timezone
)
from utils.formatters import (
    get_category_display,
    get_priority_display,
    format_task_detail_card
)

logger = logging.getLogger(__name__)

# Conversation States
(
    WAITING_EDIT_TITLE_TEXT,
    WAITING_EDIT_DATE_TEXT,
    WAITING_EDIT_TIME_TEXT
) = range(3)


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

    task_id = query.data.split(":")[2]
    user = update.effective_user

    completed_task = complete_task_by_id(task_id, user.id)
    if not completed_task:
        await query.edit_message_text(
            "⚠️ <b>Error</b>\n\nCould not mark task as completed or you do not have permission.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="menu:main")]]),
            parse_mode="HTML"
        )
        return

    title = completed_task.get("title", "Untitled")
    success_text = (
        f"✅ <b>Task Completed!</b>\n\n"
        f"🎉 Great job completing:\n\"<b>{title}</b>\"\n\n"
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

    task_id = query.data.split(":")[2]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task:
        await query.edit_message_text("⚠️ Task not found.", parse_mode="HTML")
        return

    title = task.get("title", "Untitled")
    prompt = (
        "⚠️ <b>Delete Task?</b>\n\n"
        f"Are you sure you want to delete \"<b>{title}</b>\"?\n"
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

    task_id = query.data.split(":")[2]
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
# 2. MAIN EDIT MENU
# ====================================================================

async def handle_edit_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display edit dashboard options for the selected task."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[2]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task:
        await query.edit_message_text("⚠️ Task not found.", parse_mode="HTML")
        return

    title = task.get("title", "Untitled")
    category = get_category_display(task.get("category", "personal"))
    priority = get_priority_display(task.get("priority", "medium"))
    repeat_rule = task.get("repeat_rule", "none").capitalize()

    text = (
        "✏️ <b>Edit Task Details</b>\n\n"
        f"<b>Title:</b> {title}\n"
        f"📁 <b>Category:</b> {category}\n"
        f"🚩 <b>Priority:</b> {priority}\n"
        f"🔁 <b>Repeat:</b> {repeat_rule}\n\n"
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
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


# ====================================================================
# 3. FIELD SUBMENUS & INLINE WRITES
# ====================================================================

async def handle_edit_cat_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render Category edit choices."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[3]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task:
        return

    text = f"📁 <b>Edit Category</b> for:\n\"{task.get('title')}\"\n\nChoose a category:"
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
    task_id = parts[3]
    user = update.effective_user

    update_task(task_id, user.id, {"category": category})
    await handle_edit_menu_callback(update, context)


async def handle_edit_priority_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render Priority edit choices."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[3]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task:
        return

    text = f"🚩 <b>Edit Priority</b> for:\n\"{task.get('title')}\"\n\nSelect Priority rating:"
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
    task_id = parts[3]
    user = update.effective_user

    update_task(task_id, user.id, {"priority": priority})
    await handle_edit_menu_callback(update, context)


async def handle_edit_repeat_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render Repeat Rule edit choices."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[3]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task:
        return

    text = f"🔁 <b>Edit Repeat Rule</b> for:\n\"{task.get('title')}\"\n\nChoose recurrences:"
    keyboard = [
        [
            InlineKeyboardButton("🚫 Do Not Repeat", callback_data=f"edit:save_repeat:none:{task_id}")
        ],
        [
            InlineKeyboardButton("📅 Daily", callback_data=f"edit:save_repeat:daily:{task_id}"),
            InlineKeyboardButton("📅 Weekly", callback_data=f"edit:save_repeat:weekly:{task_id}")
        ],
        [
            InlineKeyboardButton("📅 Monthly", callback_data=f"edit:save_repeat:monthly:{task_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=f"task:edit:{task_id}")
        ]
    ]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def handle_save_repeat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commit Repeat rule change directly and return to edit menu."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    repeat = parts[2]
    task_id = parts[3]
    user = update.effective_user

    update_task(task_id, user.id, {"repeat_rule": repeat})
    await handle_edit_menu_callback(update, context)


async def handle_edit_date_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render Date reschedule choices."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[3]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task:
        return

    text = f"📅 <b>Reschedule Due Date</b> for:\n\"{task.get('title')}\""
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
            InlineKeyboardButton("🔙 Back", callback_data=f"task:edit:{task_id}")
        ]
    ]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def handle_save_preset_date_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commit Preset Date choice, updating task due_at and shifting any associated reminders."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    choice = parts[2]
    task_id = parts[3]
    user = update.effective_user

    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")
    local_tz = get_timezone(user_tz)
    today_local = datetime.now(local_tz).date()

    task = get_task_by_id(task_id, user.id)
    if not task:
        return

    # Keep original due_time if preset (else default to 9:00 AM)
    orig_due_at = task.get("due_at")
    if orig_due_at:
        try:
            clean_str = orig_due_at.replace("Z", "+00:00")
            orig_dt = datetime.fromisoformat(clean_str)
            # convert UTC to local to extract time correctly
            import pytz
            local_dt = orig_dt.astimezone(local_tz)
            orig_time = local_dt.time()
        except Exception:
            orig_time = time(9, 0)
    else:
        orig_time = time(9, 0)

    if choice == "none":
        # Remove due date
        update_task(task_id, user.id, {"due_at": None})
        # Reminders require due_at, cancel any associated pending reminders
        try:
            client = get_supabase_client()
            client.table("reminders").update({"status": "cancelled"}).eq("task_id", task_id).eq("status", "pending").execute()
        except Exception as exc:
            logger.error("Error cancelling reminders on remove due date: %s", exc)
        await handle_edit_menu_callback(update, context)
        return

    elif choice == "today":
        target_date = today_local
    elif choice == "tomorrow":
        target_date = today_local + timedelta(days=1)
    else:
        return

    naive_local_dt = datetime.combine(target_date, orig_time)
    due_at_utc = local_to_utc(naive_local_dt, user_tz)

    update_task(task_id, user.id, {"due_at": due_at_utc.isoformat()})
    
    # Parse original due_at for reminder recalculation offset
    old_due_at_utc = None
    if orig_due_at:
        try:
            clean_str = orig_due_at.replace("Z", "+00:00")
            old_due_at_utc = datetime.fromisoformat(clean_str)
        except Exception:
            pass

    # Recalculate and update any pending reminders
    await recalculate_reminders_for_task(task_id, due_at_utc, old_due_at_utc)
    
    await handle_edit_menu_callback(update, context)


async def handle_edit_time_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render Time reschedule choices."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[3]
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

    text = f"⏰ <b>Reschedule Due Time</b> for:\n\"{task.get('title')}\""
    keyboard = [
        [
            InlineKeyboardButton("8:00 AM", callback_data=f"edit:save_time:08:00 AM:{task_id}"),
            InlineKeyboardButton("9:00 AM", callback_data=f"edit:save_time:09:00 AM:{task_id}")
        ],
        [
            InlineKeyboardButton("12:00 PM", callback_data=f"edit:save_time:12:00 PM:{task_id}"),
            InlineKeyboardButton("3:00 PM", callback_data=f"edit:save_time:03:00 PM:{task_id}")
        ],
        [
            InlineKeyboardButton("5:00 PM", callback_data=f"edit:save_time:05:00 PM:{task_id}"),
            InlineKeyboardButton("7:00 PM", callback_data=f"edit:save_time:07:00 PM:{task_id}")
        ],
        [
            InlineKeyboardButton("⌨️ Custom Time", callback_data=f"edit:save_time:custom:{task_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=f"task:edit:{task_id}")
        ]
    ]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def handle_save_preset_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commit Preset Time choice, reassembling due_at and rescheduling reminders."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    time_str = parts[2]
    task_id = parts[3]
    user = update.effective_user

    parsed_time = parse_time_string(time_str) or time(9, 0)
    await commit_time_change(task_id, user.id, parsed_time)
    await handle_edit_menu_callback(update, context)


async def handle_edit_reminder_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render Reminder options."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[3]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task:
        return

    if not task.get("due_at"):
        await query.edit_message_text(
            "⚠️ <b>Due Date Required</b>\n\nYou must set a Due Date before scheduling reminders.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📅 Set Due Date", callback_data=f"edit:field:date:{task_id}")]]) ,
            parse_mode="HTML"
        )
        return

    text = f"🔔 <b>Configure Reminder</b> for:\n\"{task.get('title')}\""
    keyboard = [
        [
            InlineKeyboardButton("At due time", callback_data=f"edit:save_remind:0:{task_id}"),
            InlineKeyboardButton("10 minutes before", callback_data=f"edit:save_remind:10:{task_id}")
        ],
        [
            InlineKeyboardButton("30 minutes before", callback_data=f"edit:save_remind:30:{task_id}"),
            InlineKeyboardButton("1 hour before", callback_data=f"edit:save_remind:60:{task_id}")
        ],
        [
            InlineKeyboardButton("1 day before", callback_data=f"edit:save_remind:1440:{task_id}"),
            InlineKeyboardButton("🔕 No Reminder", callback_data=f"edit:save_remind:none:{task_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back to Edit Menu", callback_data=f"task:edit:{task_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"task:view:{task_id}")
        ]
    ]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def handle_save_reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commit or update reminder entries in database."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    offset_str = parts[2]
    task_id = parts[3]
    user = update.effective_user

    task = get_task_by_id(task_id, user.id)
    if not task or not task.get("due_at"):
        return

    client = get_supabase_client()

    # Cancel previous pending reminders for this task
    try:
        client.table("reminders").update({"status": "cancelled"}).eq("task_id", task_id).eq("status", "pending").execute()
    except Exception as exc:
        logger.error("Error clearing old reminders: %s", exc)

    if offset_str != "none":
        offset_minutes = int(offset_str)
        due_at_str = task.get("due_at").replace("Z", "+00:00")
        due_at_utc = datetime.fromisoformat(due_at_str)
        remind_at_utc = due_at_utc - timedelta(minutes=offset_minutes)

        # Retrieve user UUID in Supabase
        db_user = get_or_create_user(user)
        db_user_uuid = task.get("user_id")

        try:
            client.table("reminders").insert({
                "task_id": task_id,
                "user_id": db_user_uuid,
                "remind_at": remind_at_utc.isoformat(),
                "status": "pending"
            }).execute()
            logger.info("Saved reminder for task %s to trigger at %s", task_id, remind_at_utc)
        except Exception as exc:
            logger.error("Error inserting reminder on edit: %s", exc)

    await handle_edit_menu_callback(update, context)


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

    update_task(task_id, telegram_user_id, {"due_at": new_utc_dt.isoformat()})
    await recalculate_reminders_for_task(task_id, new_utc_dt, due_dt_utc)


async def recalculate_reminders_for_task(
    task_id: str,
    due_at_utc: datetime,
    old_due_at_utc: Optional[datetime] = None
) -> None:
    """Sync any active pending reminders with the newly updated task due date/time."""
    client = get_supabase_client()
    try:
        # Check if there is an active pending reminder for this task
        rem_res = client.table("reminders").select("*").eq("task_id", task_id).eq("status", "pending").execute()
        if not rem_res.data:
            return

        for reminder in rem_res.data:
            remind_at_str = reminder.get("remind_at").replace("Z", "+00:00")
            remind_at_dt = datetime.fromisoformat(remind_at_str)

            # Calculate offset (default to 0 minutes if old_due_at_utc is not provided)
            offset = timedelta(0)
            if old_due_at_utc:
                # Ensure both are offset-aware or both naive
                if old_due_at_utc.tzinfo and not remind_at_dt.tzinfo:
                    remind_at_dt = remind_at_dt.replace(tzinfo=old_due_at_utc.tzinfo)
                elif not old_due_at_utc.tzinfo and remind_at_dt.tzinfo:
                    old_due_at_utc = old_due_at_utc.replace(tzinfo=remind_at_dt.tzinfo)
                offset = old_due_at_utc - remind_at_dt

            # Apply same offset to new due_at_utc
            new_remind_at = due_at_utc - offset

            # Update reminder time
            client.table("reminders").update({
                "remind_at": new_remind_at.isoformat()
            }).eq("id", reminder["id"]).execute()
            logger.info("Recalculated reminder %s to trigger at %s", reminder["id"], new_remind_at)

    except Exception as exc:
        logger.error("Error recalculating reminder: %s", exc)


# ====================================================================
# CONVERSATION STEPS: TEXT INPUT & WRITES
# ====================================================================

async def start_edit_title_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to write a new task name."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[3]
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
        
        # Display success and load updated details card
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

    task_id = query.data.split(":")[3]
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

    # Prevent past dates
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
            # Reconstruct due_at using original due_time if preset
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

            update_task(task_id, user.id, {"due_at": due_at_utc.isoformat()})
            await recalculate_reminders_for_task(task_id, due_at_utc)

            # Show details card
            updated_task = get_task_by_id(task_id, user.id)
            from keyboards import get_task_details_keyboard
            await update.message.reply_text(
                f"✅ <b>Due Date Updated Successfully!</b>\n\n{format_task_detail_card(updated_task, user_tz)}",
                reply_markup=get_task_details_keyboard(task_id),
                parse_mode="HTML"
            )

    context.user_data.pop("edit_task_id", None)
    return ConversationHandler.END


async def start_edit_time_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to write a custom due time."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split(":")[3]
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

        # Show details
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


async def handle_edit_cancellation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Safely abort current text input and load the details card."""
    query = update.callback_query
    await query.answer()

    task_id = context.user_data.get("edit_task_id") or query.data.split(":")[2]
    context.user_data.pop("edit_task_id", None)

    user = update.effective_user
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    task = get_task_by_id(task_id, user.id)
    if task:
        from keyboards import get_task_details_keyboard
        await query.edit_message_text(
            text=format_task_detail_card(task, user_tz),
            reply_markup=get_task_details_keyboard(task_id),
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
            CallbackQueryHandler(start_edit_time_conversation, pattern="^edit:save_time:custom:[0-9a-fA-F\\-]+$")
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
        CallbackQueryHandler(handle_save_repeat_callback, pattern="^edit:save_repeat:(none|daily|weekly|monthly):[0-9a-fA-F\\-]+$"),
        
        # Due Date sub-routines
        CallbackQueryHandler(handle_edit_date_menu, pattern="^edit:field:date:[0-9a-fA-F\\-]+$"),
        CallbackQueryHandler(handle_edit_date_menu, pattern="^task:resched:[0-9a-fA-F\\-]+$"), # Direct reschedule alias
        CallbackQueryHandler(handle_save_preset_date_callback, pattern="^edit:save_date:(today|tomorrow|none):[0-9a-fA-F\\-]+$"),
        
        # Due Time sub-routines
        CallbackQueryHandler(handle_edit_time_menu, pattern="^edit:field:time:[0-9a-fA-F\\-]+$"),
        CallbackQueryHandler(handle_save_preset_time_callback, pattern="^edit:save_time:\\d{2}:\\d{2} (AM|PM):[0-9a-fA-F\\-]+$"),

        # Reminder sub-routines
        CallbackQueryHandler(handle_edit_reminder_menu, pattern="^edit:field:reminder:[0-9a-fA-F\\-]+$"),
        CallbackQueryHandler(handle_edit_reminder_menu, pattern="^task:remind:[0-9a-fA-F\\-]+$"), # Direct reminder alias
        CallbackQueryHandler(handle_save_reminder_callback, pattern="^edit:save_remind:(none|\\d+):[0-9a-fA-F\\-]+$")
    ]

    return [edit_conv_handler] + callbacks
