"""Inline keyboard package for Todo-list by LDR."""
from .main import get_main_menu_keyboard, get_settings_keyboard
from .categories import get_categories_keyboard
from .tasks import get_tasks_list_keyboard, get_task_details_keyboard

__all__ = [
    "get_main_menu_keyboard",
    "get_settings_keyboard",
    "get_categories_keyboard",
    "get_tasks_list_keyboard",
    "get_task_details_keyboard"
]
