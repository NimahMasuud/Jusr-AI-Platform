from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core import clock
from app.core.database import get_db
from app.api.v1.deps import clinical_user, worklist_user
from app.core.permissions import GLOBAL_ROLES, ASSIGN_ROLES, CREATE_ROLES, visible_cases, can_view_case, can_modify_case
from app.models.entities import (Appointment, AuditEvent, Case, CaseStatus, Closure, Consultation, DelayFollowup, DelayReason, Facility, Patient, Priority,
                                 Referral, Result, Role, RoutingRule, Screening, TreatmentStart, User, ClosureType)
from app.api.v1.endpoints.patients import visible_patients
from app.services import routing, state_machine as sm
from app.services.audit import record_event, reject_and_log
from app.services.workflow import create_case_record
from app.schemas.cases import (CaseCreate, CaseAssign, ClassifyBody, ConfirmMatchBody, ConfirmatoryOutcomeBody, DelayReasonRecord, ExplainedBody,
                               ContactConfirmedBody)
from app.models.entities import ContactAttempt, Priority as P

router = APIRouter()

def find_case(db, key: str) -> Case | None:
    return db.query(Case).filter((Case.id == key) | (Case.case_number == key) | (Case.tracker_id == key)).first()

def load_case(db, user, key: str, *, modify=False) -> Case:
    case = find_case(db, key)
    if not case or not can_view_case(user, case, db): raise HTTPException(404, "Case not found")
    if modify and not can_modify_case(user, case): raise HTTPException(403, "Insufficient permissions")
    return case

def _hours(delta):
    return round(delta.total_seconds() / 3600, 2)

def brief(db, c: Case) -> dict:
    """Summary used by lists: identity, status, flags, owner, time in status and time left."""
    now = clock.now()
    owner = db.get(User, c.coordinator_id) if c.coordinator_id else None
    patient = db.get(Patient, c.patient_id)
    return {"id": c.id, "caseId": c.case_number, "trackerId": c.tracker_id, "patientId": c.patient_id, "patientLabel": patient.display_label, "priority": c.priority.value,
            "status": c.status.value, "flags": sm.flags_of(c), "facilityId": c.facility_id,
            "owner": {"id": owner.id, "displayName": owner.display_name, "role": owner.role.value} if owner else None,
            "timeInStatusHours": _hours(now - c.status_entered_at) if c.status_entered_at and c.status != CaseStatus.CLOSED else None,
            "timeLeftHours": _hours(c.due_at - now) if c.due_at and c.status != CaseStatus.CLOSED else None,
            "dueAt": c.due_at, "updatedAt": c.updated_at}

# ---------- reference data (static paths first) ----------

@router.get("/delay-reasons")
def delay_reason_codes(user=Depends(clinical_user)):
    return {"success": True, "data": [r.value for r in DelayReason], "meta": {}}

@router.get("/transitions")
def transition_table(user=Depends(clinical_user)):
    """The state machine as data: transitions T1 to T17 with who may do each and what it is refused unless."""
    return {"success": True, "data": {"statuses": [s.value for s in CaseStatus], "transitions": sm.transition_table()}, "meta": {}}


@router.post("/{case_id}/transition", include_in_schema=False)
def reject_direct_transition(case_id: str, payload: dict, user=Depends(clinical_user)):
    """Reject direct status mutation. State changes must use the dedicated workflow actions."""
    raise HTTPException(403, "Direct status changes are not allowed; use the corresponding workflow action")

# ---------- list, create, read ----------

@router.get("")
def list_cases(page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1), priority: Priority | None = None, status: CaseStatus | None = None,
               db: Session = Depends(get_db), user=Depends(worklist_user)):
    q = visible_cases(db.query(Case), user)
    if priority: q = q.filter(Case.priority == priority)
    if status: q = q.filter(Case.status == status)
    total = q.count()
    size = min(pageSize, 100)
    rows = q.order_by(Case.updated_at.desc()).offset((page - 1) * size).limit(size).all()
    return {"success": True, "data": [brief(db, c) for c in rows], "meta": {"total": total, "page": page, "pageSize": size}}

@router.post("")
def create_case(payload: CaseCreate, db: Session = Depends(get_db), user=Depends(clinical_user)):
    """Manual entry (T1, then T2 because a person chose the patient)."""
    if user.role not in CREATE_ROLES:
        raise HTTPException(403, "Insufficient permissions")
    facility_id = payload.facilityId or user.facility_id
    if user.role != Role.NATIONAL_ADMIN and facility_id != user.facility_id:
        raise HTTPException(403, "Cannot create a case outside your facility")
    if not facility_id or not db.get(Facility, facility_id): raise HTTPException(404, "Facility not found")
    patient = visible_patients(db.query(Patient), user).filter(Patient.id == payload.patientId).first()
    if not patient: raise HTTPException(404, "Patient not found")
    case = create_case_record(db, user, patient=patient, case_number=payload.caseId, facility_id=facility_id, priority=payload.priority,
                              next_action_code=payload.nextActionCode, next_action_label=payload.nextActionLabel, required_specialty=payload.requiredSpecialty,
                              confirmatory_required=payload.confirmatoryRequired)
    db.commit(); db.refresh(case)
    return {"success": True, "data": brief(db, case), "meta": {}}

