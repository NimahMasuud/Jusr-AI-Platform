"""The case state machine: transitions T1 to T17 held in one table of data (Developer Guide Part 1, section 3).

The API never lets a screen set a status directly. Every status change goes through apply(), which checks who
may do it, that the case is in the right status and that the guard conditions hold. A refused transition changes
nothing and writes a log entry (R-12). Every successful one writes a CASE_TRANSITION event; the measures page is
calculated from those events.
"""
from dataclasses import dataclass, field
from datetime import timedelta
from types import SimpleNamespace
from app.core import clock
from app.models.entities import (Case, CaseStatus, Closure, ClosureType, Consultation, ConsultationState, ContactAttempt, Priority, ReferralStatus,
                                 PatientResponse, Result, TreatmentStart, Appointment, Attendance, Referral, User)
from app.services import settings_store, tracker
from app.services.audit import record_event, reject_and_log

S = CaseStatus
UNSET = object()
SYSTEM = SimpleNamespace(id=None, role=SimpleNamespace(value="SYSTEM"))
PATIENT = SimpleNamespace(id=None, role=SimpleNamespace(value="PATIENT"))

COORD, REFER, RECV, NAT, SYS, PAT = "COORDINATOR", "REFERRING_CLINICIAN", "RECEIVING_CLINICIAN", "NATIONAL_ADMIN", "SYSTEM", "PATIENT"
CLINICIANS = {REFER, RECV}
OPEN_STATUSES = tuple(s for s in S if s != S.CLOSED)

@dataclass(frozen=True)
class Transition:
    id: str
    frm: tuple            # statuses the case may be in; empty means any open status (T17)
    to: S
    trigger: str
    roles: frozenset      # who may do it ("SYSTEM" and "PATIENT" are not staff roles)
    refused_unless: str

def _t(id, frm, to, trigger, roles, refused_unless):
    return Transition(id, tuple(frm), to, trigger, frozenset(roles) | {NAT}, refused_unless)  # national admin acts as a supervisor

TRANSITIONS: dict[str, Transition] = {t.id: t for t in [
    _t("T1", [], S.NEW, "Result event received", {SYS, COORD, REFER}, "Event is valid and tied to a facility"),
    _t("T2", [S.NEW], S.AWAITING_CLASSIFICATION, "Patient match confirmed", {SYS, COORD}, "Match is confirmed by a person when confidence is low"),
    _t("T3", [S.AWAITING_CLASSIFICATION], S.NOTIFYING, "Marked actionable, routine", CLINICIANS, "Urgency recorded by a person"),
    _t("T4", [S.AWAITING_CLASSIFICATION], S.URGENT_ROUTING, "Marked actionable, urgent", CLINICIANS, "Urgency recorded by a person, specialty chosen"),
    _t("T5", [S.URGENT_ROUTING], S.NOTIFYING, "Qualified person accepts", CLINICIANS, "Acceptor's profile specialty matches the case (R-13)"),
    _t("T6", [S.AWAITING_CLASSIFICATION], S.CLOSED, "Marked not actionable", CLINICIANS, "A reason is recorded"),
    _t("T7", [S.NOTIFYING], S.AWAITING_ACK, "Message approved, sent, delivery confirmed", {COORD, SYS}, "Approval logged before sending"),
    _t("T8", [S.AWAITING_ACK], S.AWAITING_CONFIRMATION, "Patient acknowledged and understood, or staff phone confirms", {PAT, COORD, SYS}, "Confirmatory test is required for this case"),
    _t("T9", [S.AWAITING_ACK], S.REFERRAL_PENDING, "Same acknowledgement, no confirmatory test needed, referral sent", CLINICIANS, "Referral has a named target"),
    _t("T10", [S.AWAITING_CONFIRMATION], S.REFERRAL_PENDING, "Confirmatory result received, referral sent", CLINICIANS, "Result stored"),
    _t("T11", [S.AWAITING_CONFIRMATION], S.READY_TO_CLOSE, "Confirmatory result shows no further care needed", CLINICIANS, "Outcome and reason recorded"),
    _t("T12", [S.REFERRAL_PENDING], S.AWAITING_APPOINTMENT, "Receiver accepts", {RECV}, "A named new owner is recorded"),
    _t("T13", [S.REFERRAL_PENDING], S.REFERRAL_PENDING, "Receiver declines", {RECV}, "Reason recorded. EXCEPTION and UNASSIGNED set, then a new referral or owner follows"),
    _t("T14", [S.AWAITING_APPOINTMENT], S.AWAITING_TREATMENT, "Attendance recorded", {RECV, COORD, SYS}, "Appointment date and attendance recorded"),
    _t("T15", [S.AWAITING_TREATMENT], S.READY_TO_CLOSE, "Treatment or monitoring start recorded", {RECV, SYS}, "A start record is attached"),
    _t("T16", [S.READY_TO_CLOSE], S.CLOSED, "Named person closes", {COORD, REFER, RECV}, "Closure rules are met. The system never triggers this (R-15)"),
    _t("T17", [], S.CLOSED, "Authorised decision, no care route", CLINICIANS, "A closure type and reason from the list"),
]}

