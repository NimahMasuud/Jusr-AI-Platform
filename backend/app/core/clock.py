"""R-66: a demo clock. In the demo environment a presenter can move time forward so overdue cases appear
without waiting. All workflow time limits read the clock through now(); a banner flag is exposed while an offset is active."""
from datetime import datetime, timedelta, timezone

_offset = timedelta(0)

def now() -> datetime:
    return datetime.now(timezone.utc) + _offset

def offset_minutes() -> float:
    return _offset.total_seconds() / 60

def is_active() -> bool:
    return _offset != timedelta(0)

def advance(minutes: float) -> None:
    global _offset
    _offset += timedelta(minutes=minutes)

def reset() -> None:
    global _offset
    _offset = timedelta(0)
