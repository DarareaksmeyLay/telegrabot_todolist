"""Date and timezone utility module for Todo-list by LDR.

Handles safe conversion between UTC (stored in Supabase TIMESTAMPTZ) and user-local timezones.
"""

from __future__ import annotations

import logging
from datetime import datetime, date, time
from typing import Optional, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


def get_timezone(tz_name: Optional[str]) -> ZoneInfo:
    """Return a safe ZoneInfo object. Fallback to Asia/Phnom_Penh if invalid or missing."""
    if not tz_name:
        return ZoneInfo("Asia/Phnom_Penh")
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning("Invalid timezone '%s' requested; falling back to Asia/Phnom_Penh", tz_name)
        return ZoneInfo("Asia/Phnom_Penh")


def utc_to_local(utc_dt: Optional[Union[str, datetime]], tz_name: str) -> Optional[datetime]:
    """Convert an absolute UTC datetime (or ISO string) into user's local timezone.

    Returns naive datetime representing the user's wall-clock time.
    """
    if not utc_dt:
        return None

    if isinstance(utc_dt, str):
        try:
            # Handle postgrest/supabase ISO format (e.g. '2026-09-22T05:00:00+00:00')
            # Replacing trailing 'Z' if present
            clean_str = utc_dt.replace("Z", "+00:00")
            parsed_dt = datetime.fromisoformat(clean_str)
        except ValueError as exc:
            logger.error("Failed to parse ISO datetime string '%s': %s", utc_dt, exc)
            return None
    else:
        parsed_dt = utc_dt

    # Ensure it's timezone-aware as UTC
    if parsed_dt.tzinfo is None:
        parsed_dt = parsed_dt.replace(tzinfo=ZoneInfo("UTC"))

    local_tz = get_timezone(tz_name)
    return parsed_dt.astimezone(local_tz)


def local_to_utc(local_dt: datetime, tz_name: str) -> datetime:
    """Attach the local timezone to a naive datetime, and convert it to UTC for storage."""
    local_tz = get_timezone(tz_name)
    
    # Attach timezone if naive, otherwise convert
    if local_dt.tzinfo is None:
        local_aware = local_dt.replace(tzinfo=local_tz)
    else:
        local_aware = local_dt.astimezone(local_tz)
        
    return local_aware.astimezone(ZoneInfo("UTC"))


def parse_date_string(date_str: str) -> Optional[date]:
    """Parse a DD/MM/YYYY date string. Return date object if valid, else None."""
    try:
        parts = date_str.split("/")
        if len(parts) != 3:
            return None
        
        day = int(parts[0])
        month = int(parts[1])
        year = int(parts[2])
        
        # Check basic bounds to prevent unreasonable years
        if year < 2026 or year > 2100:
            return None
            
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


def parse_time_string(time_str: str) -> Optional[time]:
    """Parse time string with flexible formatting support (HH:MM or 12-hour AM/PM formats).

    Supported formats: "09:30", "14:30", "9:00 AM", "2:30 PM", "9:00AM", "2:30PM".
    """
    cleaned = time_str.strip().upper()
    
    # 1. Check for 12-hour format with AM/PM
    if "AM" in cleaned or "PM" in cleaned:
        is_pm = "PM" in cleaned
        # Strip letters
        time_part = cleaned.replace("AM", "").replace("PM", "").strip()
        try:
            parts = time_part.split(":")
            if len(parts) != 2:
                return None
            hour = int(parts[0])
            minute = int(parts[1])
            
            if hour < 1 or hour > 12 or minute < 0 or minute > 59:
                return None
                
            if is_pm and hour != 12:
                hour += 12
            elif not is_pm and hour == 12:
                hour = 0
                
            return time(hour, minute)
        except ValueError:
            return None
            
    # 2. Check for 24-hour format (e.g. 14:30)
    try:
        parts = cleaned.split(":")
        if len(parts) != 2:
            return None
        hour = int(parts[0])
        minute = int(parts[1])
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return time(hour, minute)
    except ValueError:
        pass

    return None


