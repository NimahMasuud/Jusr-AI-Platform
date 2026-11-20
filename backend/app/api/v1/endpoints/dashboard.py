from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core import clock
from app.services import state_machine as sm
from app.core.database import get_db
from app.core.permissions import visible_cases
from app.api.v1.deps import current_user
from app.models.entities import (
    Case,
    Priority,
    CaseStatus,
    Closure,
    Referral,
    Role,
    RoutingStatus,
    User,
    Facility,
    Patient,
    Screening,
    AuditEvent,
)

router = APIRouter()

REFERRAL_STATUSES = ("SENT", "ACCEPTED", "DECLINED", "NOT_ACCEPTED_IN_TIME")

def _referral_counts(referrals) -> dict:
    out = {"total": len(referrals)}
    for status in REFERRAL_STATUSES:
        out[status.lower()] = sum(r.status == status for r in referrals)
    return out

def _open(rows):
    return [c for c in rows if c.status != CaseStatus.CLOSED]


def _coordinator_view(db, user, now):
    # Only cases visible to this Coordinator are included.
    rows = visible_cases(db.query(Case), user).all()

    sm.sync_overdue(
        db,
        [c for c in rows if c.status != CaseStatus.CLOSED],
        now,
    )
    db.commit()

    active = _open(rows)

    # 1. Cases grouped by their actual workflow status.
    by_status = {}
    for case in active:
        status = case.status.value
        by_status[status] = by_status.get(status, 0) + 1

    # 2. Referral counts from visible referral records.
    referrals = visible_cases(
        db.query(Referral).join(
            Case, Referral.case_id == Case.id
        ),
        user,
    ).all()

    referral_counts = _referral_counts(referrals)

    # Frontend-compatible referral names.
    referral_overview = {
        "total": referral_counts["total"],
        "pending": referral_counts.get("sent", 0),
        "accepted": referral_counts.get("accepted", 0),
        "rejected": referral_counts.get("declined", 0),
    }

    # 3. Priority queue from actual active cases.
    priority_rows = [
        c for c in active
        if (
            c.priority in (Priority.URGENT, Priority.HIGH)
            or c.flag_overdue
            or c.flag_exception
            or c.flag_message_failed
            or c.flag_not_explained
            or c.flag_data_missing
        )
    ]

    priority_rows.sort(
        key=lambda c: (
            c.priority != Priority.URGENT,
            not c.flag_overdue,
            c.due_at is None,
            c.due_at or now,
        )
    )

    priority_cases = []

    for case in priority_rows[:8]:
        patient = db.get(Patient, case.patient_id)
        screening = (
            db.get(Screening, case.screening_id)
            if case.screening_id else None
        )
        owner = (
            db.get(User, case.coordinator_id)
            if case.coordinator_id else None
        )

        priority_cases.append({
            "id": case.id,
            "caseId": case.case_number,
            "patientLabel": (
                patient.display_label if patient
                else "Unknown patient"
            ),
            "age": patient.age_years if patient else None,
            "screeningType": (
                screening.screening_type if screening else None
            ),
            "screeningResult": (
                screening.outcome if screening else None
            ),
            "priority": case.priority.value,
            "status": case.status.value,
            "nextStep": (
                case.next_action_label
                or case.next_action_code
                or "No next action recorded"
            ),
            "nextActionCode": case.next_action_code,
            "owner": (
                owner.display_name if owner else "Unassigned"
            ),
            "dueAt": case.due_at,
            "overdue": case.flag_overdue,
        })

    # 4. Screening-to-care progress.
    total_active = len(active)

    care_progress = [
        {
            "label": status.replace("_", " ").title(),
            "count": count,
            "percentage": (
                round((count / total_active) * 100)
                if total_active else 0
            ),
        }
        for status, count in by_status.items()
    ]

    # 5. Recent activity from the existing append-only audit log.
    visible_case_ids = [case.id for case in rows]

    activity_query = db.query(AuditEvent).filter(
        AuditEvent.case_id.in_(visible_case_ids)
    ) if visible_case_ids else None

    recent_events = (
        activity_query
        .order_by(AuditEvent.occurred_at.desc())
        .limit(10)
        .all()
        if activity_query is not None else []
    )

    recent_activity = []

    for event in recent_events:
        actor = (
            db.get(User, event.actor_id)
            if event.actor_id else None
        )

        recent_activity.append({
            "id": event.id,
            "description": event.description,
            "actor": (
                actor.display_name if actor
                else "System"
            ),
            "actorRole": event.actor_role,
            "eventType": event.event_type,
            "timestamp": event.occurred_at,
        })

    return {
        "stats": {
            "activeCases": len(active),
            "urgentCases": sum(
                c.priority == Priority.URGENT for c in active
            ),
            "overdueCases": sum(
                c.flag_overdue for c in active
            ),
            "unassignedCases": sum(
                c.coordinator_id is None for c in active
            ),
            "exceptionCases": sum(
                c.flag_exception for c in active
            ),
            "messageFailedCases": sum(
                c.flag_message_failed for c in active
            ),
            "notExplainedCases": sum(
                c.flag_not_explained for c in active
            ),
            "dataMissingCases": sum(
                c.flag_data_missing for c in active
            ),
            "missingDelayReason": sum(
                c.flag_overdue for c in active
            ),
            "awaitingUrgentAcceptance": sum(
                c.routing_status
                == RoutingStatus.AWAITING_ACCEPTANCE.value
                for c in active
            ),
            "urgentRoutingExceptions": sum(
                c.routing_status == RoutingStatus.EXCEPTION.value
                for c in active
            ),
        },
        "byStatus": by_status,
        "priorityCases": priority_cases,
        "careProgress": care_progress,
        "referrals": referral_overview,
        "recentActivity": recent_activity,
    }