def detail(db, case: Case) -> dict:
    data = brief(db, case)
    patient = db.get(Patient, case.patient_id)
    screening = db.get(Screening, case.screening_id) if case.screening_id else None
    facility = db.get(Facility, case.facility_id)
    referral = db.query(Referral).filter(Referral.case_id == case.id).order_by(Referral.created_at.desc()).first()
    closure = db.query(Closure).filter(Closure.case_id == case.id).order_by(Closure.requested_at.desc()).first()
    closed_by = db.get(User, closure.closed_by_id) if closure and closure.closed_by_id else None
    second_approver = db.get(User, closure.second_approver_id) if closure and closure.second_approver_id else None
    data.update({
        "patient": {"id": patient.id, "displayLabel": patient.display_label, "ageYears": patient.age_years, "sex": patient.sex, "preferredLanguage": patient.preferred_language},
        "screening": {"id": screening.id, "type": screening.screening_type, "outcome": screening.outcome, "displayLabel": screening.display_label} if screening else None,
        "facility": {"id": facility.id, "name": facility.name},
        "matchConfidence": case.match_confidence, "confirmatoryRequired": case.confirmatory_required, "requiredSpecialty": case.required_specialty,
        "statusEnteredAt": case.status_entered_at, "createdAt": case.created_at, "closedAt": case.closed_at, "closureType": case.closure_type,
        "linkedCaseId": case.linked_case_id,
        "nextAction": {"code": case.next_action_code, "label": case.next_action_label} if case.next_action_code or case.next_action_label else None,
        "delayReason": {"code": case.delay_reason_code, "note": case.delay_reason_note, "recordedAt": case.delay_reason_recorded_at} if case.delay_reason_code else None,
        "routing": routing.summary(db, case),
        "referral": {"id": referral.id, "status": referral.status, "receivingFacilityId": referral.receiving_facility_id,
                     "receivingClinicianId": referral.receiving_clinician_id} if referral else None,
        "closure": {
            "id": closure.id,
            "status": closure.status,
            "closureType": closure.closure_type,
            "reason": closure.reason,
            "closedById": closure.closed_by_id,
            "closedByName": closed_by.display_name if closed_by else None,
            "secondApproverId": closure.second_approver_id,
            "secondApproverName": second_approver.display_name if second_approver else None,
            "requestedAt": closure.requested_at,
            "secondSignOffById": closure.second_signoff_by_id,
            "closedAt": closure.closed_at
        } if closure else None,
        "counts": {"appointments": db.query(Appointment).filter(Appointment.case_id == case.id).count(),
                   "results": db.query(Result).filter(Result.case_id == case.id).count(),
                   "consultations": db.query(Consultation).filter(Consultation.case_id == case.id).count(),
                   "treatmentStarts": db.query(TreatmentStart).filter(TreatmentStart.case_id == case.id).count()},
        "validClosureTypes": sm.valid_closure_types(case),
    })
    return data