def parse_advance_alert_input(
    text: str,
    due_dt_local: datetime
) -> Optional[datetime]:
    """Parse custom input for a first/advance alert.

    Accepts relative specifications (e.g., '2 days', '3d', '1 week', '12 hours', '30 mins', '4')
    or absolute date/time strings (e.g., '24/09/2026 09:00 AM', '24/09/2026 14:00', '24/09/2026').

    Returns naive local datetime if valid, or None if unparseable.
    """
    import re
    from datetime import timedelta

    cleaned = text.strip()
    if not cleaned:
        return None

    # 1. Check relative expressions with units
    m_weeks = re.match(r"^(\d+)\s*(weeks?|w)$", cleaned, re.IGNORECASE)
    if m_weeks:
        qty = int(m_weeks.group(1))
        return due_dt_local - timedelta(weeks=qty)

    m_days = re.match(r"^(\d+)\s*(days?|d)$", cleaned, re.IGNORECASE)
    if m_days:
        qty = int(m_days.group(1))
        return due_dt_local - timedelta(days=qty)

    m_hours = re.match(r"^(\d+)\s*(hours?|hrs?|h)$", cleaned, re.IGNORECASE)
    if m_hours:
        qty = int(m_hours.group(1))
        return due_dt_local - timedelta(hours=qty)

    m_mins = re.match(r"^(\d+)\s*(minutes?|mins?|m)$", cleaned, re.IGNORECASE)
    if m_mins:
        qty = int(m_mins.group(1))
        return due_dt_local - timedelta(minutes=qty)

    # 2. Check if just a bare number (assume days)
    if cleaned.isdigit():
        qty = int(cleaned)
        return due_dt_local - timedelta(days=qty)

    # 3. Check for absolute datetime (e.g., "24/09/2026 09:00 AM" or "24/09/2026 14:30")
    if "/" in cleaned:
        tokens = cleaned.split(maxsplit=1)
        date_part = tokens[0]
        parsed_d = parse_date_string(date_part)
        if parsed_d:
            if len(tokens) > 1:
                parsed_t = parse_time_string(tokens[1])
                target_t = parsed_t if parsed_t else time(9, 0)
            else:
                target_t = time(9, 0)
            return datetime.combine(parsed_d, target_t)

    return None


def format_reminder_label(
    remind_at: Any,
    due_at: Any,
    user_tz: str
) -> str:
    """Format a clean, readable label describing when a reminder triggers relative to due date."""
    if not remind_at:
        return "🔕 Not set"

    # utc_to_local cleanly handles both ISO string and datetime instances
    local_remind = utc_to_local(remind_at, user_tz) if (isinstance(remind_at, str) or getattr(remind_at, "tzinfo", None)) else remind_at
    local_due = utc_to_local(due_at, user_tz) if (isinstance(due_at, str) or getattr(due_at, "tzinfo", None)) else due_at

    if not local_remind:
        return "🔕 Not set"

    time_str = local_remind.strftime("%I:%M %p").lstrip("0")
    date_str = local_remind.strftime("%d %b")

    if not local_due:
        return f"{date_str} at {time_str}"

    diff = local_due - local_remind
    diff_seconds = int(diff.total_seconds())

    if diff_seconds <= 0:
        return f"At due time ({date_str}, {time_str})"

    diff_days = diff_seconds // 86400
    diff_hours = (diff_seconds % 86400) // 3600
    diff_mins = (diff_seconds % 3600) // 60

    if diff_seconds % 86400 == 0 and diff_days > 0:
        if diff_days == 7:
            return f"1 week before ({date_str}, {time_str})"
        elif diff_days == 1:
            return f"1 day before ({date_str}, {time_str})"
        else:
            return f"{diff_days} days before ({date_str}, {time_str})"
    elif diff_days > 0:
        return f"{diff_days}d {diff_hours}h before ({date_str}, {time_str})"
    elif diff_hours > 0:
        return f"{diff_hours}h before ({date_str}, {time_str})"
    elif diff_mins > 0:
        return f"{diff_mins}m before ({date_str}, {time_str})"

    return f"{date_str} at {time_str}"

