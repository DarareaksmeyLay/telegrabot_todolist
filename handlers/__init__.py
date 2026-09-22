"""Handlers package for Todo-list by LDR."""
from .start import get_start_handler
from .menu import get_menu_handlers
from .tasks import get_tasks_handlers
from .create_task import get_create_task_handler
from .edit_task import get_edit_task_handlers
from .completed import get_completed_handlers
from .settings import get_settings_handlers

__all__ = [
    "get_start_handler",
    "get_menu_handlers",
    "get_tasks_handlers",
    "get_create_task_handler",
    "get_edit_task_handlers",
    "get_completed_handlers",
    "get_settings_handlers"
]

