"""Task and pagination keyboards for Todo-list by LDR."""

from __future__ import annotations

import math
from typing import List, Dict, Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

TASKS_PER_PAGE = 5


def get_tasks_list_keyboard(
    tasks: List[Dict[str, Any]],
    category: str,
    page: int = 1
) -> InlineKeyboardMarkup:
    """Return inline keyboard representing paginated tasks.

    Includes numbered buttons for task detail selection and back navigation.
    """
    keyboard = []
    total_tasks = len(tasks)
    
    # Calculate page bounds
    total_pages = max(1, math.ceil(total_tasks / TASKS_PER_PAGE))
    current_page = max(1, min(page, total_pages))
    
    start_idx = (current_page - 1) * TASKS_PER_PAGE
    end_idx = start_idx + TASKS_PER_PAGE
    page_tasks = tasks[start_idx:end_idx]

    # 1. Numbered selection buttons for tasks on current page (up to 5)
    if page_tasks:
        num_buttons = []
        for i, task in enumerate(page_tasks, start=1):
            task_id = task.get("id")
            num_buttons.append(InlineKeyboardButton(f"{i}", callback_data=f"task:view:{task_id}"))
        keyboard.append(num_buttons)

    # 2. Pagination controls
    pagination_row = []
    if current_page > 1:
        pagination_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"page:{category}:{current_page - 1}"))
    if current_page < total_pages:
        pagination_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"page:{category}:{current_page + 1}"))
    
    if pagination_row:
        keyboard.append(pagination_row)

    # 3. Quick action to add a task in the current category
    cat_label = category.capitalize() if category != "all" else ""
    keyboard.append([
        InlineKeyboardButton(f"➕ Add {cat_label} Task".strip(), callback_data=f"add:cat:{category}")
    ])

    # 4. Global navigation
    keyboard.append([
        InlineKeyboardButton("🔙 Categories", callback_data="menu:tasks"),
        InlineKeyboardButton("🏠 Main Menu", callback_data="menu:main")
    ])

    return InlineKeyboardMarkup(keyboard)


def get_task_details_keyboard(task_id: str) -> InlineKeyboardMarkup:
    """Return action buttons representing single-task operations."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Complete", callback_data=f"task:done:{task_id}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"task:edit:{task_id}")
        ],
        [
            InlineKeyboardButton("📅 Reschedule", callback_data=f"task:resched:{task_id}"),
            InlineKeyboardButton("🔔 Reminder", callback_data=f"task:remind:{task_id}")
        ],
        [
            InlineKeyboardButton("🗑 Delete", callback_data=f"task:delete:{task_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data="menu:tasks"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu:main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
