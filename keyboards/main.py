"""Main menu inline keyboard for Todo-list by LDR."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Return the dashboard-style main menu inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("➕ Create Task", callback_data="add:start"),
            InlineKeyboardButton("📋 Show Tasks", callback_data="menu:tasks")
        ],
        [
            InlineKeyboardButton("🔔 Upcoming", callback_data="menu:upcoming"),
            InlineKeyboardButton("✅ Completed", callback_data="menu:completed")
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="menu:settings")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
