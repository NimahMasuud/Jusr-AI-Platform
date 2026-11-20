"""Urgent specialty routing.

An URGENT case is routed to a receiving clinician whose specialty matches the case's required specialty.
  stage 0  clinician has `first limit` minutes to accept
  stage 1  limit passed: the coordinator is alerted (task) and the clinician may still accept; `second limit` minutes more
  stage 2  second limit passed: case goes to a qualified backup clinician, who gets a fresh `first limit`
  EXCEPTION  no qualified clinician exists, or the backup also let the limit pass; the coordinator must act
Every step writes an audit event.
"""
from datetime import timedelta
from fastapi import HTTPException
from app.core import clock
from app.models.entities import Case, CaseStatus, Priority, Role, RoutingStatus, SpecialtyBackup, Task, User
from app.services import settings_store
from app.services.audit import record_event, reject_and_log
from app.services.tasks import create_task

# Actor for work done by the scheduler: no user id, role SYSTEM.
from app.services.state_machine import SYSTEM as SYSTEM_ACTOR
ROUTING_TASKS = ("URGENT_ROUTING_ESCALATED", "URGENT_ROUTING_EXCEPTION")

def _now():
    return clock.now()

def default_limits(db, case, specialty=None):
    spec = specialty or case.required_specialty
    return (settings_store.get_int(db, "urgent.acceptance_minutes", facility_id=case.facility_id, specialty=spec),
            settings_store.get_int(db, "urgent.escalation_minutes", facility_id=case.facility_id, specialty=spec))

def normalize_specialty(value: str | None) -> str | None:
    return "_".join(value.strip().upper().split()) if value and value.strip() else None

def qualified_clinicians(db, specialty: str, *, exclude=(), prefer_facility=None) -> list[User]:
    q = db.query(User).filter(User.role == Role.RECEIVING_CLINICIAN, User.is_active.is_(True), User.specialty == specialty)
    if exclude:
        q = q.filter(User.id.notin_(list(exclude)))
    rows = q.order_by(User.id).all()
    rows.sort(key=lambda u: u.facility_id != prefer_facility)  # stable: same-facility clinicians first
    return rows

def validate_clinician(db, clinician_id: str, specialty: str) -> User:
    c = db.get(User, clinician_id)
    if not c:
        raise HTTPException(404, "Receiving clinician not found")
    if c.role != Role.RECEIVING_CLINICIAN or not c.is_active:
        raise HTTPException(422, detail={"code": "INVALID_ASSIGNEE", "message": "Must be an active receiving clinician"})
    if c.specialty != specialty:
        raise HTTPException(422, detail={"code": "SPECIALTY_MISMATCH", "message": f"Clinician specialty {c.specialty or 'none'} does not match required specialty {specialty}",
                                         "requiredSpecialty": specialty, "clinicianSpecialty": c.specialty})
    return c

def _close_routing_tasks(db, case: Case, now) -> None:
    for t in db.query(Task).filter(Task.case_id == case.id, Task.type.in_(ROUTING_TASKS), Task.status == "OPEN").all():
        t.status = "DONE"; t.completed_at = now  # closed by the system, no staff member

def summary(db, case: Case) -> dict | None:
    """Routing block for API responses; None when the case was never routed."""
    if not case.routing_status:
        return None
    clinician = db.get(User, case.routed_clinician_id) if case.routed_clinician_id else None
    return {"status": case.routing_status, "stage": case.routing_stage, "escalatedToCoordinator": case.routing_stage >= 1,
            "requiredSpecialty": case.required_specialty,
            "routedClinician": {"id": clinician.id, "displayName": clinician.display_name, "specialty": clinician.specialty} if clinician else None,
            "startedAt": case.routing_started_at, "dueAt": case.routing_due_at, "acceptedAt": case.routing_accepted_at,
            "exceptionReason": case.routing_exception_reason,
            "firstLimitMinutes": case.routing_first_limit_minutes, "secondLimitMinutes": case.routing_second_limit_minutes}

def _enter_exception(db, actor, case: Case, reason: str, now) -> None:
    previous = case.routed_clinician_id
    case.routing_status = RoutingStatus.EXCEPTION.value; case.routed_clinician_id = None; case.routing_due_at = None
    case.routing_exception_reason = reason; case.flag_exception = True
    create_task(db, case, "URGENT_ROUTING_EXCEPTION", "Urgent case has no clinician to accept it", reason, source_ref=case.id)
    record_event(db, actor, case_id=case.id, event_type="URGENT_ROUTING_EXCEPTION", description="Urgent routing exception",
                 old_values={"routedClinicianId": previous}, new_values={"status": case.routing_status, "reason": reason, "requiredSpecialty": case.required_specialty})

