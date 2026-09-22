"""Conversation handler for task creation wizard in Todo-list by LDR.

Implements sequential steps (Title, Category, Due Date, Time, Priority, Reminder, Confirmation)
with full validation, flexible format parsers, back-navigation history, and safe cancellation.
"""

from __future__ import annotations

import logging
from datetime import datetime, date, time
from typing import Dict, Any, Optional, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

from services import get_or_create_user, create_task
from keyboards import get_main_menu_keyboard
from utils.security import authorized_only
from utils.dates import (
    parse_date_string,
    parse_time_string,
    local_to_utc,
    get_timezone
)
from utils.formatters import (
    get_category_display,
    get_priority_display
)

logger = logging.getLogger(__name__)

# State Enumeration
(
    WAITING_TASK_NAME,
    WAITING_CATEGORY,
    WAITING_DATE,
    WAITING_CUSTOM_DATE,
    WAITING_TIME,
    WAITING_CUSTOM_TIME,
    WAITING_PRIORITY,
    WAITING_REMINDER,
    WAITING_CONFIRMATION
) = range(9)


# ====================================================================
# HELPER FUNCTIONS & KEYBOARDS
# ====================================================================

def get_cancel_button() -> InlineKeyboardButton:
    """Return a standard Cancel button."""
    return InlineKeyboardButton("❌ Cancel", callback_data="add:cancel")


def get_back_button() -> InlineKeyboardButton:
    """Return a standard Back button."""
    return InlineKeyboardButton("🔙 Back", callback_data="add:back")


def push_history(context: ContextTypes.DEFAULT_TYPE, state: int) -> None:
    """Track conversation states to allow step-by-step back navigation."""
    if "history" not in context.user_data:
        context.user_data["history"] = []
    context.user_data["history"].append(state)


