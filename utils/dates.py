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
