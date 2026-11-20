from math import ceil
from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.core import clock
from app.core.database import get_db
from app.api.v1.deps import worklist_user
from app.core.permissions import visible_cases
from app.services import routing, state_machine as sm
from app.models.entities import (
    Case, Patient, Screening, Facility, User, Priority,
    CaseStatus, RoutingStatus, Closure,
)

router = APIRouter()

TABS = {"ALL": None, "URGENT": Case.priority == Priority.URGENT, "OVERDUE": Case.flag_overdue.is_(True), "EXCEPTIONS": Case.flag_exception.is_(True),
        "UNASSIGNED": Case.coordinator_id.is_(None), "MESSAGE_FAILED": Case.flag_message_failed.is_(True), "NOT_EXPLAINED": Case.flag_not_explained.is_(True),
        "DATA_MISSING": Case.flag_data_missing.is_(True)}

def _initials(label: str) -> str:
    parts = [p for p in label.replace(".", " ").split() if p[:1].isalpha()]
    return "".join(p[0].upper() for p in parts[:3]) or label[:2].upper()

def _hours(delta):
    return round(delta.total_seconds() / 3600, 2)

@router.get("")
def get_worklist(page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100), search: str | None = None,
                 tab: Literal["ALL", "URGENT", "OVERDUE", "EXCEPTIONS", "UNASSIGNED", "MESSAGE_FAILED", "NOT_EXPLAINED", "DATA_MISSING"] = "ALL",
                 priority: Priority | None = None, status: CaseStatus | None = None, includeClosed: bool = False,
                 facilityId: str | None = None, coordinatorId: str | None = None, ownerId: str | None = None,
                 screeningType: str | None = None, pathway: str | None = None, overdue: bool | None = None, routingStatus: RoutingStatus | None = None,
                 sortBy: Literal["default", "dueAt", "updatedAt", "createdAt", "priority"] = "default", sortOrder: Literal["asc", "desc"] = "asc",
                 db: Session = Depends(get_db), user=Depends(worklist_user)):
    """Worklist (section 11). Tabs: All, Urgent, Overdue, Exceptions, Unassigned, Message failed, Not explained, Data missing.
    Default order: urgent first, then longest overdue."""
    now = clock.now()
    base = visible_cases(db.query(Case), user)
    sm.sync_overdue(db, base.filter(Case.status != CaseStatus.CLOSED, Case.flag_overdue.is_(False), Case.due_at < now).all(), now)
    db.commit()
    q = db.query(Case).join(Patient, Case.patient_id == Patient.id).outerjoin(Screening, Case.screening_id == Screening.id)
    visible_case_ids = visible_cases(
        db.query(Case.id),
        user,
    ).subquery()

    pending_approval_case_ids = (
        db.query(Closure.case_id)
        .filter(
            Closure.second_approver_id == user.id,
            Closure.status == "PENDING_SIGNOFF",
        )
        .subquery()
    )

    q = q.filter(
        or_(
            Case.id.in_(visible_case_ids),
            Case.id.in_(pending_approval_case_ids),
        )
    )
    if not includeClosed and status is None: q = q.filter(Case.status != CaseStatus.CLOSED)
    if TABS[tab] is not None: q = q.filter(TABS[tab])
    if facilityId: q = q.filter(Case.facility_id == facilityId)
    if coordinatorId or ownerId: q = q.filter(Case.coordinator_id == (ownerId or coordinatorId))
    if priority: q = q.filter(Case.priority == priority)
    if status: q = q.filter(Case.status == status)
    if screeningType or pathway: q = q.filter(Screening.screening_type.ilike(f"%{screeningType or pathway}%"))
    if routingStatus: q = q.filter(Case.routing_status == routingStatus.value)
    if overdue is True: q = q.filter(Case.flag_overdue.is_(True))
    if overdue is False: q = q.filter(Case.flag_overdue.is_(False))
    if search:
        term = f"%{search}%"
        q = q.filter(or_(Case.case_number.ilike(term), Case.tracker_id.ilike(term), Patient.display_label.ilike(term)))
    all_rows = q.all()
    total = len(all_rows)
    summary = {"totalCases": total, "urgentCases": sum(c.priority == Priority.URGENT for c in all_rows), "overdueCases": sum(c.flag_overdue for c in all_rows),
               "unassignedCases": sum(c.coordinator_id is None for c in all_rows), "exceptionCases": sum(c.flag_exception for c in all_rows),
               "messageFailedCases": sum(c.flag_message_failed for c in all_rows), "notExplainedCases": sum(c.flag_not_explained for c in all_rows),
               "dataMissingCases": sum(c.flag_data_missing for c in all_rows)}
    far = now.replace(year=now.year + 100)
    if sortBy == "default":
        all_rows.sort(key=lambda c: (c.priority != Priority.URGENT, not c.flag_overdue, c.due_at or far, c.id))
    else:
        keys = {"dueAt": lambda c: c.due_at or far, "updatedAt": lambda c: c.updated_at, "createdAt": lambda c: c.created_at, "priority": lambda c: c.priority.value}
        all_rows.sort(key=keys[sortBy], reverse=sortOrder == "desc")
    rows = all_rows[(page - 1) * pageSize: page * pageSize]
    results = []
    for c in rows:
        patient = db.get(Patient, c.patient_id)
        screening = db.get(Screening, c.screening_id) if c.screening_id else None
        owner = db.get(User, c.coordinator_id) if c.coordinator_id else None
        facility = db.get(Facility, c.facility_id)
        closure = (
            db.query(Closure)
            .filter(Closure.case_id == c.id)
            .order_by(Closure.requested_at.desc())
            .first()
        )

        closure_requester = (
            db.get(User, closure.closed_by_id)
            if closure and closure.closed_by_id
            else None
        )
        closure_approver = (
            db.get(User, closure.second_approver_id)
            if closure and closure.second_approver_id
            else None
        )

        closure_out = (
            {
                "id": closure.id,
                "status": closure.status,
                "closureType": closure.closure_type,
                "reason": closure.reason,
                "closedById": closure.closed_by_id,
                "closedByName": (
                    closure_requester.display_name if closure_requester else None
                ),
                "secondApproverId": closure.second_approver_id,
                "secondApproverName": (
                    closure_approver.display_name if closure_approver else None
                ),
                "secondSignOffById": closure.second_signoff_by_id,
                "requestedAt": closure.requested_at,
                "closedAt": closure.closed_at,
            }
            if closure
            else None
        )
        owner_out = {"id": owner.id, "displayName": owner.display_name, "role": owner.role.value} if owner else None
        results.append({
            "id": c.id, "caseId": c.case_number, "trackerId": c.tracker_id,
            "patient": {
                "id": patient.id,
                "recordNumber": patient.record_number,
                "displayLabel": patient.display_label,
                "ageYears": patient.age_years,
                "sex": patient.sex,
            },
            "patientInitials": _initials(patient.display_label),
            "screening": ({"id": screening.id, "type": screening.screening_type, "outcome": screening.outcome, "displayLabel": screening.display_label} if screening else None),
            "priority": c.priority.value, "status": c.status.value, "closure": closure_out, "flags": sm.flags_of(c),
            "assignedCoordinator": owner_out, "owner": owner_out,
            "facility": {"id": facility.id, "name": facility.name},
            "nextAction": ({"code": c.next_action_code, "label": c.next_action_label} if c.next_action_code or c.next_action_label else None),
            "dueAt": c.due_at, "updatedAt": c.updated_at,
            "timeInStatusHours": _hours(now - c.status_entered_at) if c.status_entered_at else None,
            "timeLeftHours": _hours(c.due_at - now) if c.due_at else None,
            "delayReason": ({"code": c.delay_reason_code, "note": c.delay_reason_note, "recordedAt": c.delay_reason_recorded_at} if c.delay_reason_code else None),
            "delayReasonRequired": c.flag_overdue,
            # Urgent routing (canonical block) and flat aliases for the frontend's current field names
            "specialty": c.required_specialty, "routingStatus": c.routing_status, "routing": routing.summary(db, c),
            "patientLabel": patient.display_label, "age": patient.age_years, "sex": patient.sex,
            "screeningType": screening.screening_type if screening else None,
            "assignedTo": owner.display_name if owner else None
        })
    return {"success": True, "data": {"summary": summary, "tab": tab, "cases": results, "total": total, "page": page, "pageSize": pageSize, "totalPages": ceil(total / pageSize) if total else 0}, "meta": {}}