def transition_table() -> list[dict]:
    return [{"id": t.id, "from": [s.value for s in t.frm] or "ANY_OPEN", "to": t.to.value, "trigger": t.trigger,
             "who": sorted(t.roles - {NAT}), "refusedUnless": t.refused_unless} for t in TRANSITIONS.values()]

# ---------------------------------------------------------------- flags and facts

def flags_of(case: Case) -> list[str]:
    """The flags that are set. URGENT follows the case priority; UNASSIGNED follows the missing owner (R-16)."""
    out = []
    if case.status == S.CLOSED:
        return out
    if case.priority == Priority.URGENT: out.append("URGENT")
    if case.flag_overdue: out.append("OVERDUE")
    if case.flag_exception: out.append("EXCEPTION")
    if case.coordinator_id is None: out.append("UNASSIGNED")
    if case.flag_data_missing: out.append("DATA_MISSING")
    if case.flag_message_failed: out.append("MESSAGE_FAILED")
    if case.flag_not_explained: out.append("NOT_EXPLAINED")
    return out

def latest_response(db, case_id, kind):
    return db.query(PatientResponse).filter(PatientResponse.case_id == case_id, PatientResponse.kind == kind).order_by(PatientResponse.created_at.desc(), PatientResponse.id).first()

def understanding_level(r) -> str | None:
    if not r or not r.value: return None
    v = r.value
    if v.get("level"): return v["level"]
    if "understood" in v: return "YES" if v["understood"] else "NO"
    return None

def acknowledgement_facts(db, case) -> dict:
    ack = latest_response(db, case.id, "ACKNOWLEDGEMENT")
    und = latest_response(db, case.id, "UNDERSTANDING")
    return {"acknowledged": bool(ack and (ack.value or {}).get("acknowledged", True)), "understood": understanding_level(und) == "YES",
            "ackSource": ack.source if ack else None}

def has_confirmatory(db, case) -> bool:
    return db.query(Result.id).filter(Result.case_id == case.id, Result.kind == "CONFIRMATORY").first() is not None

# ---------------------------------------------------------------- closure rules (sections 3 and 10)

CLINICIAN_TYPES = {ClosureType.NOT_ACTIONABLE, ClosureType.NO_FURTHER_CARE, ClosureType.PATIENT_DECLINED, ClosureType.UNREACHABLE}

def valid_closure_types(case: Case) -> list[str]:
    """Only types valid for the case's current status are offered (section 10)."""
    if case.status == S.READY_TO_CLOSE:
        return [t.value for t in ClosureType]
    if case.status == S.CLOSED:
        return []
    return [t.value for t in ClosureType if t not in (ClosureType.CARE_CONFIRMED,)]

def can_close(user, case: Case, closure_type: ClosureType) -> bool:
    role = user.role.value
    if role == NAT: return True
    if role == COORD:
        return bool(user.authorised_to_close) and closure_type not in CLINICIAN_TYPES
    if role in CLINICIANS:
        if closure_type == ClosureType.OTHER:
            return bool(user.authorised_to_close)
        return case.coordinator_id == user.id or (bool(user.authorised_to_close) and closure_type in (ClosureType.CARE_CONFIRMED, ClosureType.MOVED_OR_TRANSFERRED))
    return False