def route_case(db, actor, case: Case, *, clinician_id=None, specialty=None, first_limit=None, second_limit=None) -> Case:
    now = _now()
    if case.priority != Priority.URGENT:
        reject_and_log(db, actor, case_id=case.id, attempted="routing:route", status_code=409, code="CASE_NOT_URGENT", message="Only an URGENT case can be routed for urgent acceptance")
    if case.status == CaseStatus.CLOSED:
        reject_and_log(db, actor, case_id=case.id, attempted="routing:route", status_code=409, code="CASE_CLOSED", message="Cannot route a closed case")
    if case.status != CaseStatus.URGENT_ROUTING:
        reject_and_log(db, actor, case_id=case.id, attempted="routing:route", status_code=409, code="INVALID_STATUS_TRANSITION",
                       message=f"Urgent routing starts when a clinician marks the case urgent (T4); the case is {case.status.value}")
    if case.routing_status in (RoutingStatus.AWAITING_ACCEPTANCE.value, RoutingStatus.ACCEPTED.value):
        reject_and_log(db, actor, case_id=case.id, attempted="routing:route", status_code=409, code="ROUTING_ALREADY_ACTIVE", message=f"Routing is already {case.routing_status}")
    required = normalize_specialty(specialty) or case.required_specialty
    if not required:
        raise HTTPException(422, detail={"code": "SPECIALTY_REQUIRED", "message": "A required specialty is needed to route an urgent case"})
    clinician = validate_clinician(db, clinician_id, required) if clinician_id else None
    if clinician is None:
        found = qualified_clinicians(db, required, prefer_facility=case.facility_id)
        clinician = found[0] if found else None
    case.required_specialty = required
    d1, d2 = default_limits(db, case, required)
    case.routing_first_limit_minutes = first_limit or d1
    case.routing_second_limit_minutes = second_limit or d2
    case.routing_started_at = now; case.routing_stage = 0; case.routing_accepted_at = None; case.routing_exception_reason = None
    case.routing_tried = [clinician.id] if clinician else []
    case.updated_at = now
    if clinician is None:
        case.routed_clinician_id = None
        _enter_exception(db, actor, case, f"No qualified receiving clinician with specialty {required}", now)
        return case
    case.routing_status = RoutingStatus.AWAITING_ACCEPTANCE.value; case.routed_clinician_id = clinician.id
    case.routing_due_at = now + timedelta(minutes=case.routing_first_limit_minutes)
    record_event(db, actor, case_id=case.id, event_type="URGENT_CASE_ROUTED", description="Urgent case routed to a specialty clinician",
                 new_values={"routedClinicianId": clinician.id, "requiredSpecialty": required, "dueAt": case.routing_due_at.isoformat(),
                             "firstLimitMinutes": case.routing_first_limit_minutes, "secondLimitMinutes": case.routing_second_limit_minutes, "auto": clinician_id is None})
    return case

def reassign_case(db, actor, case: Case, *, clinician_id: str, reason: str) -> Case:
    now = _now()
    if case.routing_status not in (RoutingStatus.AWAITING_ACCEPTANCE.value, RoutingStatus.EXCEPTION.value):
        reject_and_log(db, actor, case_id=case.id, attempted="routing:reassign", status_code=409, code="INVALID_ROUTING_STATE",
                       message=f"Cannot reassign routing that is {case.routing_status or 'not started'}")
    clinician = validate_clinician(db, clinician_id, case.required_specialty)
    previous = case.routed_clinician_id
    case.routing_tried = sorted(set(case.routing_tried or []) | {clinician.id})
    case.routed_clinician_id = clinician.id; case.routing_status = RoutingStatus.AWAITING_ACCEPTANCE.value
    case.routing_stage = 0; case.routing_exception_reason = None; case.updated_at = now
    case.routing_due_at = now + timedelta(minutes=case.routing_first_limit_minutes or default_limits(db, case)[0])
    _close_routing_tasks(db, case, now)
    record_event(db, actor, case_id=case.id, event_type="URGENT_ROUTING_REASSIGNED", description="Urgent routing reassigned by staff",
                 old_values={"routedClinicianId": previous}, new_values={"routedClinicianId": clinician.id, "reason": reason, "dueAt": case.routing_due_at.isoformat()})
    return case

