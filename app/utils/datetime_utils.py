from datetime import datetime
from typing import Any


def format_datetime_local(value: Any) -> str:
    """Convert a UTC-aware datetime to local time and format it."""
    if not isinstance(value, datetime):
        return str(value) if value is not None else ''
    return value.astimezone().strftime('%Y-%m-%d %H:%M:%S')
