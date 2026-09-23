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

from database import get_supabase_client
from services import get_or_create_user, create_task
from keyboards import get_main_menu_keyboard
from utils.security import authorized_only
from utils.dates import (
    parse_date_string,
    parse_time_string,
    local_to_utc,
    get_timezone,
    parse_advance_alert_input,
    format_reminder_label
)
from utils.formatters import (
    get_category_display,
    get_priority_display
)

logger = logging.getLogger(__name__)

# State Enumeration for Dual-Alert Task Creation Wizard
(
    WAITING_TASK_NAME,
    WAITING_CATEGORY,
    WAITING_DATE,
    WAITING_CUSTOM_DATE,
    WAITING_TIME,
    WAITING_CUSTOM_TIME,
    WAITING_PRIORITY,
    WAITING_FIRST_REMINDER,
    WAITING_CUSTOM_FIRST_REMINDER,
    WAITING_SECOND_REMINDER,
    WAITING_CUSTOM_SECOND_REMINDER,
    WAITING_CONFIRMATION
) = range(12)



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
        due_time_str = due_time.strftime("%I:%M %p").lstrip("0") if due_time else "9:00 AM (Default)"
        due_display = f"{due_date_str} • {due_time_str}"
    else:
        due_display = "🚫 No Due Date"

    rem1_label = draft.get("reminder_1_label") or "🔕 None"
    rem2_label = draft.get("reminder_2_label") or "🔕 None"

    summary = (
        "📝 <b>New Task Confirmation</b>\n\n"
        f"<b>Name:</b> {title}\n"
        f"📁 <b>Category:</b> {category}\n"
        f"📅 <b>Due:</b> {due_display}\n"
        f"🚩 <b>Priority:</b> {priority}\n"
        f"🔔 <b>1st Alert (Advance):</b> {rem1_label}\n"
        f"🔔 <b>2nd Alert (Due Date):</b> {rem2_label}\n\n"
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
        "reminder_1": None,
        "reminder_1_label": None,
        "reminder_2": None,
        "reminder_2_label": None,
        "menu_message_id": query.message.message_id if query and query.message else None
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
    
    # Clean up the user's input message to keep chat tidy
    try:
        await update.message.delete()
    except Exception as exc:
        logger.debug("Failed to delete user message: %s", exc)

    if not text:
        return WAITING_TASK_NAME

    context.user_data["task_draft"]["title"] = text
    draft = context.user_data["task_draft"]
    menu_msg_id = draft.get("menu_message_id")

    async def edit_or_reply(text, reply_markup=None, parse_mode=None):
        if menu_msg_id:
            try:
                return await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=menu_msg_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            except Exception as exc:
                logger.debug("Failed to edit menu message: %s", exc)
        return await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)

    push_history(context, WAITING_TASK_NAME)

    # If category is preselected, skip the Category Selection state and head to Due Date directly
    if draft["category"]:
        return await show_date_selection_menu(edit_or_reply, context)

    return await show_category_selection_menu(edit_or_reply, context)


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
    
    # Delete user's text input to keep chat tidy
    try:
        await update.message.delete()
    except Exception as exc:
        logger.debug("Failed to delete user message: %s", exc)

    draft = context.user_data["task_draft"]
    menu_msg_id = draft.get("menu_message_id")

    async def edit_or_reply(text, reply_markup=None, parse_mode=None):
        if menu_msg_id:
            try:
                return await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=menu_msg_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            except Exception as exc:
                logger.debug("Failed to edit menu message: %s", exc)
        return await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)

    parsed_date = parse_date_string(text)

    if not parsed_date:
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await edit_or_reply(
            text="⚠️ <b>Invalid Date format</b>\n\n"
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
        await edit_or_reply(
            text="⚠️ <b>Past Date</b>\n\nDue date cannot be in the past. Please enter a valid future date:",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return WAITING_CUSTOM_DATE

    context.user_data["task_draft"]["due_date"] = parsed_date
    push_history(context, WAITING_CUSTOM_DATE)
    return await show_time_selection_menu(edit_or_reply, context)


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
    
    # Delete user's text input to keep chat tidy
    try:
        await update.message.delete()
    except Exception as exc:
        logger.debug("Failed to delete user message: %s", exc)

    draft = context.user_data["task_draft"]
    menu_msg_id = draft.get("menu_message_id")

    async def edit_or_reply(text, reply_markup=None, parse_mode=None):
        if menu_msg_id:
            try:
                return await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=menu_msg_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            except Exception as exc:
                logger.debug("Failed to edit menu message: %s", exc)
        return await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)

    parsed_time = parse_time_string(text)

    if not parsed_time:
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await edit_or_reply(
            text="⚠️ <b>Invalid Time format</b>\n\n"
                 "Please ensure the format is valid (e.g. <code>14:30</code>, <code>2:30 PM</code>, or <code>9:00 AM</code>):",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return WAITING_CUSTOM_TIME

    context.user_data["task_draft"]["due_time"] = parsed_time
    push_history(context, WAITING_CUSTOM_TIME)
    return await show_priority_selection_menu(edit_or_reply, context)


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
    """Store priority rating and transition to First Alert scheduling (or confirmation if no due date)."""
    query = update.callback_query
    await query.answer()

    priority = query.data.split(":")[2]
    context.user_data["task_draft"]["priority"] = priority

    draft = context.user_data["task_draft"]
    push_history(context, WAITING_PRIORITY)

    # Reminders require a valid due date. If there is no due date, skip reminders entirely.
    if not draft["due_date"]:
        return await show_confirmation_screen(query.edit_message_text, context)

    return await show_first_reminder_menu(query.edit_message_text, context)


# ====================================================================
# STEP 6A: FIRST ALERT SELECTION MENU (ADVANCE REMINDER)
# ====================================================================

async def show_first_reminder_menu(reply_or_edit_func, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render First Alert options: 1-4 days, 1 week, custom advance alert, or skip."""
    draft = context.user_data["task_draft"]
    due_d = draft.get("due_date")
    due_t = draft.get("due_time") or time(9, 0)
    due_str = f"{due_d.strftime('%d %b %Y')} at {due_t.strftime('%I:%M %p').lstrip('0')}" if due_d else ""

    text = (
        "🔔 <b>Step 1 of 2: First Alert (Advance Reminder)</b>\n"
        "────────────────────\n"
        f"📅 Task Due: <b>{due_str}</b>\n\n"
        "Choose an advance alert before your task is due:"
    )

    keyboard = [
        [
            InlineKeyboardButton("1 day before", callback_data="add:set_remind1:1440"),
            InlineKeyboardButton("2 days before", callback_data="add:set_remind1:2880")
        ],
        [
            InlineKeyboardButton("3 days before", callback_data="add:set_remind1:4320"),
            InlineKeyboardButton("4 days before", callback_data="add:set_remind1:5760")
        ],
        [
            InlineKeyboardButton("1 week before", callback_data="add:set_remind1:10080"),
            InlineKeyboardButton("1 hour before", callback_data="add:set_remind1:60")
        ],
        [
            InlineKeyboardButton("⌨️ Custom Advance Alert", callback_data="add:set_remind1:custom"),
            InlineKeyboardButton("🔕 Skip 1st Alert", callback_data="add:set_remind1:none")
        ],
        [
            get_back_button(),
            get_cancel_button()
        ]
    ]
    await reply_or_edit_func(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return WAITING_FIRST_REMINDER


async def handle_first_reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process First Alert choice and proceed to Second Alert."""
    query = update.callback_query
    await query.answer()

    choice = query.data.split(":")[2]
    draft = context.user_data["task_draft"]

    if choice == "none":
        draft["reminder_1"] = None
        draft["reminder_1_label"] = "🔕 None"
        push_history(context, WAITING_FIRST_REMINDER)
        return await show_second_reminder_menu(query.edit_message_text, context)

    if choice == "custom":
        push_history(context, WAITING_FIRST_REMINDER)
        prompt = (
            "⌨️ <b>Custom First Alert (Advance Reminder)</b>\n\n"
            "Type how long before your task is due (e.g. <code>2 days</code>, <code>3d</code>, <code>5 days</code>, <code>12 hours</code>, <code>30 mins</code>)\n"
            "or enter a specific date/time (e.g. <code>24/09/2026 09:00 AM</code>):"
        )
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await query.edit_message_text(text=prompt, reply_markup=markup, parse_mode="HTML")
        return WAITING_CUSTOM_FIRST_REMINDER

    # Preset minutes calculation
    offset_minutes = int(choice)
    user = update.effective_user
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    due_time = draft["due_time"] or time(9, 0)
    naive_due = datetime.combine(draft["due_date"], due_time)
    due_at_utc = local_to_utc(naive_due, user_tz)

    from datetime import timedelta, timezone
    remind_at_utc = due_at_utc - timedelta(minutes=offset_minutes)

    if remind_at_utc <= datetime.now(timezone.utc):
        await query.answer("⚠️ This alert time has already passed! Please select another option or skip.", show_alert=True)
        return WAITING_FIRST_REMINDER

    draft["reminder_1"] = remind_at_utc.isoformat()
    draft["reminder_1_label"] = format_reminder_label(remind_at_utc, due_at_utc, user_tz)

    push_history(context, WAITING_FIRST_REMINDER)
    return await show_second_reminder_menu(query.edit_message_text, context)


async def handle_custom_first_reminder_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parse custom advance alert text and proceed to Second Alert."""
    text = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass

    draft = context.user_data["task_draft"]
    menu_msg_id = draft.get("menu_message_id")

    async def edit_or_reply(txt, reply_markup=None, parse_mode=None):
        if menu_msg_id:
            try:
                return await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=menu_msg_id,
                    text=txt,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            except Exception:
                pass
        return await update.message.reply_text(text=txt, reply_markup=reply_markup, parse_mode=parse_mode)

    user = update.effective_user
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    due_time = draft["due_time"] or time(9, 0)
    naive_due = datetime.combine(draft["due_date"], due_time)
    due_at_utc = local_to_utc(naive_due, user_tz)

    parsed_local_dt = parse_advance_alert_input(text, naive_due)
    if not parsed_local_dt:
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await edit_or_reply(
            txt="⚠️ <b>Invalid Alert Format</b>\n\n"
                "Please enter a valid format such as:\n"
                "• Relative: <code>2 days</code>, <code>3d</code>, <code>1 week</code>, <code>12 hours</code>\n"
                "• Date & Time: <code>24/09/2026 09:00 AM</code>",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return WAITING_CUSTOM_FIRST_REMINDER

    remind_at_utc = local_to_utc(parsed_local_dt, user_tz)
    from datetime import timezone
    now_utc = datetime.now(timezone.utc)

    if remind_at_utc >= due_at_utc:
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await edit_or_reply(
            txt="⚠️ <b>Alert Must Be Before Due Time</b>\n\n"
                "The 1st alert is an advance reminder and must be set before your task's due date and time. Please try again:",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return WAITING_CUSTOM_FIRST_REMINDER

    if remind_at_utc <= now_utc:
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await edit_or_reply(
            txt="⚠️ <b>Past Alert Time</b>\n\n"
                "This alert time has already passed. Please enter a future time before your task is due:",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return WAITING_CUSTOM_FIRST_REMINDER

    draft["reminder_1"] = remind_at_utc.isoformat()
    draft["reminder_1_label"] = format_reminder_label(remind_at_utc, due_at_utc, user_tz)

    push_history(context, WAITING_CUSTOM_FIRST_REMINDER)
    return await show_second_reminder_menu(edit_or_reply, context)


# ====================================================================
# STEP 6B: SECOND ALERT SELECTION MENU (DUE DATE REMINDER)
# ====================================================================

async def show_second_reminder_menu(reply_or_edit_func, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render Second Alert options on the due date: Morning, Afternoon, Evening, Due Time, Custom, or skip."""
    draft = context.user_data["task_draft"]
    due_d = draft.get("due_date")
    due_d_str = due_d.strftime("%d %B %Y") if due_d else "Due Date"
    due_t = draft.get("due_time")
    due_t_str = due_t.strftime("%I:%M %p").lstrip("0") if due_t else "9:00 AM (Default)"

    rem1_display = draft.get("reminder_1_label") or "🔕 None"

    text = (
        "🔔 <b>Step 2 of 2: Second Alert (Due Date Alert)</b>\n"
        "────────────────────\n"
        f"📅 Due Date: <b>{due_d_str}</b>\n"
        f"1st Alert: {rem1_display}\n\n"
        "Choose an alert time on your due date:"
    )

    keyboard = [
        [
            InlineKeyboardButton("🌅 Morning (08:00 AM)", callback_data="add:set_remind2:morning"),
            InlineKeyboardButton("☀️ Afternoon (01:00 PM)", callback_data="add:set_remind2:afternoon")
        ],
        [
            InlineKeyboardButton("🌙 Evening (06:00 PM)", callback_data="add:set_remind2:evening"),
            InlineKeyboardButton(f"⏰ At Due Time ({due_t_str})", callback_data="add:set_remind2:duetime")
        ],
        [
            InlineKeyboardButton("⌨️ Custom Time on Due Date", callback_data="add:set_remind2:custom"),
            InlineKeyboardButton("🔕 Skip 2nd Alert", callback_data="add:set_remind2:none")
        ],
        [
            get_back_button(),
            get_cancel_button()
        ]
    ]
    await reply_or_edit_func(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return WAITING_SECOND_REMINDER


async def handle_second_reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process Second Alert choice and proceed to Confirmation screen."""
    query = update.callback_query
    await query.answer()

    choice = query.data.split(":")[2]
    draft = context.user_data["task_draft"]

    if choice == "none":
        draft["reminder_2"] = None
        draft["reminder_2_label"] = "🔕 None"
        push_history(context, WAITING_SECOND_REMINDER)
        return await show_confirmation_screen(query.edit_message_text, context)

    if choice == "custom":
        push_history(context, WAITING_SECOND_REMINDER)
        due_d = draft.get("due_date")
        due_d_str = due_d.strftime("%d/%m/%Y") if due_d else ""
        prompt = (
            f"⌨️ <b>Custom Second Alert (Due Date Time)</b>\n\n"
            f"Enter the time on your due date (<b>{due_d_str}</b>) for this alert:\n"
            "(e.g. <code>10:30 AM</code>, <code>2:45 PM</code>, or <code>15:00</code>)"
        )
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await query.edit_message_text(text=prompt, reply_markup=markup, parse_mode="HTML")
        return WAITING_CUSTOM_SECOND_REMINDER

    # Preset times
    if choice == "morning":
        target_time = time(8, 0)
        label_prefix = "Due Date Morning (08:00 AM)"
    elif choice == "afternoon":
        target_time = time(13, 0)
        label_prefix = "Due Date Afternoon (01:00 PM)"
    elif choice == "evening":
        target_time = time(18, 0)
        label_prefix = "Due Date Evening (06:00 PM)"
    elif choice == "duetime":
        target_time = draft["due_time"] or time(9, 0)
        t_str = target_time.strftime("%I:%M %p").lstrip("0")
        label_prefix = f"At Due Time ({t_str})"
    else:
        target_time = time(9, 0)
        label_prefix = "Due Date (09:00 AM)"

    user = update.effective_user
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    naive_alert = datetime.combine(draft["due_date"], target_time)
    remind_at_utc = local_to_utc(naive_alert, user_tz)

    from datetime import timezone
    if remind_at_utc <= datetime.now(timezone.utc):
        await query.answer("⚠️ This time has already passed today! Please select another time or skip.", show_alert=True)
        return WAITING_SECOND_REMINDER

    draft["reminder_2"] = remind_at_utc.isoformat()
    draft["reminder_2_label"] = label_prefix

    push_history(context, WAITING_SECOND_REMINDER)
    return await show_confirmation_screen(query.edit_message_text, context)


async def handle_custom_second_reminder_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parse custom time text for the second alert on due date."""
    text = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass

    draft = context.user_data["task_draft"]
    menu_msg_id = draft.get("menu_message_id")

    async def edit_or_reply(txt, reply_markup=None, parse_mode=None):
        if menu_msg_id:
            try:
                return await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=menu_msg_id,
                    text=txt,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            except Exception:
                pass
        return await update.message.reply_text(text=txt, reply_markup=reply_markup, parse_mode=parse_mode)

    parsed_time = parse_time_string(text)
    if not parsed_time:
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await edit_or_reply(
            txt="⚠️ <b>Invalid Time format</b>\n\n"
                "Please enter a valid time (e.g. <code>10:30 AM</code>, <code>2:30 PM</code>, or <code>15:00</code>):",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return WAITING_CUSTOM_SECOND_REMINDER

    user = update.effective_user
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    naive_alert = datetime.combine(draft["due_date"], parsed_time)
    remind_at_utc = local_to_utc(naive_alert, user_tz)

    from datetime import timezone
    if remind_at_utc <= datetime.now(timezone.utc):
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await edit_or_reply(
            txt="⚠️ <b>Past Time</b>\n\n"
                "This time has already passed today. Please enter a future time on your due date:",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return WAITING_CUSTOM_SECOND_REMINDER

    time_formatted = parsed_time.strftime("%I:%M %p").lstrip("0")
    draft["reminder_2"] = remind_at_utc.isoformat()
    draft["reminder_2_label"] = f"Due Date at {time_formatted}"

    push_history(context, WAITING_CUSTOM_SECOND_REMINDER)
    return await show_confirmation_screen(edit_or_reply, context)


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
    """Commit the fully prepared task and both alerts to Supabase and clean up state."""
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
        repeat_rule="none",
        description=None
    )

    if not saved_task:
        await query.edit_message_text(
            "⚠️ <b>Failed to Save</b>\n\nCould not commit task to the database. Please try again later.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML"
        )
        return ConversationHandler.END

    task_id = saved_task.get("id")
    db_user_uuid = saved_task.get("user_id")
    client = get_supabase_client()

    # Schedule 1st Alert (Advance) if set
    rem1_iso = draft.get("reminder_1")
    if rem1_iso:
        try:
            client.table("reminders").insert({
                "task_id": task_id,
                "user_id": db_user_uuid,
                "remind_at": rem1_iso,
                "status": "pending"
            }).execute()
            logger.info("Saved 1st alert for task %s at %s", task_id, rem1_iso)
        except Exception as exc:
            logger.error("Error inserting 1st reminder: %s", exc)

    # Schedule 2nd Alert (Due Date) if set
    rem2_iso = draft.get("reminder_2")
    if rem2_iso:
        try:
            client.table("reminders").insert({
                "task_id": task_id,
                "user_id": db_user_uuid,
                "remind_at": rem2_iso,
                "status": "pending"
            }).execute()
            logger.info("Saved 2nd alert for task %s at %s", task_id, rem2_iso)
        except Exception as exc:
            logger.error("Error inserting 2nd reminder: %s", exc)


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

    elif prev_state == WAITING_FIRST_REMINDER:
        context.user_data["task_draft"]["reminder_1"] = None
        context.user_data["task_draft"]["reminder_1_label"] = None
        return await show_first_reminder_menu(query.edit_message_text, context)

    elif prev_state == WAITING_CUSTOM_FIRST_REMINDER:
        prompt = (
            "⌨️ <b>Custom First Alert (Advance Reminder)</b>\n\n"
            "Type how long before your task is due (e.g. <code>2 days</code>, <code>3d</code>, <code>5 days</code>, <code>12 hours</code>, <code>30 mins</code>)\n"
            "or enter a specific date/time (e.g. <code>24/09/2026 09:00 AM</code>):"
        )
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await query.edit_message_text(text=prompt, reply_markup=markup, parse_mode="HTML")
        return WAITING_CUSTOM_FIRST_REMINDER

    elif prev_state == WAITING_SECOND_REMINDER:
        context.user_data["task_draft"]["reminder_2"] = None
        context.user_data["task_draft"]["reminder_2_label"] = None
        return await show_second_reminder_menu(query.edit_message_text, context)

    elif prev_state == WAITING_CUSTOM_SECOND_REMINDER:
        due_d = context.user_data["task_draft"].get("due_date")
        due_d_str = due_d.strftime("%d/%m/%Y") if due_d else ""
        prompt = (
            f"⌨️ <b>Custom Second Alert (Due Date Time)</b>\n\n"
            f"Enter the time on your due date (<b>{due_d_str}</b>) for this alert:\n"
            "(e.g. <code>10:30 AM</code>, <code>2:45 PM</code>, or <code>15:00</code>)"
        )
        markup = InlineKeyboardMarkup([[get_back_button(), get_cancel_button()]])
        await query.edit_message_text(text=prompt, reply_markup=markup, parse_mode="HTML")
        return WAITING_CUSTOM_SECOND_REMINDER

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
            WAITING_FIRST_REMINDER: [
                CallbackQueryHandler(handle_first_reminder_callback, pattern="^add:set_remind1:(none|custom|\\d+)$")
            ],
            WAITING_CUSTOM_FIRST_REMINDER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_first_reminder_text)
            ],
            WAITING_SECOND_REMINDER: [
                CallbackQueryHandler(handle_second_reminder_callback, pattern="^add:set_remind2:(none|custom|morning|afternoon|evening|duetime)$")
            ],
            WAITING_CUSTOM_SECOND_REMINDER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_second_reminder_text)
            ],
            WAITING_CONFIRMATION: [
                CallbackQueryHandler(handle_save_task, pattern="^add:save_task$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(handle_back_navigation, pattern="^add:back$"),
            CallbackQueryHandler(handle_cancellation, pattern="^add:cancel$"),
            CommandHandler("cancel", handle_cancellation),
            CommandHandler("start", handle_cancellation)
        ],
        per_message=False
    )