def closure_checklist(db, case: Case, closure_type: ClosureType, *, decision=None, evidence=None, reason=None) -> list[dict]:
    """Each evidence item for the chosen type as present or missing, with the record that satisfies it (R-53)."""
    items = []
    def item(name, present, ref=None):
        items.append({"item": name, "present": bool(present), "ref": ref})
    item("A reason", reason)
    treat = db.query(TreatmentStart).filter(TreatmentStart.case_id == case.id).first()
    outcome = db.query(Consultation).filter(Consultation.case_id == case.id, Consultation.state == ConsultationState.OUTCOME_RECORDED.value,
                                            Consultation.type == "CLINICIAN_TO_CLINICIAN").first()
    confirm = db.query(Result).filter(Result.case_id == case.id, Result.kind == "CONFIRMATORY").first()
    if closure_type == ClosureType.CARE_CONFIRMED:
        item("A treatment or monitoring start record, or a specialist outcome note", treat or outcome, {"treatmentStartId": treat.id} if treat else ({"consultationId": outcome.id} if outcome else None))
    elif closure_type == ClosureType.NOT_ACTIONABLE:
        item("The clinician's decision", decision)
    elif closure_type == ClosureType.NO_FURTHER_CARE:
        item("A confirmatory result", confirm, {"resultId": confirm.id} if confirm else None)
        item("The clinician's decision", decision)
    elif closure_type == ClosureType.PATIENT_DECLINED:
        item("A documented informed refusal", evidence)
        item("The clinician's decision", decision)
    elif closure_type == ClosureType.UNREACHABLE:
        need_n = settings_store.get_int(db, "closure.unreachable_min_attempts", facility_id=case.facility_id)
        need_r = settings_store.get_int(db, "closure.unreachable_min_routes", facility_id=case.facility_id)
        window_days = settings_store.get_int(db, "closure.unreachable_window_days", facility_id=case.facility_id)

        # R-55: only attempts inside the window count, so an old attempt cannot satisfy the rule.
        q = db.query(ContactAttempt).filter(ContactAttempt.case_id == case.id)
        if window_days:
            q = q.filter(ContactAttempt.created_at >= clock.now() - timedelta(days=window_days))
        attempts = q.all()

        routes = {a.route for a in attempts}

        item(f"At least {need_n} logged contact attempts in the last {window_days} days (found {len(attempts)})", len(attempts) >= need_n, {"attemptIds": [a.id for a in attempts]})
        item(f"Attempts by at least {need_r} routes (found {len(routes)})", len(routes) >= need_r)
        item("The clinician's decision", decision)
    elif closure_type == ClosureType.MOVED_OR_TRANSFERRED:
        accepted = db.query(Referral).filter(Referral.case_id == case.id, Referral.status == ReferralStatus.ACCEPTED.value).first()
        item("The receiving provider's acceptance, or a documented hand-off", accepted or evidence, {"referralId": accepted.id} if accepted else None)
    elif closure_type == ClosureType.OTHER:
        approved_closure = (
            db.query(Closure)
            .filter(
                Closure.case_id == case.id,
                Closure.closure_type == ClosureType.OTHER.value,
                Closure.status == "CLOSED",
                Closure.second_signoff_by_id.isnot(None),
            )
            .order_by(Closure.requested_at.desc())
            .first()
        )
        item(
            "A second authorised person's sign-off",
            approved_closure is not None,
            {"closureId": approved_closure.id} if approved_closure else None,
        )
    return items

def missing_for_closure(db, case, closure_type, **kw) -> list[str]:
    missing = [i["item"] for i in closure_checklist(db, case, closure_type, **kw) if not i["present"] and i["item"] != "A second authorised person's sign-off"]
    return missing

# ---------------------------------------------------------------- the engine

def _refuse(db, actor, case, tid, status_code, code, message):
    reject_and_log(db, actor, case_id=case.id, attempted=f"{tid}:{case.status.value}", status_code=status_code, code=code, message=message)