def accept_case(db, user, case: Case) -> Case:
    now = _now()
    if case.routing_status != RoutingStatus.AWAITING_ACCEPTANCE.value:
        reject_and_log(db, user, case_id=case.id, attempted="routing:accept", status_code=409, code="INVALID_ROUTING_STATE", message=f"Cannot accept: routing is {case.routing_status or 'not started'}")
    from app.services import state_machine as sm
    stage = case.routing_stage
    sm.apply(db, user, case, "T5", ctx={"clinician": user}, at=now, flags={"exception": False},
             details={"routedClinicianId": user.id, "stage": stage, "requiredSpecialty": case.required_specialty,
                      "acceptedAt": now.isoformat()}, event_type="URGENT_CASE_ACCEPTED")
    case.routing_status = RoutingStatus.ACCEPTED.value; case.routing_accepted_at = now; case.routing_due_at = None
    _close_routing_tasks(db, case, now)
    return case

def _named_backup_id(db, specialty: str | None) -> str | None:
    if not specialty:
        return None
    row = db.query(SpecialtyBackup).filter(SpecialtyBackup.specialty == specialty).first()
    return row.clinician_id if row else None


def _named_backup(db, case: Case) -> User | None:
    """R-29: the named backup for the case's specialty, if set and still valid."""
    row = db.query(SpecialtyBackup).filter(SpecialtyBackup.specialty == case.required_specialty).first()
    if not row:
        return None
    user = db.get(User, row.clinician_id)
    if not user or not user.is_active or user.role != Role.RECEIVING_CLINICIAN or user.specialty != case.required_specialty:
        return None
    if user.id in (case.routing_tried or []):
        return None
    return user


def process_due_routing(db, actor, case_query=None, now=None) -> dict:
    """Apply expired acceptance limits. Safe to call repeatedly; each case advances one step per call."""
    now = now or _now()
    q = case_query if case_query is not None else db.query(Case)
    due = q.filter(Case.routing_status == RoutingStatus.AWAITING_ACCEPTANCE.value, Case.routing_due_at <= now).with_for_update(skip_locked=True).all()
    counts = {"processed": 0, "escalated": 0, "reassigned": 0, "exceptions": 0}
    for case in due:
        counts["processed"] += 1
        d1, d2 = default_limits(db, case)
        first = case.routing_first_limit_minutes or d1
        second = case.routing_second_limit_minutes or d2
        if case.routing_stage == 0:
            case.flag_exception = True  # R-13: not accepted in time is an EXCEPTION, escalated to the coordinator
            case.routing_stage = 1; case.routing_due_at = now + timedelta(minutes=second); case.updated_at = now
            create_task(db, case, "URGENT_ROUTING_ESCALATED", "Urgent case not accepted within the time limit",
                        f"Routed clinician has not accepted. Reassign it, or it goes to a backup clinician at {case.routing_due_at.isoformat()}.", source_ref=case.id)
            record_event(db, actor, case_id=case.id, event_type="URGENT_ROUTING_ESCALATED", description="Acceptance limit expired; escalated to the coordinator",
                         new_values={"routedClinicianId": case.routed_clinician_id, "nextDueAt": case.routing_due_at.isoformat()})
            counts["escalated"] += 1
        elif case.routing_stage == 1:
            backup = _named_backup(db, case)
            if backup is None:
                backups = qualified_clinicians(db, case.required_specialty, exclude=case.routing_tried or [], prefer_facility=case.facility_id)
                backup = backups[0] if backups else None
            if backup:
                previous = case.routed_clinician_id
                case.routed_clinician_id = backup.id; case.routing_stage = 2; case.routing_tried = list(case.routing_tried or []) + [backup.id]
                case.routing_due_at = now + timedelta(minutes=first); case.updated_at = now
                record_event(db, actor, case_id=case.id, event_type="URGENT_ROUTING_REASSIGNED", description="Second limit expired; routed to the specialty backup clinician",
                             old_values={"routedClinicianId": previous}, new_values={"routedClinicianId": backup.id, "reason": "SECOND_LIMIT_EXPIRED", "dueAt": case.routing_due_at.isoformat(),
                                                                                    "namedBackup": _named_backup_id(db, case.required_specialty) == backup.id})
                counts["reassigned"] += 1
            else:
                case.updated_at = now
                _enter_exception(db, actor, case, f"Second limit expired and no qualified backup clinician with specialty {case.required_specialty} is available", now)
                counts["exceptions"] += 1
        else:
            case.updated_at = now
            _enter_exception(db, actor, case, "The backup clinician did not accept within the time limit", now)
            counts["exceptions"] += 1
    return counts
