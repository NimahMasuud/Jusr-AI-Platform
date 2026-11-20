"""R-23: time limits, routing and message rules live in one settings store with a scope (global, facility or
specialty). Most specific wins: specialty, then facility, then global, then the built-in default below.
Every change is logged (R-03). Changing a value takes effect on the next check, with no deployment (A-28)."""
from datetime import datetime, timedelta
from app.core.config import settings as env
from app.models.entities import Setting, CaseStatus

# Time limit before OVERDUE, per status (Developer Guide Part 1). {"value": n, "unit": minutes|hours|days|working_days}
DEFAULT_LIMITS = {
    "NEW": (1, "working_days"), "AWAITING_CLASSIFICATION": (1, "working_days"), "URGENT_ROUTING": (2, "hours"),
    "NOTIFYING": (1, "working_days"), "AWAITING_ACK": (3, "days"), "AWAITING_CONFIRMATION": (7, "days"),
    "REFERRAL_PENDING": (3, "days"), "AWAITING_APPOINTMENT": (14, "days"), "AWAITING_TREATMENT": (14, "days"),
    "READY_TO_CLOSE": (2, "days"),
}
DEFAULTS: dict = {f"limit.{k}": {"value": v[0], "unit": v[1]} for k, v in DEFAULT_LIMITS.items()}
DEFAULTS.update({
    "urgent.acceptance_minutes": 120,       # R-29 placeholder: 2 hours to accept
    "urgent.escalation_minutes": 120,       # then 2 hours before the backup
    "referral.second_limit_days": 3,        # R-46: a second limit of 3 days before NOT_ACCEPTED_IN_TIME
    "consultation.limit": {"value": 1, "unit": "working_days"},
    "consultation.limit_urgent": {"value": 2, "unit": "hours"},
    "message.max_attempts": 4,              # R-33 placeholder: first attempt plus 3 retries
    "message.retry_minutes": [60, 300, 1080],  # ...over 24 hours (1 h, 5 h, 18 h after the previous attempt)
    "closure.unreachable_min_attempts": 3,  # R-55 placeholder
    "closure.unreachable_min_routes": 2,
    "closure.unreachable_window_days": 7,   # R-55: attempts must fall inside this window
    "reminder.ack_schedule_approved": False,  # R-32: the facility approves the reminder schedule once
    "feed.expected_interval_hours": None,   # R-26: unset means the feed monitor ignores the facility
    "baseline.m1_median_hours": 72, "baseline.m1_p90_hours": 168, "baseline.m2_acknowledged_share": 0.4,
    "baseline.m2_understood_share": 0.5, "baseline.m3_referral_accepted_share": 0.55, "baseline.m3_attended_share": 0.6,
    "baseline.m4_treatment_median_hours": 720, "baseline.m5_dropoff_share": 0.3,
})
LIMIT_UNITS = ("minutes", "hours", "days", "working_days")

def scope_for(facility_id=None, specialty=None) -> list[str]:
    scopes = []
    if specialty: scopes.append(f"specialty:{specialty}")
    if facility_id: scopes.append(f"facility:{facility_id}")
    scopes.append("global")
    return scopes

def get(db, key: str, *, facility_id=None, specialty=None, default=None):
    rows = {r.scope: r.value for r in db.query(Setting).filter(Setting.key == key, Setting.scope.in_(scope_for(facility_id, specialty))).all()}
    for scope in scope_for(facility_id, specialty):
        if scope in rows:
            return rows[scope]
    return DEFAULTS.get(key, default) if default is None else default

def get_int(db, key, **kw) -> int | None:
    v = get(db, key, **kw)
    return None if v is None else int(v)

def validate(key: str, value):
    """Return an error message, or None if the value is acceptable for the key."""
    if key not in DEFAULTS:
        return f"Unknown setting {key}"
    default = DEFAULTS[key]
    if isinstance(default, dict):  # a limit
        if not isinstance(value, dict) or set(value) != {"value", "unit"} or value["unit"] not in LIMIT_UNITS or not isinstance(value["value"], (int, float)) or isinstance(value["value"], bool) or value["value"] <= 0:
            return f"{key} must be an object {{value > 0, unit in {list(LIMIT_UNITS)}}}"
    elif isinstance(default, list):
        if not isinstance(value, list) or not value or not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value):
            return f"{key} must be a non-empty list of positive whole numbers"
    elif isinstance(default, bool):
        return None
    elif isinstance(default, int):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            return f"{key} must be a positive whole number"
    elif isinstance(default, float):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            return f"{key} must be a non-negative number"
    elif default is None:  # optional positive hours
        if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0):
            return f"{key} must be null or a positive number"
    return None

def is_working_day(d: datetime) -> bool:
    return d.weekday() < 5  # Monday to Friday; facility working days are a later refinement

def add_limit(start: datetime, spec) -> datetime:
    """start + a limit expressed as {"value", "unit"}. Working days skip Saturday and Sunday."""
    value, unit = spec["value"], spec["unit"]
    if unit == "minutes": return start + timedelta(minutes=value)
    if unit == "hours": return start + timedelta(hours=value)
    if unit == "days": return start + timedelta(days=value)
    due, remaining = start, int(value)
    while remaining > 0:
        due += timedelta(days=1)
        if is_working_day(due):
            remaining -= 1
    return due

def status_limit(db, status, *, facility_id=None):
    s = status.value if isinstance(status, CaseStatus) else status
    return get(db, f"limit.{s}", facility_id=facility_id)

def due_for(db, status, start: datetime, *, facility_id=None) -> datetime | None:
    s = status.value if isinstance(status, CaseStatus) else status
    if s == "CLOSED":
        return None
    return add_limit(start, status_limit(db, s, facility_id=facility_id))

def retry_delay(db, attempts: int, *, facility_id=None) -> timedelta:
    minutes = get(db, "message.retry_minutes", facility_id=facility_id) or [5]
    return timedelta(minutes=minutes[min(attempts - 1, len(minutes) - 1)])
