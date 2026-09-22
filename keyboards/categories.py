"""Category selection keyboard module for Todo-list by LDR."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_categories_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard to let user filter tasks by default categories."""
    keyboard = [
        [
            InlineKeyboardButton("👤 Personal", callback_data="cat:personal"),
            InlineKeyboardButton("💼 Work", callback_data="cat:work")
        ],
        [
            InlineKeyboardButton("🎓 School", callback_data="cat:school"),
            InlineKeyboardButton("📚 All Tasks", callback_data="cat:all")
        ],
        [
            InlineKeyboardButton("🔴 Overdue", callback_data="cat:overdue")
        ],
        [
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu:main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
