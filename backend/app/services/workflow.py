"""Workflow actions shared by direct staff calls, AI-suggestion approvals and inbound events, so all of them pass
the same state-machine checks."""
from fastapi import HTTPException
from app.core import clock
from app.models.entities import Case, CaseStatus, Facility, Priority, Referral, ReferralStatus, Role, User
from app.services import state_machine as sm
from app.services.audit import record_event, reject_and_log
from app.services.routing import normalize_specialty

ACTIVE_REFERRAL = (ReferralStatus.SENT.value, ReferralStatus.ACCEPTED.value)

def check_receiving_clinician(db, clinician_id, facility_id) -> User:
    c = db.get(User, clinician_id)
    if not c:
        raise HTTPException(404, "Receiving clinician not found")
    if c.role != Role.RECEIVING_CLINICIAN or not c.is_active or c.facility_id != facility_id:
        raise HTTPException(422, detail={"code": "INVALID_ASSIGNEE", "message": "Must be an active receiving clinician at the receiving facility"})
    return c

def create_case_record(db, user, *, patient, case_number, facility_id, priority=Priority.NORMAL, next_action_code=None, next_action_label=None,
                       required_specialty=None, extra_event=None, confirmatory_required=False, owner_id="auto", match_confidence=1.0, at=None) -> Case:
    """T1 (a new case in NEW) and, when the patient match is confirmed, T2. A manual entry by a coordinator confirms the match
    as a person; otherwise a high-confidence match is confirmed by the system and a low one waits for a coordinator."""
    if db.query(Case.id).filter(Case.case_number == case_number).first():
        raise HTTPException(409, detail={"code": "DUPLICATE_CASE_ID", "message": f"Case {case_number} already exists"})
    if owner_id == "auto":
        owner_id = user.id if user.role == Role.COORDINATOR else None
    case = Case(case_number=case_number, patient_id=patient.id, facility_id=facility_id, priority=priority, coordinator_id=owner_id,
                next_action_code=next_action_code, next_action_label=next_action_label, confirmatory_required=confirmatory_required,
                required_specialty=normalize_specialty(required_specialty))
    db.add(case)
    sm.open_case(db, user, case, at=at, details=extra_event)
    if match_confidence >= 1.0:
        actor = user if user.role in (Role.COORDINATOR, Role.NATIONAL_ADMIN) else sm.SYSTEM
        sm.confirm_match(db, actor, case, confidence=match_confidence, at=at)
    return case

# ---------------------------------------------------------------- referrals

def create_referral_record(db, user, case, *, facility_id, clinician_id=None, reason=None, target_specialty=None, packet=None, extra_event=None, at=None) -> Referral:
    facility = db.get(Facility, facility_id)
    if not facility:
        raise HTTPException(404, "Receiving facility not found")
    if facility.id == case.facility_id:
        raise HTTPException(422, detail={"code": "INVALID_RECEIVING_FACILITY", "message": "Receiving facility must differ from the case's facility"})
    if clinician_id:
        check_receiving_clinician(db, clinician_id, facility.id)
    if db.query(Referral.id).filter(Referral.case_id == case.id, Referral.status.in_(ACTIVE_REFERRAL)).first():
        reject_and_log(db, user, case_id=case.id, attempted="referral:create", status_code=409, code="REFERRAL_ALREADY_ACTIVE", message="This case already has an active referral")
    now = at or clock.now()
    r = Referral(case_id=case.id, status=ReferralStatus.SENT.value, receiving_facility_id=facility.id, receiving_clinician_id=clinician_id,
                 referred_by_id=user.id, reason=reason, target_specialty=normalize_specialty(target_specialty), packet=packet, created_at=now, updated_at=now)
    db.add(r); db.flush()
    details = {"referralId": r.id, "receivingFacilityId": facility.id, "receivingClinicianId": clinician_id, **(extra_event or {})}
    if case.status == CaseStatus.AWAITING_ACK:
        sm.apply(db, user, case, "T9", ctx={"referral": r}, details=details, at=now, owner=user.id)
    elif case.status == CaseStatus.AWAITING_CONFIRMATION:
        sm.apply(db, user, case, "T10", ctx={"referral": r}, details=details, at=now, owner=user.id)
    elif case.status == CaseStatus.REFERRAL_PENDING:
        # A new referral after a decline or a missed deadline: the status stays REFERRAL_PENDING (T13 follow-up).
        if user.role not in (Role.REFERRING_CLINICIAN, Role.RECEIVING_CLINICIAN, Role.NATIONAL_ADMIN):
            reject_and_log(db, user, case_id=case.id, attempted="referral:create", status_code=403, code="ROLE_NOT_ALLOWED", message="Only a clinician can send a referral")
        case.coordinator_id = user.id; case.due_at = None
        from app.services import settings_store
        case.status_entered_at = now; case.due_at = settings_store.due_for(db, CaseStatus.REFERRAL_PENDING, now, facility_id=case.facility_id)
        case.flag_overdue = False; case.updated_at = now
        record_event(db, user, case_id=case.id, event_type="REFERRAL_RESENT", description="New referral sent after the earlier one was not accepted", at=now,
                     new_values={"status": "REFERRAL_PENDING", **details})
    else:
        reject_and_log(db, user, case_id=case.id, attempted="referral:create", status_code=409, code="INVALID_STATUS_TRANSITION",
                       message=f"A referral cannot be sent while the case is {case.status.value}. It is sent from AWAITING_ACK (no confirmatory test needed), AWAITING_CONFIRMATION (result received) or after a decline")
    record_event(db, user, case_id=case.id, event_type="REFERRAL_CREATED", description="Referral created", at=now,
                 new_values={"referralId": r.id, "status": r.status, "receivingFacilityId": facility.id, "receivingClinicianId": clinician_id, "reason": reason, **(extra_event or {})})
    return r

