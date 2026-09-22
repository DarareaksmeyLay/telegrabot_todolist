"""Help command handler for Todo-list by LDR.

Displays clear instructions on how to use the bot and lists all available commands.
"""

from __future__ import annotations

import logging
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from utils.security import authorized_only

logger = logging.getLogger(__name__)


@authorized_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command. Displays user manual and commands list."""
    help_text = (
        "📖 <b>To-Do Assistant Guide & User Manual</b>\n"
        "─────────────────────────\n\n"
        "Welcome! This bot is your elegant personal assistant to manage tasks with smart notifications and overdue alerts.\n\n"
        "<b>🎮 How to Use the Bot:</b>\n"
        "• <b>Start the Bot:</b> Type /start to load the interactive dashboard menu.\n"
        "• <b>➕ Create a Task:</b> Click the <b>Create Task</b> button on the dashboard, then type your task's title, choose a category, priority, due date, and reminder time step-by-step.\n"
        "• <b>📋 Show Tasks:</b> Click <b>Show Tasks</b> to view your pending to-do lists, edit priority/time, or mark tasks as completed.\n"
        "• <b>🔔 Upcoming:</b> See tasks sorted chronologically by due date.\n"
        "• <b>✅ Completed:</b> View completed tasks history.\n"
        "• <b>🚪 Exit:</b> Click the exit button to completely clear the chat history and make it spotless, while keeping all alerts active!\n\n"
        "<b>💻 Available Commands:</b>\n"
        "• /start - Launch the visual Dashboard menu\n"
        "• /help - Display this manual and command instructions\n"
        "• /cancel - Abort active task creation or conversation states\n\n"
        "<b>⏰ Automated Smart Alerts:</b>\n"
        "• The bot runs background schedulers to send you direct reminder alerts exactly at your set notification times.\n"
        "• If a task passes its due time without being completed, the bot instantly marks it as 🔴 <b>Overdue</b> and sends you an immediate warning alert so you can complete or reschedule it!"
    )

    # Automatically track help messages so they are deleted on Exit if the user wants
    if "menu_messages" not in context.user_data:
        context.user_data["menu_messages"] = []

    # Track user's command
    if update.message:
        context.user_data["menu_messages"].append(update.message.message_id)

    try:
        sent_msg = await update.message.reply_text(
            text=help_text,
            parse_mode="HTML"
        )
        context.user_data["menu_messages"].append(sent_msg.message_id)
    except Exception as exc:
        logger.error("Failed to send help message: %s", exc)


def get_help_handler() -> CommandHandler:
    """Return configured CommandHandler for help."""
    return CommandHandler("help", help_command)
