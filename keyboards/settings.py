"""Settings inline keyboards for Todo-list by LDR."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Return the inline keyboard for settings options."""
    keyboard = [
        [
            InlineKeyboardButton("🌐 Change Timezone", callback_data="settings:timezone:list")
        ],
        [
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu:main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_timezone_keyboard() -> InlineKeyboardMarkup:
    """Return the inline keyboard for choosing common timezones."""
    keyboard = [
        [
            InlineKeyboardButton("🇰🇭 Phnom Penh", callback_data="settings:timezone:set:Asia/Phnom_Penh"),
            InlineKeyboardButton("🇹🇭 Bangkok", callback_data="settings:timezone:set:Asia/Bangkok")
        ],
        [
            InlineKeyboardButton("🇸🇬 Singapore", callback_data="settings:timezone:set:Asia/Singapore"),
            InlineKeyboardButton("🌐 UTC", callback_data="settings:timezone:set:UTC")
        ],
        [
            InlineKeyboardButton("↩️ Back to Settings", callback_data="menu:settings")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