def mark_not_accepted(db, actor, referral, case, at=None):
    """R-46: NOT_ACCEPTED_IN_TIME and EXCEPTION. The case stays REFERRAL_PENDING until a new referral or owner follows."""
    from app.services.tasks import create_task
    now = at or clock.now()
    referral.status = ReferralStatus.NOT_ACCEPTED_IN_TIME.value; referral.decided_at = now; referral.updated_at = now
    case.flag_exception = True; case.updated_at = now
    create_task(db, case, "REFERRAL_NOT_ACCEPTED", "Referral was not accepted in time: choose another target", None, source_ref=referral.id)
    record_event(db, actor, case_id=case.id, event_type="REFERRAL_NOT_ACCEPTED_IN_TIME", description="Referral not accepted in time; EXCEPTION set", at=now,
                 new_values={"referralId": referral.id, "status": referral.status})

def process_referral_timeouts(db, now=None) -> int:
    """Scheduler: a referral still SENT after the status limit plus a second limit (R-46) becomes NOT_ACCEPTED_IN_TIME."""
    from datetime import timedelta
    from app.services import settings_store
    now = now or clock.now()
    n = 0
    for r in db.query(Referral).filter(Referral.status == ReferralStatus.SENT.value).all():
        case = db.get(Case, r.case_id)
        first = settings_store.add_limit(r.created_at, settings_store.status_limit(db, CaseStatus.REFERRAL_PENDING, facility_id=case.facility_id))
        second = timedelta(days=settings_store.get_int(db, "referral.second_limit_days", facility_id=case.facility_id))
        if now >= first + second:
            mark_not_accepted(db, sm.SYSTEM, r, case, at=now); n += 1
    return n

def after_patient_response(db, case, *, actor, source, staff_id=None, now=None):
    """Apply what a patient answer means (R-31, T8). The answer may come from the patient's own link or from staff recording it by phone (R-74).
    'Partly' or 'no' sets NOT_EXPLAINED, creates a worklist task and keeps the case in AWAITING_ACK. Acknowledged and understood
    moves a case that needs a confirmatory test to AWAITING_CONFIRMATION (T8)."""
    from app.services.tasks import create_task
    now = now or clock.now()
    facts = sm.acknowledgement_facts(db, case)
    level = sm.understanding_level(sm.latest_response(db, case.id, "UNDERSTANDING"))
    if level in ("PARTLY", "NO") and not case.flag_not_explained:
        case.flag_not_explained = True
        create_task(db, case, "NOT_EXPLAINED", "Patient says the result is not clear", "Contact the patient and explain the result again.", source_ref=f"understanding:{now.isoformat()}")
        record_event(db, actor, case_id=case.id, event_type="CASE_FLAG_SET", description="NOT_EXPLAINED: the patient did not fully understand", at=now, new_values={"flag": "NOT_EXPLAINED", "level": level, "source": source})
    if case.status == CaseStatus.AWAITING_ACK and case.confirmatory_required and facts["acknowledged"] and facts["understood"]:
        sm.apply(db, actor, case, "T8", at=now, ctx={"staff_phone": source == "STAFF_ASSISTED"}, details={"source": source, "recordedByStaffId": staff_id})