def _referring_view(db, user, now):
    visible = visible_cases(db.query(Case), user).all()

    owned = [c for c in visible if c.coordinator_id == user.id]

    sm.sync_overdue(
        db,
        [c for c in owned if c.status != CaseStatus.CLOSED],
        now,
    )
    db.commit()

    active = _open(owned)
    ids = [c.id for c in owned]
    visible_ids = [c.id for c in visible]

    referrals = (
        db.query(Referral)
        .filter(Referral.case_id.in_(ids))
        .all()
        if ids else []
    )

    # Closures specifically assigned to this clinician for second sign-off.
    pending_closures_query = (
        db.query(Closure)
        .join(Case, Closure.case_id == Case.id)
        .filter(
            Closure.second_approver_id == user.id,
            Closure.status == "PENDING_SIGNOFF",
        )
    )

    if user.facility_id:
        pending_closures_query = pending_closures_query.filter(
            Case.facility_id == user.facility_id
        )
    else:
        pending_closures_query = pending_closures_query.filter(
            Case.id.in_(visible_ids)
        )

    pending_closures = (
        pending_closures_query
        .order_by(Closure.requested_at.desc())
        .all()
    )

    closure_approvals = []

    for closure in pending_closures:
        case = db.get(Case, closure.case_id)
        if not case:
            continue

        patient = db.get(Patient, case.patient_id)
        requester = (
            db.get(User, closure.closed_by_id)
            if closure.closed_by_id else None
        )

        closure_approvals.append({
            "id": case.id,
            "caseNumber": case.case_number,
            "patientLabel": (
                patient.display_label if patient
                else "Unknown patient"
            ),
            "closureType": closure.closure_type,
            "reason": closure.reason,
            "requestedBy": (
                requester.display_name if requester
                else "Authorised staff"
            ),
            "requestedAt": closure.requested_at,
        })

    return {
        "stats": {
            "assignedCases": len(active),
            "urgentCases": sum(
                c.priority == Priority.URGENT for c in active
            ),
            "overdueCases": sum(c.flag_overdue for c in active),
            "missingDelayReason": sum(c.flag_overdue for c in active),
            "closuresAwaitingSignOff": len(closure_approvals),
        },
        "referrals": _referral_counts(referrals),
        "closureApprovals": closure_approvals,
    }

def _receiving_view(db, user, now):
    routed = db.query(Case).filter(Case.routed_clinician_id == user.id).all()
    urgent_routing = {"awaitingAcceptance": sum(c.routing_status == RoutingStatus.AWAITING_ACCEPTANCE.value for c in routed),
                      "accepted": sum(c.routing_status == RoutingStatus.ACCEPTED.value for c in routed)}
    if not user.facility_id:
        return {"referrals": {"incoming": 0, "pending": 0, "accepted": 0, "urgent": 0, "assignedToMe": 0, "outstandingDecisions": 0}, "urgentRouting": urgent_routing}
    rows = db.query(Referral, Case).join(Case, Referral.case_id == Case.id).filter(Referral.receiving_facility_id == user.facility_id).all()
    return {"referrals": {
        "incoming": len(rows),
        "pending": sum(r.status == "SENT" for r, _ in rows),
        "accepted": sum(r.status == "ACCEPTED" for r, _ in rows),
        "urgent": sum(r.status in ("SENT", "ACCEPTED") and c.priority == Priority.URGENT for r, c in rows),
        "assignedToMe": sum(r.receiving_clinician_id == user.id and r.status in ("SENT", "ACCEPTED") for r, _ in rows),
        "outstandingDecisions": sum(r.status == "SENT" and r.receiving_clinician_id in (None, user.id) for r, _ in rows),
    }, "urgentRouting": urgent_routing}

def _facility_admin_view(db, user, now):
    """Staff access and facility connection only. No patient or clinical case data (R-09)."""
    facility = db.get(Facility, user.facility_id) if user.facility_id else None
    staff = db.query(User).filter(
        User.facility_id == user.facility_id,
        User.role.in_((Role.COORDINATOR, Role.REFERRING_CLINICIAN, Role.RECEIVING_CLINICIAN, Role.FACILITY_ADMIN)),
    ).all() if user.facility_id else []
    by_role = {}
    for u in staff:
        by_role[u.role.value] = by_role.get(u.role.value, 0) + 1
    return {
        "facility": {"id": facility.id, "name": facility.name, "code": facility.code} if facility else None,
        "staffAccess": {"totalStaff": len(staff), "activeStaff": sum(u.is_active for u in staff), "inactiveStaff": sum(not u.is_active for u in staff), "byRole": by_role},
        "connection": {"status": facility.connection_status if facility else "UNKNOWN", "connectorType": facility.connector_type if facility else None,
                       "lastEventAt": facility.last_event_at if facility else None},
    }

VIEWS = {
    Role.COORDINATOR: _coordinator_view,
    Role.NATIONAL_ADMIN: _coordinator_view,
    Role.AI_SERVICE: _coordinator_view,
    Role.REFERRING_CLINICIAN: _referring_view,
    Role.RECEIVING_CLINICIAN: _receiving_view,
    Role.FACILITY_ADMIN: _facility_admin_view,
}

@router.get("/summary")
def dashboard_summary(db: Session = Depends(get_db), user=Depends(current_user)):
    view = VIEWS.get(user.role)
    if view is None:
        raise HTTPException(403, "Insufficient permissions")
    now = clock.now()
    data = view(db, user, now)
    data.update({"role": user.role.value, "generatedAt": now})
    if user.role != Role.FACILITY_ADMIN:
        data["demoClock"] = {"active": clock.is_active(), "offsetMinutes": clock.offset_minutes()}
    return {"success": True, "data": data, "meta": {}}
