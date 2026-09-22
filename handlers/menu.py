"""Main menu callback query handlers for Todo-list by LDR."""

from __future__ import annotations

import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
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


@authorized_only
async def menu_upcoming_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Load upcoming pending tasks and display a paginated/simple list with numeric selectors."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    db_user = get_or_create_user(user)
    user_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    # Fetch upcoming tasks
    from services.task_service import get_upcoming_tasks
    from keyboards.tasks import get_tasks_list_keyboard
    from utils.formatters import get_priority_display, format_relative_date, format_time

    tasks = get_upcoming_tasks(user.id)

    header = "🔔 <b>Upcoming Tasks</b>\n──────────────────────\n\n"

    if not tasks:
        body = "<i>You have no upcoming tasks scheduled. Create one using the ➕ <b>Create Task</b> button!</i>\n\n"
    else:
        # Show up to 5 upcoming tasks
        lines = []
        for i, task in enumerate(tasks[:5], start=1):
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
        
        body = "\n\n".join(lines) + "\n\n"

    markup = get_tasks_list_keyboard(tasks, "all")

    try:
        await query.edit_message_text(
            text=header + body,
            reply_markup=markup,
            parse_mode="HTML"
        )
    except Exception as exc:
        logger.error("Failed to render upcoming list: %s", exc)


@authorized_only
async def menu_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display settings screen with IANA timezone choices."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    db_user = get_or_create_user(user)
    current_tz = db_user.get("timezone", "Asia/Phnom_Penh")

    from keyboards import get_settings_keyboard

    text = (
        "⚙️ <b>Settings Dashboard</b>\n"
        "─────────────────\n\n"
        f"🌐 <b>Current Timezone:</b> <code>{current_tz}</code>\n\n"
        "To ensure reminder notifications and alert messages are delivered exactly on time, "
        "please select your local timezone from the options below:"
    )

    try:
        await query.edit_message_text(
            text=text,
            reply_markup=get_settings_keyboard(current_tz),
            parse_mode="HTML"
        )
    except Exception as exc:
        logger.error("Failed to render settings menu: %s", exc)


@authorized_only
async def timezone_change_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle timezone button clicks, update database, and show success."""
    query = update.callback_query
    
    # Extract timezone name from pattern, e.g. "settings:timezone:Asia/Phnom_Penh"
    new_tz = query.data.split(":")[2]
    
    user = update.effective_user
    from services import update_user_timezone
    
    success = update_user_timezone(user.id, new_tz)
    
    if success:
        await query.answer(f"Timezone updated to {new_tz}!", show_alert=False)
    else:
        await query.answer("Failed to update timezone. Please try again.", show_alert=True)

    # Re-render settings screen with the newly saved timezone
    from keyboards import get_settings_keyboard
    
    text = (
        "⚙️ <b>Settings Dashboard</b>\n"
        "─────────────────\n\n"
        f"🌐 <b>Current Timezone:</b> <code>{new_tz}</code>\n\n"
        "✨ <b>Success:</b> Timezone has been updated successfully!\n\n"
        "Your upcoming alerts and reminders will now perfectly align with your local clock."
    )

    try:
        await query.edit_message_text(
            text=text,
            reply_markup=get_settings_keyboard(new_tz),
            parse_mode="HTML"
        )
    except Exception as exc:
        logger.error("Failed to edit settings menu after update: %s", exc)


@authorized_only
async def menu_exit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Close the menu, clear all tracked chat messages, and show a clean informative goodbye message."""
    query = update.callback_query
    await query.answer()

    # 1. Fetch all tracked message IDs for this session
    menu_messages = context.user_data.get("menu_messages", [])
    chat_id = query.message.chat_id

    # 2. Iterate and delete all logged messages to completely clean the chat history of this session
    logger.info("Exiting: Clearing %d tracked chat messages for user %s...", len(menu_messages), chat_id)
    for msg_id in list(menu_messages):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            # Ignore messages already deleted or older than 48 hours
            pass

    # Clear the tracking list
    context.user_data["menu_messages"] = []

    text = (
        "👋 <b>Closed To-Do Assistant</b>\n"
        "──────────────────\n\n"
        "All active menu screens and intermediate inputs have been cleared from this chat!\n\n"
        "⚠️ <b>Reminder Status:</b> Even though you have closed this dashboard, "
        "your scheduled task reminders, alerts, and overdue notifications are <b>fully active</b> "
        "and will continue to notify you in this chat exactly at your set times!\n\n"
        "To open the menu dashboard again at any time, just type /start."
    )

    # 3. Send a single clean goodbye message with ForceReply to keep the bot responsive
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=ForceReply(selective=True, placeholder="Type /start to open the menu..."),
            parse_mode="HTML"
        )
    except Exception as exc:
        logger.error("Failed to send clean exit message: %s", exc)


def get_menu_handlers() -> list[CallbackQueryHandler]:
    """Return list of callback handlers for main menu routes."""
    return [
        CallbackQueryHandler(menu_main_callback, pattern="^menu:main$"),
        CallbackQueryHandler(menu_tasks_callback, pattern="^menu:tasks$"),
        CallbackQueryHandler(menu_upcoming_callback, pattern="^menu:upcoming$"),
        CallbackQueryHandler(menu_settings_callback, pattern="^menu:settings$"),
        CallbackQueryHandler(timezone_change_callback, pattern="^settings:timezone:(.+)$"),
        CallbackQueryHandler(menu_exit_callback, pattern="^menu:exit$")
    ]