def _guard(db, actor, case, tid, ctx):
    """Guard conditions per transition. Refuses with a plain reason; returns normally when satisfied."""
    ctx = ctx or {}
    role = actor.role.value
    if tid == "T2" and role == SYS and float(ctx.get("confidence", 0)) < 1.0:
        _refuse(db, actor, case, tid, 422, "MATCH_NEEDS_PERSON", "A low-confidence patient match must be confirmed by a person")
    if tid == "T4" and not case.required_specialty and not ctx.get("specialty"):
        _refuse(db, actor, case, tid, 422, "SPECIALTY_REQUIRED", "An urgent case needs a specialty chosen")
    if tid == "T5":
        clinician = ctx.get("clinician")
        if clinician is None or not clinician.specialty or clinician.specialty != case.required_specialty:
            _refuse(db, actor, case, tid, 403, "SPECIALTY_MISMATCH",
                    f"Your specialty {getattr(clinician, 'specialty', None) or 'none'} does not match the required specialty {case.required_specialty}")
    if tid == "T6" and not ctx.get("reason"):
        _refuse(db, actor, case, tid, 422, "REASON_REQUIRED", "Marking a result not actionable needs a reason")
    if tid == "T7":
        m = ctx.get("message")
        if m is None or not m.approved_by_id:
            _refuse(db, actor, case, tid, 409, "MESSAGE_NOT_APPROVED", "The patient message must be approved before delivery counts")
    if tid in ("T8", "T9"):
        facts = acknowledgement_facts(db, case)
        staff_phone = bool(ctx.get("staff_phone"))
        if not ((facts["acknowledged"] and facts["understood"]) or staff_phone):
            _refuse(db, actor, case, tid, 422, "ACKNOWLEDGEMENT_REQUIRED", "The patient must acknowledge and understand the result, or staff must confirm by phone")
        if tid == "T8" and not case.confirmatory_required:
            _refuse(db, actor, case, tid, 409, "CONFIRMATORY_NOT_REQUIRED", "No confirmatory test is required for this case")
        if tid == "T9" and case.confirmatory_required:
            _refuse(db, actor, case, tid, 409, "CONFIRMATORY_REQUIRED", "A confirmatory test is required before the referral")
        if tid == "T9" and not ctx.get("referral"):
            _refuse(db, actor, case, tid, 422, "REFERRAL_TARGET_REQUIRED", "The referral needs a named target")
    if tid in ("T10", "T11") and not has_confirmatory(db, case):
        _refuse(db, actor, case, tid, 422, "CONFIRMATORY_RESULT_REQUIRED", "The confirmatory result has not been received")
    if tid == "T11" and not (ctx.get("outcome") and ctx.get("reason")):
        _refuse(db, actor, case, tid, 422, "OUTCOME_REQUIRED", "Record the outcome and the reason")
    if tid == "T12" and not ctx.get("new_owner"):
        _refuse(db, actor, case, tid, 422, "OWNER_REQUIRED", "Accepting a referral needs a named new owner")
    if tid == "T13" and not ctx.get("reason"):
        _refuse(db, actor, case, tid, 422, "DECLINE_REASON_REQUIRED", "Declining a referral needs a reason")
    if tid == "T14":
        a = ctx.get("appointment")
        if a is None or not a.scheduled_at or a.attendance != Attendance.ATTENDED.value:
            _refuse(db, actor, case, tid, 422, "ATTENDANCE_REQUIRED", "Record the appointment date and that the patient attended")
    if tid == "T15":
        r = ctx.get("start")
        if r is None or not r.start_date or not (r.note or r.attachment_ref):
            _refuse(db, actor, case, tid, 422, "START_RECORD_REQUIRED", "Treatment or monitoring start needs a start record with a date and a note or document")
    if tid in ("T16", "T17"):
        if role in (SYS, "AI_SERVICE", PAT):
            _refuse(db, actor, case, tid, 403, "CLOSURE_IS_HUMAN", "Closure is a human act; the system and the AI service cannot close a case (R-15)")
        if case.flag_data_missing:
            _refuse(db, actor, case, tid, 409, "DATA_MISSING", "Data missing: a facility feed is missing or incomplete, so this case cannot be closed yet (R-14)")

