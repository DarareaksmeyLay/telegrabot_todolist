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
            InlineKeyboardButton("🚪 Exit", callback_data="menu:exit")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_settings_keyboard(current_timezone: str) -> InlineKeyboardMarkup:
    """Return timezone adjustment settings keyboard."""
    def btn_label(tz: str, name: str) -> str:
        return f"✅ {name}" if tz == current_timezone else name

    keyboard = [
        [
            InlineKeyboardButton(btn_label("Asia/Phnom_Penh", "Phnom Penh 🇰🇭"), callback_data="settings:timezone:Asia/Phnom_Penh"),
            InlineKeyboardButton(btn_label("Asia/Bangkok", "Bangkok 🇹🇭"), callback_data="settings:timezone:Asia/Bangkok")
        ],
        [
            InlineKeyboardButton(btn_label("Asia/Singapore", "Singapore 🇸🇬"), callback_data="settings:timezone:Asia/Singapore"),
            InlineKeyboardButton(btn_label("Asia/Ho_Chi_Minh", "Vietnam 🇻🇳"), callback_data="settings:timezone:Asia/Ho_Chi_Minh")
        ],
        [
            InlineKeyboardButton(btn_label("Asia/Jakarta", "Jakarta 🇮🇩"), callback_data="settings:timezone:Asia/Jakarta"),
            InlineKeyboardButton(btn_label("Asia/Manila", "Manila 🇵🇭"), callback_data="settings:timezone:Asia/Manila")
        ],
        [
            InlineKeyboardButton(btn_label("UTC", "UTC 🌐"), callback_data="settings:timezone:UTC")
        ],
        [
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu:main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
