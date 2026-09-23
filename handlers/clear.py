"""Clear command handler for Todo-list by LDR.

Purges the chat history of all tracked session messages.
"""

from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes

from utils.security import authorized_only

logger = logging.getLogger(__name__)


@authorized_only
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /clear command. Deletes all tracked bot and user messages for a spotless chat."""
    chat_id = update.effective_chat.id
    user_msg_id = update.message.message_id if update.message else None

    # Retrieve all currently tracked message IDs
    menu_messages = context.user_data.get("menu_messages", [])
    
    # Ensure the user's /clear command message is included in the deletion list
    if user_msg_id and user_msg_id not in menu_messages:
        menu_messages.append(user_msg_id)

    logger.info("Purging %d tracked messages for chat %s...", len(menu_messages), chat_id)
    
    # Delete all logged messages to fully clear chat history
    for msg_id in list(menu_messages):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            # Silence errors for already deleted or expired messages
            pass

    # Reset tracking
    context.user_data["menu_messages"] = []

    # Send a fresh, clean confirmation message with a button to return to the main dashboard
    text = (
        "🧹 <b>Chat Cleared Successfully!</b>\n"
        "──────────────────\n\n"
        "All active menu screens, input prompts, and bot interactions have been permanently deleted from this chat window.\n\n"
        "🚀 To open the task manager again, use the button below or type /start."
    )
    
    keyboard = [
        [
            InlineKeyboardButton("🏠 Open Dashboard", callback_data="menu:main")
        ]
    ]
    
    try:
        sent_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        # Track the new confirmation message so it can also be deleted subsequently
        context.user_data["menu_messages"].append(sent_msg.message_id)
    except Exception as exc:
        logger.error("Failed to send clear confirmation message: %s", exc)


def get_clear_handler() -> CommandHandler:
    """Return configured CommandHandler for clearing chat history."""
    return CommandHandler("clear", clear_command)
