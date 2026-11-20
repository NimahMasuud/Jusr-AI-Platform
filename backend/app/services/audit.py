from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core import clock
from app.models.entities import AuditEvent

def record_event(db: Session, user, *, case_id, event_type, description, old_values=None, new_values=None, at=None):
    """Append an audit event with staff id, role and timestamp (R-01). Caller commits.
    `at` backdates the event (seeding only); normally the time is the demo-clock time."""
    event = AuditEvent(actor_id=user.id, actor_role=user.role.value, case_id=case_id, event_type=event_type,
                       description=description, old_values=old_values, new_values=new_values, occurred_at=at or clock.now())
    db.add(event)
    return event

def reject_and_log(db: Session, user, *, case_id, attempted, status_code, code, message):
    """Refuse an invalid action: nothing changes except a log entry (R-12)."""
    db.rollback()
    record_event(db, user, case_id=case_id, event_type="INVALID_ACTION_REJECTED", description=message,
                 new_values={"attempted": attempted, "code": code})
    db.commit()
    raise HTTPException(status_code, detail={"code": code, "message": message})

def record_patient_event(db: Session, *, case_id, event_type, description, new_values=None):
    """Audit event for an action taken through a patient secure link (no staff identity)."""
    event = AuditEvent(actor_id=None, actor_role="PATIENT", case_id=case_id, event_type=event_type,
                       description=description, new_values=new_values, occurred_at=clock.now())
    db.add(event)
    return event
