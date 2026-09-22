"""Main Telegram Bot entry point for Todo-list by LDR.

Initializes the bot application, wires up routers, triggers startup health checks,
and handles runtime errors gracefully.
"""

from __future__ import annotations

import logging
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import config
from database import check_supabase_connection
from handlers import (
    get_start_handler,
    get_menu_handlers,
    get_tasks_handlers,
    get_create_task_handler,
    get_edit_task_handlers,
    get_completed_handlers,
    get_settings_handlers
)

# Setup professional logging format
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, config.log_level, logging.INFO)
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Centralized exception handling to prevent runtime bot crashes on unhandled handler errors."""
    logger.error("Exception occurred during update handling:", exc_info=context.error)
    
    friendly_msg = (
        "⚠️ <b>Something went wrong</b>\n\n"
        "An unexpected error occurred while processing your request. Please try again later."
    )
    
    # Notify user if possible
    if isinstance(update, Update):
        if update.callback_query:
            try:
                await update.callback_query.answer("⚠️ An error occurred.", show_alert=True)
                await update.callback_query.message.reply_text(friendly_msg, parse_mode="HTML")
            except Exception:
                pass
        elif update.effective_message:
            try:
                await update.effective_message.reply_text(friendly_msg, parse_mode="HTML")
            except Exception:
                pass


def main() -> None:
    """Bootstraps and runs the Telegram Bot."""
    logger.info("Starting %s telegram bot...", config.bot_name)

    # 1. Trigger Supabase Connectivity Health Check
    if not check_supabase_connection():
        logger.critical("Database health check failed. Please check your Supabase credentials in .env!")
        sys.exit(1)

    # 2. Build the Application
    application = Application.builder().token(config.telegram_bot_token).build()

    # 3. Register Central Error Handler
    application.add_error_handler(error_handler)

    # 4. Attach Command & Callback Handlers
    application.add_handler(get_start_handler())
    application.add_handler(get_create_task_handler())
    
    # Edit task contains a ConversationHandler that needs to be registered before general callbacks
    for edit_handler in get_edit_task_handlers():
        application.add_handler(edit_handler)
    
    for completed_handler in get_completed_handlers():
        application.add_handler(completed_handler)
    
    for menu_handler in get_menu_handlers():
        application.add_handler(menu_handler)
        
    for task_handler in get_tasks_handlers():
        application.add_handler(task_handler)

    for settings_handler in get_settings_handlers():
        application.add_handler(settings_handler)

    # 5. Initialize background reminder scheduler
    if application.job_queue:
        from services.scheduler_service import poll_and_dispatch_reminders, check_pending_reminders
        # Polling runs every 30 seconds, with an initial 10-second delay for smooth bootup
        application.job_queue.run_repeating(
            poll_and_dispatch_reminders,
            interval=30,
            first=10,
            name="poll_and_dispatch_reminders"
        )
        # Check for overdue tasks runs every 60 seconds (every minute), with an initial 15-second delay
        application.job_queue.run_repeating(
            check_pending_reminders,
            interval=60,
            first=15,
            name="check_pending_reminders"
        )
        logger.info("Background reminder and overdue task schedulers registered.")
    else:
        logger.warning("JobQueue is unavailable. Reminder scheduler will not run.")

    # 6. Run the bot (using long polling for individual personal dev)
    logger.info("Bot is ready and listening for events.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
