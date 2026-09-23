"""Visual formatting and emoji utilities for Todo-list by LDR Telegram UI.

Provides standardized strings, cards, headers, and relative date indicators.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Dict, Any, Optional
from utils.dates import utc_to_local, get_timezone

# Emojis and display titles
CATEGORY_EMOJIS: Dict[str, str] = {
    "personal": "👤",
    "work": "💼",
    "school": "🎓"
}

CATEGORY_LABELS: Dict[str, str] = {
    "personal": "Personal",
    "work": "Work",
    "school": "School"
}

PRIORITY_EMOJIS: Dict[str, str] = {
    "high": "🔴",
    "medium": "🟡",
    "low": "🟢"
}

PRIORITY_LABELS: Dict[str, str] = {
    "high": "High",
    "medium": "Medium",
    "low": "Low"
}

STATUS_EMOJIS: Dict[str, str] = {
    "pending": "⏳",
    "completed": "✅",
    "overdue": "🔴"
}


def get_category_display(category: str) -> str:
    """Return category string formatted with its corresponding emoji."""
    emoji = CATEGORY_EMOJIS.get(category.lower(), "📁")
    label = CATEGORY_LABELS.get(category.lower(), category.capitalize())
    return f"{emoji} {label}"


def get_priority_display(priority: str) -> str:
    """Return priority string formatted with its corresponding emoji."""
    emoji = PRIORITY_EMOJIS.get(priority.lower(), "🚩")
    label = PRIORITY_LABELS.get(priority.lower(), priority.capitalize())
    return f"{emoji} {label}"


def format_relative_date(target_dt: Optional[datetime], tz_name: str) -> str:
    """Format a timezone-aware datetime into a relative human-readable string.

    Returns "Today", "Tomorrow", "Yesterday", or full formatted date "23 September 2026".
    """
    if not target_dt:
        return "No Due Date"

    local_dt = utc_to_local(target_dt, tz_name)
    if not local_dt:
        return "No Due Date"

    user_tz = get_timezone(tz_name)
    now_local = datetime.now(user_tz).date()
    target_date = local_dt.date()

    delta = (target_date - now_local).days

    if delta == 0:
        return "Today"
    elif delta == 1:
        return "Tomorrow"
    elif delta == -1:
        return "Yesterday"
    else:
        # e.g., "23 September 2026"
        return target_date.strftime("%d %B %Y")


def format_time(target_dt: Optional[datetime], tz_name: str) -> str:
    """Format time component cleanly in 12-hour format (e.g. '3:00 PM')."""
    if not target_dt:
        return ""
    local_dt = utc_to_local(target_dt, tz_name)
    if not local_dt:
        return ""
    return local_dt.strftime("%I:%M %p").lstrip("0")


def format_task_detail_card(task: Dict[str, Any], user_tz: str) -> str:
    """Generate a clean, highly formatted markdown block of a task's full details."""
    title = task.get("title", "Untitled")
    description = task.get("description") or "No description provided."
    category = get_category_display(task.get("category") or "personal")
    priority = get_priority_display(task.get("priority") or "medium")
    status_raw = task.get("status") or "pending"
    repeat_rule = (task.get("repeat_rule") or "none").capitalize()
    
    due_at_raw = task.get("due_at")
    
    if due_at_raw:
        due_date_str = format_relative_date(due_at_raw, user_tz)
        due_time_str = format_time(due_at_raw, user_tz)
        due_display = f"{due_date_str} • {due_time_str}"
    else:
        due_display = "🚫 No Due Date"

    status_display = "Pending"
    if status_raw == "completed":
        status_display = "Completed"
        completed_at_raw = task.get("completed_at")
        if completed_at_raw:
            comp_date = format_relative_date(completed_at_raw, user_tz)
            comp_time = format_time(completed_at_raw, user_tz)
            status_display += f" (on {comp_date} at {comp_time})"
    elif status_raw == "pending" and due_at_raw:
        try:
            from datetime import timezone
            from zoneinfo import ZoneInfo
            clean_str = due_at_raw.replace("Z", "+00:00")
            due_dt = datetime.fromisoformat(clean_str)
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=ZoneInfo("UTC"))
            
            if due_dt < datetime.now(timezone.utc):
                status_display = "🔴 Overdue"
            else:
                status_display = "⏳ Pending"
        except Exception:
            status_display = "⏳ Pending"
    else:
        status_display = "⏳ Pending"

    card = (
        "📋 <b>Task Details</b>\n\n"
        f"📝 <b>{title}</b>\n"
        f"ℹ️ {description}\n\n"
        f"📁 <b>Category:</b> {category}\n"
        f"📅 <b>Due:</b> {due_display}\n"
        f"🚩 <b>Priority:</b> {priority}\n"
        f"🔁 <b>Repeat:</b> {repeat_rule}\n"
        f"📌 <b>Status:</b> {status_display}\n"
    )
    return card
