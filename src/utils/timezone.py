"""Timezone utilities for consistent time handling across the application"""

from datetime import datetime, timezone, timedelta
from typing import Optional
import os


def get_timezone_offset() -> int:
    """Get timezone offset in hours from environment variable or default to UTC+8

    Returns:
        int: Timezone offset in hours (default: 8 for China/Asia/Shanghai)
    """
    try:
        return int(os.getenv("TIMEZONE_OFFSET", "8"))
    except ValueError:
        return 8


def get_timezone() -> timezone:
    """Get timezone object based on configured offset

    Returns:
        timezone: Timezone object with configured offset
    """
    offset_hours = get_timezone_offset()
    return timezone(timedelta(hours=offset_hours))


def convert_utc_to_local(utc_time_str: Optional[str]) -> Optional[str]:
    """Convert UTC timestamp string to local timezone with ISO format

    Args:
        utc_time_str: UTC timestamp string (e.g., "2024-01-24 10:30:45")

    Returns:
        str: ISO formatted timestamp with timezone info (e.g., "2024-01-24T18:30:45+08:00")
        None: If conversion fails or input is None
    """
    if not utc_time_str:
        return None

    try:
        if isinstance(utc_time_str, datetime):
            dt = utc_time_str
        else:
            # Parse timestamp string - handle both with and without 'Z' suffix
            dt = datetime.fromisoformat(str(utc_time_str).replace('Z', '+00:00'))

        # If no timezone info, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # Convert to local timezone
        local_tz = get_timezone()
        dt_local = dt.astimezone(local_tz)

        # Return ISO format with timezone
        return dt_local.isoformat()
    except Exception as e:
        # If conversion fails, return original value
        print(f"Warning: Failed to convert timestamp '{utc_time_str}': {e}")
        return utc_time_str


def get_current_local_time() -> datetime:
    """Get current time in local timezone

    Returns:
        datetime: Current datetime with local timezone
    """
    return datetime.now(get_timezone())


def format_local_time(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format datetime to string in local timezone

    Args:
        dt: Datetime object to format
        fmt: Format string (default: "%Y-%m-%d %H:%M:%S")

    Returns:
        str: Formatted time string, or "-" if dt is None
    """
    if not dt:
        return "-"

    try:
        # Convert to local timezone if needed
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        local_tz = get_timezone()
        dt_local = dt.astimezone(local_tz)
        return dt_local.strftime(fmt)
    except Exception as e:
        print(f"Warning: Failed to format datetime: {e}")
        return str(dt)
