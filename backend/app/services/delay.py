"""R-18: reason-for-delay codes. An OVERDUE case needs a follow-up with a code (A-10); a missed appointment does too (R-47)."""
from app.models.entities import DelayReason

def codes() -> list[str]:
    return [r.value for r in DelayReason]