@router.get("/{case_id}")
def get_case(case_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = load_case(db, user, case_id)
    sm.sync_overdue(db, [case]); db.commit()
    return {"success": True, "data": detail(db, case), "meta": {}}

# ---------- owner ----------

@router.post("/{case_id}/assign")
def assign_case(case_id: str, payload: CaseAssign, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = load_case(db, user, case_id)
    if user.role not in ASSIGN_ROLES or not can_modify_case(user, case): raise HTTPException(403, "Insufficient permissions")
    owner = db.get(User, payload.ownerId or payload.coordinatorId)
    if not owner: raise HTTPException(404, "User not found")
    if owner.role not in (Role.COORDINATOR, Role.REFERRING_CLINICIAN, Role.RECEIVING_CLINICIAN) or not owner.is_active:
        raise HTTPException(422, detail={"code": "INVALID_ASSIGNEE", "message": "A case can only be assigned to an active clinical staff member"})
    if user.role != Role.NATIONAL_ADMIN and owner.facility_id != case.facility_id:
        raise HTTPException(422, detail={"code": "INVALID_ASSIGNEE", "message": "The owner must work at the case's facility"})
    if case.status == CaseStatus.CLOSED:
        reject_and_log(db, user, case_id=case.id, attempted="assign", status_code=409, code="CASE_CLOSED", message="A closed case is read-only")
    old = case.coordinator_id
    case.coordinator_id = owner.id
    case.updated_at = clock.now()
    record_event(db, user, case_id=case.id, event_type="CASE_ASSIGNED", description="Owner assigned",
                 old_values={"ownerId": old, "coordinatorId": old}, new_values={"ownerId": owner.id, "coordinatorId": owner.id})
    db.commit()
    return {"success": True, "data": {"caseId": case.case_number, "coordinatorId": owner.id, "ownerId": owner.id, "status": case.status.value, "flags": sm.flags_of(case)}, "meta": {}}

# ---------- T2: confirm the patient match ----------

@router.post("/{case_id}/confirm-match")
def confirm_match(case_id: str, payload: ConfirmMatchBody | None = None, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = load_case(db, user, case_id, modify=True)
    if user.role not in (Role.COORDINATOR, Role.NATIONAL_ADMIN):
        reject_and_log(db, user, case_id=case.id, attempted="T2", status_code=403, code="ROLE_NOT_ALLOWED", message="Only a coordinator confirms a patient match")
    if payload and payload.patientId and payload.patientId != case.patient_id:
        patient = visible_patients(db.query(Patient), user).filter(Patient.id == payload.patientId).first()
        if not patient: raise HTTPException(404, "Patient not found")
        record_event(db, user, case_id=case.id, event_type="PATIENT_MATCH_CHANGED", description="Patient match corrected by a person",
                     old_values={"patientId": case.patient_id}, new_values={"patientId": patient.id})
        case.patient_id = patient.id
    sm.confirm_match(db, user, case, confidence=1.0)
    db.commit()
    return {"success": True, "data": detail(db, case), "meta": {}}

# ---------- T3, T4, T6: classify ----------

def suggested_rule(db, case: Case):
    screening = db.get(Screening, case.screening_id) if case.screening_id else None
    if not screening: return None
    return db.query(RoutingRule).filter(RoutingRule.pathway.ilike(f"%{screening.screening_type.split()[0]}%")).first()

@router.get("/{case_id}/suggested-routing")
def suggested_routing(case_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)):
    """Plain table lookup (R-27, R-28a). A suggestion only: a person always sets urgency."""
    case = load_case(db, user, case_id)
    r = suggested_rule(db, case)
    return {"success": True, "data": ({"pathway": r.pathway, "resultCategory": r.result_category, "suggestedUrgency": r.suggested_urgency,
                                       "confirmatoryRequired": r.confirmatory_required, "specialty": r.specialty, "timeToAcceptMinutes": r.time_to_accept_minutes} if r else None), "meta": {}}

@router.post("/{case_id}/classify")
def classify_case(case_id: str, payload: ClassifyBody, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = load_case(db, user, case_id, modify=True)
    now = clock.now()
    if payload.confirmatoryRequired is not None:
        case.confirmatory_required = payload.confirmatoryRequired
    if not payload.actionable:
        sm.apply(db, user, case, "T6", ctx={"reason": payload.reason}, at=now, details={"reason": payload.reason}, owner=case.coordinator_id)
        closure = Closure(case_id=case.id, closure_type=ClosureType.NOT_ACTIONABLE.value, status="CLOSED", reason=payload.reason, decision=payload.reason,
                          closed_by_id=user.id, transition_id="T6", requested_at=now, closed_at=now)
        db.add(closure); case.closure_type = ClosureType.NOT_ACTIONABLE.value; case.closed_at = now
    elif payload.urgent:
        specialty = routing.normalize_specialty(payload.specialty) or case.required_specialty
        if not specialty:
            reject_and_log(db, user, case_id=case.id, attempted="T4", status_code=422, code="SPECIALTY_REQUIRED", message="An urgent case needs a specialty chosen")
        case.required_specialty = specialty; case.priority = Priority.URGENT
        sm.apply(db, user, case, "T4", ctx={"specialty": specialty}, at=now, details={"priority": "URGENT", "specialty": specialty})
        routing.route_case(db, user, case, specialty=specialty)
    else:
        if payload.priority == Priority.URGENT:
            raise HTTPException(422, detail={"code": "URGENT_NEEDS_URGENT_PATH", "message": "Set urgent=true to mark a case urgent"})
        case.priority = payload.priority or Priority.NORMAL
        sm.apply(db, user, case, "T3", at=now, details={"priority": case.priority.value})
    db.commit()
    return {"success": True, "data": detail(db, case), "meta": {}}

# ---------- T11: confirmatory result shows no further care needed ----------

@router.post("/{case_id}/confirmatory-outcome")
def confirmatory_outcome(case_id: str, payload: ConfirmatoryOutcomeBody, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = load_case(db, user, case_id, modify=True)
    sm.apply(db, user, case, "T11", ctx={"outcome": payload.outcome, "reason": payload.reason}, owner=user.id, details={"outcome": payload.outcome, "reason": payload.reason})
    db.commit()
    return {"success": True, "data": detail(db, case), "meta": {}}

# ---------- flags: OVERDUE follow-up, NOT_EXPLAINED, MESSAGE_FAILED ----------

@router.post("/{case_id}/delay-reason")
def record_delay_reason(case_id: str, payload: DelayReasonRecord, db: Session = Depends(get_db), user=Depends(clinical_user)):
    """R-18 / A-10: handling an OVERDUE flag needs a reason-for-delay code. The follow-up clears the flag."""
    case = load_case(db, user, case_id, modify=True)
    if user.role not in CREATE_ROLES: raise HTTPException(403, "Insufficient permissions")
    sm.sync_overdue(db, [case])
    if not case.flag_overdue:
        reject_and_log(db, user, case_id=case.id, attempted="delay-reason", status_code=409, code="CASE_NOT_OVERDUE", message="A reason-for-delay code can only be recorded on an overdue case")
    now = clock.now()
    old = {"code": case.delay_reason_code, "note": case.delay_reason_note}
    db.add(DelayFollowup(case_id=case.id, flag="OVERDUE", status=case.status.value, code=payload.code.value, note=payload.note, staff_id=user.id, created_at=now))
    case.delay_reason_code = payload.code.value; case.delay_reason_note = payload.note
    case.delay_reason_recorded_at = now; case.delay_reason_recorded_by_id = user.id; case.flag_overdue = False
    record_event(db, user, case_id=case.id, event_type="DELAY_REASON_RECORDED", description="Reason for delay recorded; OVERDUE cleared", old_values=old,
                 new_values={"code": payload.code.value, "note": payload.note, "status": case.status.value})
    db.commit()
    return {"success": True, "data": {"caseId": case.case_number, "flags": sm.flags_of(case),
                                      "delayReason": {"code": case.delay_reason_code, "note": case.delay_reason_note, "recordedAt": case.delay_reason_recorded_at, "recordedById": user.id}}, "meta": {}}

@router.post("/{case_id}/explained")
def record_explained(case_id: str, payload: ExplainedBody, db: Session = Depends(get_db), user=Depends(clinical_user)):
    """A clinician or coordinator explains the result again and records it: clears NOT_EXPLAINED."""
    case = load_case(db, user, case_id, modify=True)
    if user.role not in CREATE_ROLES: raise HTTPException(403, "Insufficient permissions")
    if not case.flag_not_explained:
        reject_and_log(db, user, case_id=case.id, attempted="explained", status_code=409, code="NOT_FLAGGED", message="This case is not flagged NOT_EXPLAINED")
    case.flag_not_explained = False; case.updated_at = clock.now()
    record_event(db, user, case_id=case.id, event_type="EXPLANATION_RECORDED", description="Result explained again; NOT_EXPLAINED cleared", new_values={"note": payload.note})
    db.commit()
    return {"success": True, "data": {"caseId": case.case_number, "flags": sm.flags_of(case)}, "meta": {}}

@router.post("/{case_id}/contact-confirmed")
def contact_confirmed(case_id: str, payload: ContactConfirmedBody, db: Session = Depends(get_db), user=Depends(clinical_user)):
    """Staff confirm they reached the patient by another route: clears MESSAGE_FAILED."""
    case = load_case(db, user, case_id, modify=True)
    if user.role not in CREATE_ROLES: raise HTTPException(403, "Insufficient permissions")
    if not case.flag_message_failed:
        reject_and_log(db, user, case_id=case.id, attempted="contact-confirmed", status_code=409, code="NOT_FLAGGED", message="This case is not flagged MESSAGE_FAILED")
    db.add(ContactAttempt(case_id=case.id, route=payload.route, outcome="REACHED", note=payload.note, recorded_by_id=user.id, created_at=clock.now()))
    case.flag_message_failed = False; case.updated_at = clock.now()
    record_event(db, user, case_id=case.id, event_type="CONTACT_CONFIRMED", description="Patient reached by another route; MESSAGE_FAILED cleared",
                 new_values={"route": payload.route, "note": payload.note})
    db.commit()
    return {"success": True, "data": {"caseId": case.case_number, "flags": sm.flags_of(case)}, "meta": {}}

# ---------- timeline ----------

@router.get("/{case_id}/events")
def case_events(case_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = load_case(db, user, case_id)
    events = db.query(AuditEvent).filter(AuditEvent.case_id == case.id).order_by(AuditEvent.occurred_at.asc(), AuditEvent.id).all()
    return {"success": True, "data": [{"id": e.id, "eventType": e.event_type, "description": e.description, "occurredAt": e.occurred_at, "actorId": e.actor_id,
                                       "actorRole": e.actor_role, "transition": (e.new_values or {}).get("transition"), "oldValues": e.old_values, "newValues": e.new_values}
                                      for e in events], "meta": {}}