def pop_history(context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Retrieve previous state for back navigation."""
    if "history" in context.user_data and context.user_data["history"]:
        return context.user_data["history"].pop()
    return None


def format_draft_summary(draft: Dict[str, Any]) -> str:
    """Generate a clean, professional summary of the task draft for final confirmation."""
    title = draft.get("title", "Untitled")
    category = get_category_display(draft.get("category", "personal"))
    priority = get_priority_display(draft.get("priority", "medium"))
    
    due_date = draft.get("due_date")
    due_time = draft.get("due_time")
    
    if due_date:
        due_date_str = due_date.strftime("%d %B %Y")
        due_time_str = due_time.strftime("%I:%M %p").lstrip("0") if due_time else "No Time Set"
        due_display = f"{due_date_str} • {due_time_str}"
    else:
        due_display = "🚫 No Due Date"

    reminder_display = "🔕 No Reminder"
    if due_date:
        offset = draft.get("reminder_offset_minutes")
        if offset == 0:
            reminder_display = "🔔 At due time"
        elif offset == 10:
            reminder_display = "🔔 10 minutes before"
        elif offset == 30:
            reminder_display = "🔔 30 minutes before"
        elif offset == 60:
            reminder_display = "🔔 1 hour before"
        elif offset == 1440:
            reminder_display = "🔔 1 day before"

    summary = (
        "📝 <b>New Task Confirmation</b>\n\n"
        f"<b>Name:</b> {title}\n"
        f"📁 <b>Category:</b> {category}\n"
        f"📅 <b>Due:</b> {due_display}\n"
        f"🚩 <b>Priority:</b> {priority}\n"
        f"🔔 <b>Reminder:</b> {reminder_display}\n\n"
        "Would you like to save this task?"
    )
    return summary


# ====================================================================
# STATE TRANSITIONS / FLOW INITIALIZERS
# ====================================================================

@authorized_only
async def start_task_creation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Initialize the task creation conversation flow."""
    query = update.callback_query
    await query.answer()

    # Initialize empty task draft
    context.user_data["task_draft"] = {
        "title": None,
        "category": None,
        "due_date": None,
        "due_time": None,
        "priority": "medium",
        "reminder_offset_minutes": None
    }
    context.user_data["history"] = []

    # Check if a category was preselected
    data = query.data
    if data.startswith("add:cat:"):
        preselected_cat = data.split(":")[2]
        if preselected_cat in ["personal", "work", "school"]:
            context.user_data["task_draft"]["category"] = preselected_cat
            logger.info("Task creation started with preselected category: %s", preselected_cat)

    # Prompt user for Task Name
    prompt = (
        "➕ <b>Create New Task</b>\n\n"
        "Please enter your task name (e.g. <i>Prepare shipment report</i>):"
    )
    
    markup = InlineKeyboardMarkup([[get_cancel_button()]])
    await query.edit_message_text(text=prompt, reply_markup=markup, parse_mode="HTML")
    return WAITING_TASK_NAME


# ====================================================================
# STEP 1: TASK NAME HANDLER
# ====================================================================

async def handle_task_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store task title and transition to Category selection (or Date if preselected)."""
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("⚠️ Task name cannot be empty. Please enter a valid name:")
        return WAITING_TASK_NAME

    context.user_data["task_draft"]["title"] = text
    draft = context.user_data["task_draft"]

    # If category is preselected, skip the Category Selection state and head to Due Date directly
    if draft["category"]:
        push_history(context, WAITING_TASK_NAME)
        return await show_date_selection_menu(update.message.reply_text, context)

    push_history(context, WAITING_TASK_NAME)
    return await show_category_selection_menu(update.message.reply_text, context)


# ====================================================================
# STEP 2: CATEGORY SELECTION MENU
# ====================================================================

async def show_category_selection_menu(reply_func, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render category selection inline keyboard."""
    draft = context.user_data["task_draft"]
    text = f"📁 Select a category for:\n\n\"<b>{draft['title']}</b>\""
    
    keyboard = [
        [
            InlineKeyboardButton("👤 Personal", callback_data="add:set_cat:personal"),
            InlineKeyboardButton("💼 Work", callback_data="add:set_cat:work")
        ],
        [
            InlineKeyboardButton("🎓 School", callback_data="add:set_cat:school")
        ],
        [
            get_back_button(),
            get_cancel_button()
        ]
    ]
    await reply_func(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return WAITING_CATEGORY


async def handle_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store category choice and transition to Date selection."""
    query = update.callback_query
    await query.answer()

    category = query.data.split(":")[2]
    context.user_data["task_draft"]["category"] = category

    push_history(context, WAITING_CATEGORY)
    return await show_date_selection_menu(query.edit_message_text, context)


# ====================================================================
# STEP 3: DUE DATE SELECTION MENU
# ====================================================================

async def show_date_selection_menu(reply_or_edit_func, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render due date option buttons."""
    text = "📅 <b>When is this task due?</b>"
    
    keyboard = [
        [
            InlineKeyboardButton("Today", callback_data="add:set_date:today"),
            InlineKeyboardButton("Tomorrow", callback_data="add:set_date:tomorrow")
        ],
        [
            InlineKeyboardButton("📅 Choose Date", callback_data="add:set_date:custom"),
            InlineKeyboardButton("🚫 No Due Date", callback_data="add:set_date:none")
        ],
        [
            get_back_button(),
            get_cancel_button()
        ]
    ]
    await reply_or_edit_func(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return WAITING_DATE


async def handle_date_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store standard relative date choices, request custom date text, or skip directly to Priority."""
    query = update.callback_query
    await query.answer()

    choice = query.data.split(":")[2]
    user = update.effective_user
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")
    
    local_tz = get_timezone(user_tz)
    today_local = datetime.now(local_tz).date()

    if choice == "today":
        context.user_data["task_draft"]["due_date"] = today_local
        push_history(context, WAITING_DATE)
        return await show_time_selection_menu(query.edit_message_text, context)

    elif choice == "tomorrow":
        import datetime as dt_mod
        context.user_data["task_draft"]["due_date"] = today_local + dt_mod.timedelta(days=1)
        push_history(context, WAITING_DATE)
        return await show_time_selection_menu(query.edit_message_text, context)

    elif choice == "custom":
        push_history(context, WAITING_DATE)
        prompt = (
            "📅 <b>Custom Due Date</b>\n\n"
            "Please type a due date in <b>DD/MM/YYYY</b> format (e.g. <code>25/09/2026</code>):"
        )
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await query.edit_message_text(text=prompt, reply_markup=markup, parse_mode="HTML")
        return WAITING_CUSTOM_DATE

    elif choice == "none":
        # Clear date/time fields and skip directly to Priority (reminders require a due date)
        context.user_data["task_draft"]["due_date"] = None
        context.user_data["task_draft"]["due_time"] = None
        context.user_data["task_draft"]["reminder_offset_minutes"] = None
        push_history(context, WAITING_DATE)
        return await show_priority_selection_menu(query.edit_message_text, context)

    return WAITING_DATE


async def handle_custom_date_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parse and validate DD/MM/YYYY input string from user."""
    text = update.message.text.strip()
    parsed_date = parse_date_string(text)

    if not parsed_date:
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await update.message.reply_text(
            "⚠️ <b>Invalid Date format</b>\n\n"
            "Please ensure the date format is exactly <b>DD/MM/YYYY</b>, and is a valid future date (e.g., 25/09/2026):",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return WAITING_CUSTOM_DATE

    # Check to prevent past dates
    user = update.effective_user
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")
    local_tz = get_timezone(user_tz)
    today_local = datetime.now(local_tz).date()

    if parsed_date < today_local:
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await update.message.reply_text(
            "⚠️ <b>Past Date</b>\n\nDue date cannot be in the past. Please enter a valid future date:",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return WAITING_CUSTOM_DATE

    context.user_data["task_draft"]["due_date"] = parsed_date
    push_history(context, WAITING_CUSTOM_DATE)
    return await show_time_selection_menu(update.message.reply_text, context)


# ====================================================================
# STEP 4: TIME SELECTION MENU
# ====================================================================

async def show_time_selection_menu(reply_or_edit_func, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render standard time slots or custom options."""
    text = "⏰ <b>What time should this task be due?</b>"
    
    keyboard = [
        [
            InlineKeyboardButton("8:00 AM", callback_data="add:set_time:08:00 AM"),
            InlineKeyboardButton("9:00 AM", callback_data="add:set_time:09:00 AM")
        ],
        [
            InlineKeyboardButton("12:00 PM", callback_data="add:set_time:12:00 PM"),
            InlineKeyboardButton("3:00 PM", callback_data="add:set_time:03:00 PM")
        ],
        [
            InlineKeyboardButton("5:00 PM", callback_data="add:set_time:05:00 PM"),
            InlineKeyboardButton("7:00 PM", callback_data="add:set_time:07:00 PM")
        ],
        [
            InlineKeyboardButton("⌨️ Custom Time", callback_data="add:set_time:custom")
        ],
        [
            get_back_button(),
            get_cancel_button()
        ]
    ]
    await reply_or_edit_func(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return WAITING_TIME


async def handle_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store time choice or request custom time input."""
    query = update.callback_query
    await query.answer()

    choice = query.data.split(":")[2]

    if choice == "custom":
        push_history(context, WAITING_TIME)
        prompt = (
            "⌨️ <b>Custom Due Time</b>\n\n"
            "Please enter a time in HH:MM format or 12-hour format (e.g. <code>14:30</code> or <code>2:30 PM</code>):"
        )
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await query.edit_message_text(text=prompt, reply_markup=markup, parse_mode="HTML")
        return WAITING_CUSTOM_TIME

    # Parse selected preset standard time
    parsed_time = parse_time_string(choice)
    if not parsed_time:
        # Fallback safeguard
        parsed_time = time(9, 0)

    context.user_data["task_draft"]["due_time"] = parsed_time
    push_history(context, WAITING_TIME)
    return await show_priority_selection_menu(query.edit_message_text, context)


async def handle_custom_time_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parse custom time text input."""
    text = update.message.text.strip()
    parsed_time = parse_time_string(text)

    if not parsed_time:
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await update.message.reply_text(
            "⚠️ <b>Invalid Time format</b>\n\n"
            "Please ensure the format is valid (e.g. <code>14:30</code>, <code>2:30 PM</code>, or <code>9:00 AM</code>):",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return WAITING_CUSTOM_TIME

    context.user_data["task_draft"]["due_time"] = parsed_time
    push_history(context, WAITING_CUSTOM_TIME)
    return await show_priority_selection_menu(update.message.reply_text, context)


# ====================================================================
# STEP 5: PRIORITY SELECTION MENU
# ====================================================================

async def show_priority_selection_menu(reply_or_edit_func, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render Priority ratings."""
    text = "🚩 <b>Select Task Priority</b>"
    
    keyboard = [
        [
            InlineKeyboardButton("🔴 High", callback_data="add:set_priority:high")
        ],
        [
            InlineKeyboardButton("🟡 Medium", callback_data="add:set_priority:medium")
        ],
        [
            InlineKeyboardButton("🟢 Low", callback_data="add:set_priority:low")
        ],
        [
            get_back_button(),
            get_cancel_button()
        ]
    ]
    await reply_or_edit_func(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return WAITING_PRIORITY


async def handle_priority_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store priority rating and transition to Reminder scheduling (or confirmation if no due date)."""
    query = update.callback_query
    await query.answer()

    priority = query.data.split(":")[2]
    context.user_data["task_draft"]["priority"] = priority

    draft = context.user_data["task_draft"]
    push_history(context, WAITING_PRIORITY)

    # Reminders require a valid due date. If there is no due date, skip reminders entirely.
    if not draft["due_date"]:
        return await show_confirmation_screen(query.edit_message_text, context)

    return await show_reminder_selection_menu(query.edit_message_text, context)


# ====================================================================
# STEP 6: REMINDER SELECTION MENU
# ====================================================================

async def show_reminder_selection_menu(reply_or_edit_func, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render reminder offsets."""
    text = "🔔 <b>When should I remind you?</b>"
    
    keyboard = [
        [
            InlineKeyboardButton("At due time", callback_data="add:set_remind:0"),
            InlineKeyboardButton("10 minutes before", callback_data="add:set_remind:10")
        ],
        [
            InlineKeyboardButton("30 minutes before", callback_data="add:set_remind:30"),
            InlineKeyboardButton("1 hour before", callback_data="add:set_remind:60")
        ],
        [
            InlineKeyboardButton("1 day before", callback_data="add:set_remind:1440"),
            InlineKeyboardButton("🔕 No Reminder", callback_data="add:set_remind:none")
        ],
        [
            get_back_button(),
            get_cancel_button()
        ]
    ]
    await reply_or_edit_func(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return WAITING_REMINDER


async def handle_reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store reminder offset in minutes and show confirmation card."""
    query = update.callback_query
    await query.answer()

    choice = query.data.split(":")[2]
    
    if choice == "none":
        context.user_data["task_draft"]["reminder_offset_minutes"] = None
    else:
        context.user_data["task_draft"]["reminder_offset_minutes"] = int(choice)

    push_history(context, WAITING_REMINDER)
    return await show_confirmation_screen(query.edit_message_text, context)


# ====================================================================
# STEP 7: FINAL CONFIRMATION & SAVE
# ====================================================================

async def show_confirmation_screen(reply_or_edit_func, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render the final confirmation details card."""
    draft = context.user_data["task_draft"]
    text = format_draft_summary(draft)

    keyboard = [
        [
            InlineKeyboardButton("✅ Save Task", callback_data="add:save_task")
        ],
        [
            get_back_button(),
            get_cancel_button()
        ]
    ]
    await reply_or_edit_func(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return WAITING_CONFIRMATION


async def handle_save_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Commit the fully prepared task to Supabase and clean up state."""
    query = update.callback_query
    await query.answer()

    draft = context.user_data["task_draft"]
    user = update.effective_user
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    # Construct the localized due_at datetime for conversion to UTC
    due_at_utc = None
    if draft["due_date"]:
        # Fallback to 9:00 AM if date selected but no specific time selected
        due_time = draft["due_time"] or time(9, 0)
        naive_local_dt = datetime.combine(draft["due_date"], due_time)
        due_at_utc = local_to_utc(naive_local_dt, user_tz)

    # Commit task to Supabase
    saved_task = create_task(
        telegram_user_id=user.id,
        title=draft["title"],
        category=draft["category"],
        priority=draft["priority"],
        due_at=due_at_utc,
        repeat_rule="none", # Single-shot initially
        description=None
    )

    if not saved_task:
        await query.edit_message_text(
            "⚠️ <b>Failed to Save</b>\n\nCould not commit task to the database. Please try again later.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML"
        )
        return ConversationHandler.END

    # If reminder is configured, schedule it
    task_id = saved_task.get("id")
    offset = draft.get("reminder_offset_minutes")
    
    if due_at_utc and offset is not None:
        try:
            from datetime import timedelta
            remind_at_utc = due_at_utc - timedelta(minutes=offset)
            
            # Save reminder entry to Supabase
            client = get_supabase_client()
            db_user_uuid = saved_task.get("user_id")
            
            reminder_data = {
                "task_id": task_id,
                "user_id": db_user_uuid,
                "remind_at": remind_at_utc.isoformat(),
                "status": "pending"
            }
            client.table("reminders").insert(reminder_data).execute()
            logger.info("Inserted reminder for task %s to trigger at %s", task_id, remind_at_utc)
            
            # NOTE: Reminders will be picked up by the upcoming Phase 5 Scheduler Restoration.
        except Exception as exc:
            logger.error("Error setting reminder entry: %s", exc)

    success_text = (
        "✅ <b>Task Created Successfully!</b>\n\n"
        f"📝 <b>{draft['title']}</b> has been added under your <b>{draft['category'].capitalize()}</b> list."
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📋 Show Tasks", callback_data="menu:tasks"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu:main")
        ]
    ]
    
    await query.edit_message_text(text=success_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    
    # Flush memory cache
    context.user_data.pop("task_draft", None)
    context.user_data.pop("history", None)
    return ConversationHandler.END


# ====================================================================
# GLOBAL ACTIONS: BACK, CANCEL & FALLBACKS
# ====================================================================

async def handle_back_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Traverse backward through the conversation history tree."""
    query = update.callback_query
    await query.answer()

    prev_state = pop_history(context)
    if prev_state is None:
        # No history left; safety fallback to cancelling
        return await handle_cancellation(update, context)

    logger.info("Navigating back to state index: %s", prev_state)

    if prev_state == WAITING_TASK_NAME:
        context.user_data["task_draft"]["title"] = None
        prompt = "Please enter your task name (e.g. <i>Prepare shipment report</i>):"
        await query.edit_message_text(text=prompt, reply_markup=InlineKeyboardMarkup([[get_cancel_button()]]), parse_mode="HTML")
        return WAITING_TASK_NAME

    elif prev_state == WAITING_CATEGORY:
        context.user_data["task_draft"]["category"] = None
        return await show_category_selection_menu(query.edit_message_text, context)

    elif prev_state == WAITING_DATE:
        context.user_data["task_draft"]["due_date"] = None
        return await show_date_selection_menu(query.edit_message_text, context)

    elif prev_state == WAITING_CUSTOM_DATE:
        prompt = "Please type a due date in <b>DD/MM/YYYY</b> format (e.g. <code>25/09/2026</code>):"
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await query.edit_message_text(text=prompt, reply_markup=markup, parse_mode="HTML")
        return WAITING_CUSTOM_DATE

    elif prev_state == WAITING_TIME:
        context.user_data["task_draft"]["due_time"] = None
        return await show_time_selection_menu(query.edit_message_text, context)

    elif prev_state == WAITING_CUSTOM_TIME:
        prompt = "Please enter a time in HH:MM format or 12-hour format (e.g. <code>14:30</code> or <code>2:30 PM</code>):"
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await query.edit_message_text(text=prompt, reply_markup=markup, parse_mode="HTML")
        return WAITING_CUSTOM_TIME

    elif prev_state == WAITING_PRIORITY:
        context.user_data["task_draft"]["priority"] = "medium"
        return await show_priority_selection_menu(query.edit_message_text, context)

    elif prev_state == WAITING_REMINDER:
        context.user_data["task_draft"]["reminder_offset_minutes"] = None
        return await show_reminder_selection_menu(query.edit_message_text, context)

    return ConversationHandler.END


async def handle_cancellation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Abort task draft instantly, discard caches, and return to Main Menu."""
    # Works for both text messages and callback queries
    if update.callback_query:
        query = update.callback_query
        await query.answer("Draft cancelled.")
        edit_func = query.edit_message_text
    else:
        edit_func = update.message.reply_text

    # Clear caches
    context.user_data.pop("task_draft", None)
    context.user_data.pop("history", None)

    await edit_func(
        "❌ <b>Creation Aborted.</b>\n\nReturned to the main menu.",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML"
    )
    return ConversationHandler.END


# ====================================================================
# CONVERSATION DISPATCHER EXPORT
# ====================================================================

def get_create_task_handler() -> ConversationHandler:
    """Return the complete state-machine ConversationHandler for task creation."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_task_creation, pattern="^add:(start|cat:(personal|work|school|all))$")
        ],
        states={
            WAITING_TASK_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_task_name)
            ],
            WAITING_CATEGORY: [
                CallbackQueryHandler(handle_category_callback, pattern="^add:set_cat:(personal|work|school)$")
            ],
            WAITING_DATE: [
                CallbackQueryHandler(handle_date_callback, pattern="^add:set_date:(today|tomorrow|custom|none)$")
            ],
            WAITING_CUSTOM_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_date_text)
            ],
            WAITING_TIME: [
                CallbackQueryHandler(handle_time_callback, pattern="^add:set_time:(custom|\\d{2}:\\d{2} (AM|PM))$")
            ],
            WAITING_CUSTOM_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_time_text)
            ],
            WAITING_PRIORITY: [
                CallbackQueryHandler(handle_priority_callback, pattern="^add:set_priority:(high|medium|low)$")
            ],
            WAITING_REMINDER: [
                CallbackQueryHandler(handle_reminder_callback, pattern="^add:set_remind:(none|\\d+)$")
            ],
            WAITING_CONFIRMATION: [
                CallbackQueryHandler(handle_save_task, pattern="^add:save_task$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(handle_back_navigation, pattern="^add:back$"),
            CallbackQueryHandler(handle_cancellation, pattern="^add:cancel$"),
            CommandHandler("cancel", handle_cancellation)
        ],
        per_message=True
    )