def apply(db, actor, case: Case, tid: str, *, ctx=None, details=None, at=None, owner=UNSET, flags=None, event_type="CASE_TRANSITION") -> Case:
    """Perform transition `tid`. Caller commits. Refusals roll back, log and raise."""
    t = TRANSITIONS[tid]
    role = actor.role.value
    if case.status == S.CLOSED:
        _refuse(db, actor, case, tid, 409, "CASE_CLOSED", "A closed case is read-only; start a new linked case instead (R-56)")
    if role not in t.roles:
        _refuse(db, actor, case, tid, 403, "ROLE_NOT_ALLOWED", f"A {role} cannot perform {tid} ({t.trigger}); it needs {', '.join(sorted(t.roles - {NAT}))}")
    if t.frm and case.status not in t.frm:
        _refuse(db, actor, case, tid, 409, "INVALID_STATUS_TRANSITION", f"{tid} ({t.trigger}) needs the case to be {' or '.join(s.value for s in t.frm)}, but it is {case.status.value}")
    _guard(db, actor, case, tid, ctx)
    now = at or clock.now()
    old = case.status
    case.status = t.to
    if t.to != old:
        case.status_entered_at = now
        case.due_at = settings_store.due_for(db, t.to, now, facility_id=case.facility_id)
        case.flag_overdue = False  # OVERDUE clears when the status changes
        case.delay_reason_code = None; case.delay_reason_note = None; case.delay_reason_recorded_at = None; case.delay_reason_recorded_by_id = None
    if owner is not UNSET:
        case.coordinator_id = owner
    for flag, value in (flags or {}).items():
        setattr(case, f"flag_{flag.lower()}", value)
    case.updated_at = now
    record_event(db, actor, case_id=case.id, event_type=event_type, description=f"{tid}: {t.trigger}", at=now,
                 old_values={"status": old.value}, new_values={"status": t.to.value, "transition": tid, **(details or {})})
    return case

def open_case(db, actor, case: Case, *, at=None, details=None) -> Case:
    """T1: a new case in NEW. The case has been added to the session by the caller."""
    now = at or clock.now()
    case.status = S.NEW; case.status_entered_at = now; case.created_at = now; case.updated_at = now
    case.due_at = settings_store.due_for(db, S.NEW, now, facility_id=case.facility_id)
    db.flush()
    record_event(db, actor, case_id=case.id, event_type="CASE_TRANSITION", description=f"T1: {TRANSITIONS['T1'].trigger}", at=now,
                 new_values={"status": "NEW", "transition": "T1", **(details or {})})
    return case

def confirm_match(db, actor, case: Case, *, confidence: float, at=None, details=None) -> Case:
    """T2, and the tracker ID is created here (R-20)."""
    if case.tracker_id is None:
        case.tracker_id = tracker.new_tracker_id(db)
    case.match_confidence = confidence
    case.match_confirmed_by_id = actor.id
    return apply(db, actor, case, "T2", ctx={"confidence": confidence}, at=at, details={"trackerId": case.tracker_id, "matchConfidence": confidence, **(details or {})})

# ---------------------------------------------------------------- OVERDUE (A-04)

def sync_overdue(db, cases, now=None, actor=SYSTEM) -> int:
    """Set OVERDUE on open cases whose status limit has passed and that have no follow-up since entering the status. Caller commits."""
    now = now or clock.now()
    n = 0
    for c in cases:
        if c.status == S.CLOSED or c.flag_overdue or c.due_at is None or c.due_at >= now:
            continue
        if c.delay_reason_recorded_at is not None and c.status_entered_at is not None and c.delay_reason_recorded_at >= c.status_entered_at:
            continue  # a follow-up with a reason code was recorded for this status
        c.flag_overdue = True
        record_event(db, actor, case_id=c.id, event_type="CASE_FLAG_SET", description="OVERDUE: the time limit for this status has passed", at=now,
                     new_values={"flag": "OVERDUE", "status": c.status.value, "dueAt": c.due_at.isoformat()})
        n += 1
    return n

def refresh_due_dates(db, status_value: str | None = None) -> int:
    """A changed time limit takes effect on cases already in the status (A-28): their due date is recalculated from when they entered it."""
    n = 0
    q = db.query(Case).filter(Case.status != S.CLOSED, Case.status_entered_at.isnot(None))
    if status_value: q = q.filter(Case.status == S(status_value))
    for c in q.all():
        due = settings_store.due_for(db, c.status, c.status_entered_at, facility_id=c.facility_id)
        if due != c.due_at:
            c.due_at = due; n += 1
    return n

def process_overdue(db, now=None) -> dict:
    from sqlalchemy import select
    now = now or clock.now()
    due = db.query(Case).filter(Case.status != S.CLOSED, Case.flag_overdue.is_(False), Case.due_at < now).with_for_update(skip_locked=True, of=Case).all()
    return {"flagged": sync_overdue(db, due, now)}
