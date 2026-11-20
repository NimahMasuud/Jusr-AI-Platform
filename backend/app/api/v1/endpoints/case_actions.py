"""Case child records and closure: results, appointments (R-47), treatment start (R-48), contact attempts, closure (T16, T17), linked cases and transfers."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core import clock
from app.core.database import get_db
from app.api.v1.deps import clinical_user
from app.api.v1.endpoints.cases import detail, load_case, find_case
from app.core.permissions import CREATE_ROLES, accepted_receiving_side, can_modify_case, can_view_case
from app.models.entities import (Appointment, Attendance, Case, CaseStatus, Closure, ClosureType, ContactAttempt, DelayFollowup, Facility, Patient, Result, Role,
                                 TreatmentStart, User, Task)
from app.schemas.cases import (AppointmentCreate, AttendanceBody, CloseBody, ContactAttemptBody, LinkedCaseBody, ResultBody, TransferBody, TreatmentStartBody)
from app.services import state_machine as sm
from app.services.audit import record_event, reject_and_log
from app.services.workflow import create_case_record

router = APIRouter()

def _need_role(db, user, case, roles, attempted):
    if user.role not in roles:
        reject_and_log(db, user, case_id=case.id, attempted=attempted, status_code=403, code="ROLE_NOT_ALLOWED", message=f"A {user.role.value} cannot do this")

def _receiving_or_owner(db, user, case):
    """Receiving-side access (accepted referral) or normal modify rights."""
    if not (can_modify_case(user, case) or accepted_receiving_side(db, user, case)):
        raise HTTPException(403, "Insufficient permissions")

def _load_for_receiving(db, user, case_id) -> Case:
    case = find_case(db, case_id)
    if not case or not (can_view_case(user, case, db) or accepted_receiving_side(db, user, case)):
        raise HTTPException(404, "Case not found")
    return case

# ---------------------------------------------------------------- results

def _result_out(r: Result):
    return {"id": r.id, "kind": r.kind, "testCode": r.test_code, "testName": r.test_name, "value": r.value, "abnormal": r.abnormal, "issuedAt": r.issued_at,
            "source": r.source, "receivedAt": r.received_at}

@router.get("/{case_id}/results")
def list_results(case_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = load_case(db, user, case_id)
    rows = db.query(Result).filter(Result.case_id == case.id).order_by(Result.received_at, Result.id).all()
    return {"success": True, "data": [_result_out(r) for r in rows], "meta": {}}

@router.post("/{case_id}/results")
def add_result(case_id: str, payload: ResultBody, db: Session = Depends(get_db), user=Depends(clinical_user)):
    """Manual entry of a result. A confirmatory result is stored so T10 or T11 can follow. Result text is data, never instructions (R-40)."""
    case = load_case(db, user, case_id, modify=True)
    _need_role(db, user, case, CREATE_ROLES, "result:add")
    if case.status == CaseStatus.CLOSED:
        reject_and_log(db, user, case_id=case.id, attempted="result:add", status_code=409, code="CASE_CLOSED", message="A closed case is read-only")
    r = Result(case_id=case.id, facility_id=case.facility_id, kind=payload.kind, test_code=payload.testCode, test_name=payload.testName, value=payload.value,
               abnormal=payload.abnormal, issued_at=payload.issuedAt, source="MANUAL", received_at=clock.now())
    db.add(r); db.flush()
    record_event(db, user, case_id=case.id, event_type="RESULT_STORED", description=f"{payload.kind.title()} result stored", new_values={"resultId": r.id, "kind": r.kind})
    db.commit()
    return {"success": True, "data": _result_out(r), "meta": {}}

# ---------------------------------------------------------------- appointments (R-47), T14

def _appt_out(a: Appointment):
    return {"id": a.id, "caseId": a.case_id, "facilityId": a.facility_id, "scheduledAt": a.scheduled_at, "attendance": a.attendance, "recordedById": a.recorded_by_id, "recordedAt": a.recorded_at}

@router.get("/{case_id}/appointments")
def list_appointments(case_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = _load_for_receiving(db, user, case_id)
    rows = db.query(Appointment).filter(Appointment.case_id == case.id).order_by(Appointment.scheduled_at).all()
    return {"success": True, "data": [_appt_out(a) for a in rows], "meta": {}}

@router.post("/{case_id}/appointments")
def book_appointment(case_id: str, payload: AppointmentCreate, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = _load_for_receiving(db, user, case_id)
    _receiving_or_owner(db, user, case)
    _need_role(db, user, case, (Role.RECEIVING_CLINICIAN, Role.COORDINATOR, Role.NATIONAL_ADMIN), "appointment:book")
    if case.status != CaseStatus.AWAITING_APPOINTMENT:
        reject_and_log(db, user, case_id=case.id, attempted="appointment:book", status_code=409, code="INVALID_STATUS_TRANSITION",
                       message=f"An appointment is booked after the referral is accepted; the case is {case.status.value}")
    if db.query(Appointment.id).filter(Appointment.case_id == case.id, Appointment.attendance == Attendance.BOOKED.value).first():
        reject_and_log(db, user, case_id=case.id, attempted="appointment:book", status_code=409, code="APPOINTMENT_ALREADY_BOOKED", message="An appointment is already booked; record its attendance first")
    a = Appointment(case_id=case.id, facility_id=user.facility_id or case.facility_id, scheduled_at=payload.scheduledAt, created_at=clock.now())
    db.add(a); db.flush()
    record_event(db, user, case_id=case.id, event_type="APPOINTMENT_BOOKED", description="Appointment booked", new_values={"appointmentId": a.id, "scheduledAt": payload.scheduledAt.isoformat()})
    db.commit()
    return {"success": True, "data": _appt_out(a), "meta": {}}

def record_attendance(db, user, case: Case, a: Appointment, attendance: str, reason_code=None, note=None, at=None):
    """ATTENDED applies T14. MISSED keeps the case in AWAITING_APPOINTMENT, needs a reason-for-delay code (R-18) and a rebooking (R-47)."""
    now = at or clock.now()
    if a.attendance != Attendance.BOOKED.value:
        reject_and_log(db, user, case_id=case.id, attempted="appointment:attendance", status_code=409, code="ATTENDANCE_ALREADY_RECORDED", message=f"Attendance is already recorded as {a.attendance}")
    if attendance == Attendance.MISSED.value:
        if not reason_code:
            reject_and_log(db, user, case_id=case.id, attempted="appointment:attendance", status_code=422, code="DELAY_REASON_REQUIRED",
                           message="A missed appointment needs a reason-for-delay code (R-47, R-18)")
        a.attendance = Attendance.MISSED.value; a.recorded_by_id = user.id; a.recorded_at = now
        db.add(DelayFollowup(case_id=case.id, flag="MISSED_APPOINTMENT", status=case.status.value, code=reason_code.value if hasattr(reason_code, "value") else reason_code,
                             note=note, staff_id=user.id, created_at=now))
        record_event(db, user, case_id=case.id, event_type="APPOINTMENT_MISSED", description="Appointment missed; rebooking needed", at=now,
                     new_values={"appointmentId": a.id, "code": getattr(reason_code, "value", reason_code), "note": note})
        from app.services.tasks import create_task
        create_task(db, case, "REBOOK_APPOINTMENT", "Missed appointment needs rebooking", note, source_ref=a.id)
        return case
    a.attendance = Attendance.ATTENDED.value; a.recorded_by_id = user.id; a.recorded_at = now
    sm.apply(db, user, case, "T14", ctx={"appointment": a}, at=now, details={"appointmentId": a.id, "scheduledAt": a.scheduled_at.isoformat()})
    return case

@router.post("/{case_id}/appointments/{appointment_id}/attendance")
def set_attendance(case_id: str, appointment_id: str, payload: AttendanceBody, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = _load_for_receiving(db, user, case_id)
    _receiving_or_owner(db, user, case)
    _need_role(db, user, case, (Role.RECEIVING_CLINICIAN, Role.COORDINATOR, Role.NATIONAL_ADMIN), "appointment:attendance")
    a = db.query(Appointment).filter(Appointment.id == appointment_id, Appointment.case_id == case.id).first()
    if not a: raise HTTPException(404, "Appointment not found")
    record_attendance(db, user, case, a, payload.attendance, payload.reasonCode, payload.note)
    db.commit()
    return {"success": True, "data": {"appointment": _appt_out(a), "caseStatus": case.status.value, "flags": sm.flags_of(case)}, "meta": {}}

# ---------------------------------------------------------------- treatment start (R-48), T15

def _start_out(t: TreatmentStart):
    return {"id": t.id, "kind": t.kind, "startDate": t.start_date, "note": t.note, "attachmentRef": t.attachment_ref, "recordedById": t.recorded_by_id, "recordedAt": t.recorded_at}

def record_treatment_start(db, user, case: Case, *, kind, start_date, note, attachment_ref, at=None):
    now = at or clock.now()
    t = TreatmentStart(case_id=case.id, kind=kind, start_date=start_date, note=note, attachment_ref=attachment_ref, recorded_by_id=user.id, recorded_at=now)
    db.add(t); db.flush()
    sm.apply(db, user, case, "T15", ctx={"start": t}, at=now, details={"treatmentStartId": t.id, "kind": kind})
    return t

@router.post("/{case_id}/treatment-start")
def treatment_start(case_id: str, payload: TreatmentStartBody, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = _load_for_receiving(db, user, case_id)
    _receiving_or_owner(db, user, case)
    t = record_treatment_start(db, user, case, kind=payload.kind, start_date=payload.startDate, note=payload.note, attachment_ref=payload.attachmentRef)
    db.commit()
    return {"success": True, "data": {"treatmentStart": _start_out(t), "caseStatus": case.status.value}, "meta": {}}

@router.get("/{case_id}/treatment-start")
def get_treatment_start(case_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = _load_for_receiving(db, user, case_id)
    rows = db.query(TreatmentStart).filter(TreatmentStart.case_id == case.id).order_by(TreatmentStart.recorded_at).all()
    return {"success": True, "data": [_start_out(t) for t in rows], "meta": {}}

# ---------------------------------------------------------------- contact attempts (R-55)

def _attempt_out(a: ContactAttempt):
    return {"id": a.id, "route": a.route, "outcome": a.outcome, "note": a.note, "recordedById": a.recorded_by_id, "recordedAt": a.created_at}

@router.get("/{case_id}/contact-attempts")
def list_attempts(case_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = load_case(db, user, case_id)
    rows = db.query(ContactAttempt).filter(ContactAttempt.case_id == case.id).order_by(ContactAttempt.created_at).all()
    return {"success": True, "data": [_attempt_out(a) for a in rows], "meta": {}}

@router.post("/{case_id}/contact-attempts")
def add_attempt(case_id: str, payload: ContactAttemptBody, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = load_case(db, user, case_id, modify=True)
    _need_role(db, user, case, CREATE_ROLES, "contact-attempt")
    a = ContactAttempt(case_id=case.id, route=payload.route, outcome=payload.outcome, note=payload.note, recorded_by_id=user.id, created_at=clock.now())
    db.add(a); db.flush()
    record_event(db, user, case_id=case.id, event_type="CONTACT_ATTEMPT_LOGGED", description=f"Contact attempt by {payload.route}: {payload.outcome}", new_values={"attemptId": a.id, "route": payload.route, "outcome": payload.outcome})
    db.commit()
    return {"success": True, "data": _attempt_out(a), "meta": {}}

# ---------------------------------------------------------------- closure (section 10): T16 and T17

@router.get("/{case_id}/closure-checklist")
def closure_checklist(case_id: str, closureType: ClosureType, reason: str | None = None, decision: str | None = None, evidence: str | None = None,
                      db: Session = Depends(get_db), user=Depends(clinical_user)):
    """The evidence checklist for the chosen type, each item present or missing, with the record that satisfies it (R-53)."""
    case = load_case(db, user, case_id)
    items = sm.closure_checklist(db, case, closureType, decision=decision, evidence=evidence, reason=reason)
    complete = all(i["present"] for i in items if i["item"] != "A second authorised person's sign-off")
    return {"success": True, "data": {"closureType": closureType.value, "validClosureTypes": sm.valid_closure_types(case), "items": items,
                                      "dataMissing": case.flag_data_missing, "canClose": sm.can_close(user, case, closureType), "complete": complete and not case.flag_data_missing,
                                      "needsSecondSignOff": closureType == ClosureType.OTHER}, "meta": {}}

def _tid(case): return "T16" if case.status == CaseStatus.READY_TO_CLOSE else "T17"

def _finish_closure(db, actor, case: Case, closure: Closure, *, second=None):
    now = clock.now()
    tid = _tid(case)
    sm.apply(db, actor, case, tid, at=now, details={"closureType": closure.closure_type, "reason": closure.reason, "closedById": closure.closed_by_id,
                                                  "secondSignOffById": second.id if second else None, "documented": bool(closure.decision or closure.evidence)})
    closure.status = "CLOSED"; closure.closed_at = now; closure.transition_id = tid
    if second: closure.second_signoff_by_id = second.id
    case.closure_type = closure.closure_type; case.closed_at = now
    for t in db.query(Task).filter(Task.case_id == case.id, Task.status == "OPEN").all():
        t.status = "DONE"; t.completed_at = now  # nothing is left open on a closed case


@router.post("/{case_id}/close")
def close_case(case_id: str, payload: CloseBody, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = load_case(db, user, case_id)
    tid = _tid(case)

    if case.status == CaseStatus.CLOSED:
        reject_and_log(db, user, case_id=case.id, attempted=tid, status_code=409, code="CASE_CLOSED", message="A closed case is read-only (R-56)")

    if user.role.value in ("AI_SERVICE", "SYSTEM", "PATIENT", "FACILITY_ADMIN"):
        reject_and_log(db, user, case_id=case.id, attempted=tid, status_code=403, code="CLOSURE_IS_HUMAN", message="Closure is a human act; the AI service and the system cannot close a case (R-15)")

    if not sm.can_close(user, case, payload.closureType):
        reject_and_log(db, user, case_id=case.id, attempted=tid, status_code=403, code="NOT_AUTHORISED_TO_CLOSE",
                       message="You cannot close this case this way: you need the authorised-to-close flag, or to be the named owner for a clinician's closure")

    if payload.closureType.value not in sm.valid_closure_types(case):
        reject_and_log(db, user, case_id=case.id, attempted=tid, status_code=422, code="INVALID_CLOSURE_TYPE", message=f"{payload.closureType.value} cannot be used while the case is {case.status.value}")

    if tid == "T17" and user.role.value not in sm.CLINICIANS | {sm.NAT}:
        reject_and_log(db, user, case_id=case.id, attempted=tid, status_code=403, code="ROLE_NOT_ALLOWED", message="Only a clinician can close a case before it is ready to close (T17)")

    second_approver = None

    if payload.closureType == ClosureType.OTHER:
        if not payload.secondApproverId:
            reject_and_log(db, user, case_id=case.id, attempted="close:request", status_code=422,
                           code="SECOND_APPROVER_REQUIRED", message="Select a second authorised person to approve this closure (R-54)")

        second_approver = db.get(User, payload.secondApproverId)

        allowed_second_approver_roles = (
            (Role.REFERRING_CLINICIAN,)
            if tid == "T17"
            else (Role.COORDINATOR, Role.REFERRING_CLINICIAN)
        )

        if (
            not second_approver
            or not second_approver.is_active
            or second_approver.id == user.id
            or second_approver.facility_id != case.facility_id
            or second_approver.role not in allowed_second_approver_roles
            or not second_approver.authorised_to_close
        ):
            reject_and_log(
                db,
                user,
                case_id=case.id,
                attempted="close:request",
                status_code=422,
                code="INVALID_SECOND_APPROVER",
                message="The second approver must be a different, active, authorised person at this facility with a role permitted for this closure transition",
            )

    if case.flag_data_missing:
        reject_and_log(db, user, case_id=case.id, attempted=tid, status_code=409, code="DATA_MISSING", message="Data missing: a facility feed is missing or incomplete, so this case cannot be closed yet (R-14)")

    missing = sm.missing_for_closure(db, case, payload.closureType, decision=payload.decision, evidence=payload.evidence, reason=payload.reason)
    if missing:
        reject_and_log(db, user, case_id=case.id, attempted=tid, status_code=422, code="EVIDENCE_REQUIRED",
                       message="Cannot close this case yet. Missing: " + "; ".join(missing) + " (rule A-01)")

    now = clock.now()

    if payload.closureType == ClosureType.OTHER:
        pending = db.query(Closure).filter(
            Closure.case_id == case.id,
            Closure.status == "PENDING_SIGNOFF",
        ).first()

        if pending and pending.closed_by_id != user.id:
            reject_and_log(db, user, case_id=case.id, attempted="close:request", status_code=409,
                           code="CLOSURE_ALREADY_PENDING",
                           message="Another user has already submitted a closure awaiting sign-off")

        if pending:
            pending.reason = payload.reason
            pending.decision = payload.decision
            pending.evidence = payload.evidence
            pending.closed_by_id = user.id
            pending.second_approver_id = second_approver.id
            pending.requested_at = now
        else:
            pending = Closure(
                case_id=case.id,
                closure_type=payload.closureType.value,
                status="PENDING_SIGNOFF",
                reason=payload.reason,
                decision=payload.decision,
                evidence=payload.evidence,
                closed_by_id=user.id,
                second_approver_id=second_approver.id,
                requested_at=now,
            )
            db.add(pending)

        record_event(
            db,
            user,
            case_id=case.id,
            event_type="CLOSURE_REQUESTED",
            description="Closure as OTHER requested; a second authorised person must approve (R-54)",
            new_values={
                "closureType": "OTHER",
                "reason": payload.reason,
                "secondApproverId": second_approver.id,
            },
        )
        db.commit()

        return {
            "success": True,
            "data": {
                "caseId": case.case_number,
                "status": case.status.value,
                "pendingSignOff": True,
                "secondApproverId": second_approver.id,
                "message": "A second authorised person must approve before the case closes",
            },
            "meta": {},
        }

    closure = Closure(
        case_id=case.id,
        closure_type=payload.closureType.value,
        status="PENDING_SIGNOFF",
        reason=payload.reason,
        decision=payload.decision,
        evidence=payload.evidence,
        closed_by_id=user.id,
        requested_at=now,
    )
    db.add(closure)
    _finish_closure(db, user, case, closure)
    db.commit()

    return {
        "success": True,
        "data": {
            "caseId": case.case_number,
            "status": case.status.value,
            "closureType": case.closure_type,
            "closedAt": case.closed_at,
            "pendingSignOff": False,
        },
        "meta": {},
    }


@router.post("/{case_id}/close/sign-off")
def sign_off_closure(case_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)):
    """R-54: only the specifically selected second authorised person can approve an 'Other' closure."""
    case = load_case(db, user, case_id)

    closure = db.query(Closure).filter(
        Closure.case_id == case.id,
        Closure.status == "PENDING_SIGNOFF",
        Closure.closure_type == ClosureType.OTHER.value,
    ).first()

    if not closure:
        reject_and_log(db, user, case_id=case.id, attempted="close:sign-off", status_code=409,
                       code="NOTHING_TO_SIGN_OFF", message="There is no closure waiting for a second sign-off")

    if closure.closed_by_id == user.id:
        reject_and_log(db, user, case_id=case.id, attempted="close:sign-off", status_code=403,
                       code="SECOND_PERSON_REQUIRED", message="A second, different authorised person must approve (R-54)")

    if closure.second_approver_id != user.id:
        reject_and_log(
            db,
            user,
            case_id=case.id,
            attempted="close:sign-off",
            status_code=403,
            code="NOT_SELECTED_APPROVER",
            message="Only the person selected as the second approver can sign off this closure",
        )

    allowed_signoff_roles = (
        (Role.REFERRING_CLINICIAN,)
        if _tid(case) == "T17"
        else (Role.COORDINATOR, Role.REFERRING_CLINICIAN)
    )

    if (
        not user.is_active
        or user.role not in allowed_signoff_roles
        or not user.authorised_to_close
    ):
        reject_and_log(
            db,
            user,
            case_id=case.id,
            attempted="close:sign-off",
            status_code=403,
            code="NOT_AUTHORISED_TO_CLOSE",
            message="The selected second person must be active, authorised, and permitted for this closure transition",
        )
    _finish_closure(db, user, case, closure, second=user)
    db.commit()

    return {
        "success": True,
        "data": {
            "caseId": case.case_number,
            "status": case.status.value,
            "closureType": case.closure_type,
            "closedAt": case.closed_at,
            "pendingSignOff": False,
        },
        "meta": {},
    }

# ---------------------------------------------------------------- R-56: reopening is not allowed; start a new linked case

@router.post("/{case_id}/linked-case")
def start_linked_case(case_id: str, payload: LinkedCaseBody, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = load_case(db, user, case_id)
    if case.status != CaseStatus.CLOSED:
        reject_and_log(db, user, case_id=case.id, attempted="linked-case", status_code=409, code="CASE_NOT_CLOSED", message="A linked case starts from a closed case")
    if not (user.role == Role.NATIONAL_ADMIN or user.authorised_to_close or case.coordinator_id == user.id) or user.role not in CREATE_ROLES:
        raise HTTPException(403, "Insufficient permissions")
    patient = db.get(Patient, case.patient_id)
    new = create_case_record(db, user, patient=patient, case_number=payload.caseId, facility_id=case.facility_id, priority=case.priority, extra_event={"linkedCaseId": case.id, "reason": payload.reason})
    new.linked_case_id = case.id; new.screening_id = case.screening_id
    record_event(db, user, case_id=case.id, event_type="LINKED_CASE_STARTED", description="A new linked case was started; this case stays closed",
                 new_values={"newCaseId": new.id, "newCaseNumber": new.case_number, "reason": payload.reason})
    db.commit()
    return {"success": True, "data": detail(db, new), "meta": {}}

# ---------------------------------------------------------------- R-17: the patient moves to another facility

@router.post("/{case_id}/transfer")
def transfer_case(case_id: str, payload: TransferBody, db: Session = Depends(get_db), user=Depends(clinical_user)):
    """The coordinator reassigns ownership. The tracker ID and case history stay; the change is logged (A-07)."""
    case = load_case(db, user, case_id, modify=True)
    if user.role not in (Role.COORDINATOR, Role.NATIONAL_ADMIN):
        reject_and_log(db, user, case_id=case.id, attempted="transfer", status_code=403, code="ROLE_NOT_ALLOWED", message="Only a coordinator reassigns a case to another facility")
    if case.status == CaseStatus.CLOSED:
        reject_and_log(db, user, case_id=case.id, attempted="transfer", status_code=409, code="CASE_CLOSED", message="A closed case is read-only")
    new_fac = db.get(Facility, payload.newFacilityId)
    if not new_fac: raise HTTPException(404, "Facility not found")
    owner = None
    if payload.newOwnerId:
        owner = db.get(User, payload.newOwnerId)
        if not owner or not owner.is_active or owner.facility_id != new_fac.id or owner.role not in (Role.COORDINATOR, Role.REFERRING_CLINICIAN, Role.RECEIVING_CLINICIAN):
            raise HTTPException(422, detail={"code": "INVALID_ASSIGNEE", "message": "The new owner must be an active coordinator or clinician at the new facility"})
    old = {"facilityId": case.facility_id, "ownerId": case.coordinator_id}
    case.facility_id = new_fac.id; case.coordinator_id = owner.id if owner else None; case.updated_at = clock.now()
    patient = db.get(Patient, case.patient_id); patient.facility_id = new_fac.id
    for t in db.query(Task).filter(Task.case_id == case.id, Task.type == "REASSIGN_CASE", Task.status == "OPEN").all():
        t.status = "DONE"; t.completed_at = clock.now(); t.completed_by_id = user.id
    record_event(db, user, case_id=case.id, event_type="CASE_TRANSFERRED", description="Case reassigned to another facility; history kept", old_values=old,
                 new_values={"facilityId": new_fac.id, "ownerId": owner.id if owner else None, "reason": payload.reason, "trackerId": case.tracker_id})
    db.commit()
    return {"success": True, "data": {"caseId": case.case_number, "trackerId": case.tracker_id, "facilityId": case.facility_id, "ownerId": case.coordinator_id, "flags": sm.flags_of(case)}, "meta": {}}
