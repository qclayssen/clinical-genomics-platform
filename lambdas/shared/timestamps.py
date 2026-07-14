"""ISO 8601 UTC timestamp utilities.

All timestamps are formatted to seconds precision in UTC: YYYY-MM-DDTHH:MM:SSZ
"""

from datetime import datetime, timezone


def format_iso8601(dt: datetime) -> str:
    """Format a datetime as ISO 8601 UTC with seconds precision.

    Truncates microseconds and converts to UTC if timezone-aware.
    Naive datetimes are assumed to be UTC.

    Returns:
        String in format YYYY-MM-DDTHH:MM:SSZ
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    # Truncate to seconds
    dt = dt.replace(microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def now_iso8601() -> str:
    """Return the current UTC time formatted as ISO 8601 with seconds precision."""
    return format_iso8601(datetime.now(timezone.utc))
