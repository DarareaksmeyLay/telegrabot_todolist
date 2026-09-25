"""Visual formatting and emoji utilities for Todo-list by LDR Telegram UI.

Provides standardized strings, cards, headers, and relative date indicators.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Dict, Any, Optional
from utils.dates import utc_to_local, get_timezone, format_reminder_label

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


from database import get_supabase_client


def format_time(target_dt: Any, tz_name: str) -> str:
    """Format time component cleanly in 12-hour format (e.g. '3:00 PM')."""
    if not target_dt:
        return ""
    local_dt = utc_to_local(target_dt, tz_name) if (isinstance(target_dt, str) or getattr(target_dt, "tzinfo", None)) else target_dt
    if not local_dt:
        return ""
    return local_dt.strftime("%I:%M %p").lstrip("0")


def format_task_detail_card(
    task: Dict[str, Any],
    user_tz: str,
    reminders: Optional[list] = None
) -> str:
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

    # Automatically query reminders if not passed and task has an ID
    alerts_text = ""
    rems = reminders
    if rems is None and task.get("id"):
        try:
            client = get_supabase_client()
            rem_res = client.table("reminders").select("*").eq("task_id", task["id"]).eq("status", "pending").order("remind_at", desc=False).execute()
            rems = rem_res.data or []
        except Exception:
            rems = []
    elif rems is None:
        rems = task.get("reminders")

    try:
        if rems:
            # Sort pending reminders
            pending_rems = [r for r in rems if r.get("status") == "pending"]
            if pending_rems:
                pending_rems.sort(key=lambda x: str(x.get("remind_at", "")))
                lines = []
                if len(pending_rems) >= 2:
                    r1 = pending_rems[0]
                    r2 = pending_rems[1]
                    lines.append(f"• 1st Alert (Advance): {format_reminder_label(r1.get('remind_at'), due_at_raw, user_tz)}")
                    r2_date = format_relative_date(r2.get("remind_at"), user_tz)
                    r2_time = format_time(r2.get("remind_at"), user_tz)
                    lines.append(f"• 2nd Alert (Due Date): {r2_date} at {r2_time}")
                elif len(pending_rems) == 1:
                    r = pending_rems[0]
                    local_r = utc_to_local(r.get("remind_at"), user_tz)
                    local_due = utc_to_local(due_at_raw, user_tz) if due_at_raw else None
                    if local_r and local_due and local_r.date() == local_due.date():
                        r_time = format_time(r.get("remind_at"), user_tz)
                        lines.append(f"• 2nd Alert (Due Date): At {r_time}")
                    else:
                        lines.append(f"• 1st Alert (Advance): {format_reminder_label(r.get('remind_at'), due_at_raw, user_tz)}")
                if lines:
                    alerts_text = f"\n🔔 <b>Alerts:</b>\n" + "\n".join(lines)
        elif due_at_raw:
            alerts_text = "\n🔔 <b>Alerts:</b> 🔕 None set"
    except Exception:
        if due_at_raw:
            alerts_text = "\n🔔 <b>Alerts:</b> 🔕 None set"


    card = (
        "📋 <b>Task Details</b>\n\n"
        f"📝 <b>{title}</b>\n"
        f"ℹ️ {description}\n\n"
        f"📁 <b>Category:</b> {category}\n"
        f"📅 <b>Due:</b> {due_display}\n"
        f"🚩 <b>Priority:</b> {priority}\n"
        f"🔁 <b>Repeat:</b> {repeat_rule}\n"
        f"📌 <b>Status:</b> {status_display}"
        f"{alerts_text}\n"
    )
    return card

