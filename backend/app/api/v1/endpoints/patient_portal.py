"""Patient secure-link access: /p/{token}. Separate from staff authentication; limited to one patient and one case."""
import hashlib
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.core import clock
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_patient_session_token, patient_session_link_id
from app.models.entities import Case, CaseStatus, Facility, LinkStatus, Patient, PatientLink, PatientResponse, Priority, Screening, User
from app.schemas.patient_access import CallbackBody, ConfidenceBody, ReassuranceBody, UnderstandingBody, VerifyBody
from app.services.audit import record_patient_event
from app.services.tasks import create_task
from app.services import state_machine as sm
from app.services.workflow import after_patient_response

router = APIRouter()

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def _now():
    return clock.now()

def _gone(status, code, message, **extra):
    raise HTTPException(status, detail={"code": code, "message": message, **extra})

def load_link(db: Session, token: str) -> PatientLink:
    link = db.query(PatientLink).filter(PatientLink.token_hash == hash_token(token)).first()
    if not link:
        _gone(404, "LINK_NOT_FOUND", "This link is not valid")
    if link.status == LinkStatus.SUPERSEDED.value:
        _gone(410, "LINK_SUPERSEDED", "This link has been replaced by a newer one")
    if link.status == LinkStatus.LOCKED.value:
        _gone(423, "LINK_LOCKED", "This link is locked. Please contact your health facility")
    if link.expires_at <= _now():
        _gone(410, "LINK_EXPIRED", "This link has expired")
    return link

def needs_verification(patient: Patient) -> bool:
    return settings.patient_link_verify_birth_year and patient.birth_year is not None

def attempts_remaining(link: PatientLink) -> int:
    return max(settings.patient_link_max_attempts - link.failed_attempts, 0)

def context(db: Session, token: str, session: str | None, *, require_session: bool = True):
    """Resolve link, case and patient; enforce birth-year verification when it applies."""
    link = load_link(db, token)
    case = db.get(Case, link.case_id); patient = db.get(Patient, link.patient_id)
    # A staff preview link already requires a staff session to create; the
    # birth-year check exists for links that travel to the patient.
    preview = link.delivery_channel == "PREVIEW"
    if require_session and not preview and needs_verification(patient) and patient_session_link_id(session) != link.id:
        _gone(403, "VERIFICATION_REQUIRED", "Please verify your birth year to continue", verificationRequired=True, attemptsRemaining=attempts_remaining(link))
    return link, case, patient

def _record(db, link, case, kind, value):
    db.add(PatientResponse(case_id=case.id, kind=kind, value=value, source="PATIENT_LINK", link_id=link.id))
    record_patient_event(db, case_id=case.id, event_type="PATIENT_RESPONSE", description=f"Patient response: {kind}", new_values={"kind": kind, "linkId": link.id, **(value or {})})

def _ok(kind, **extra):
    return {"success": True, "data": {"recorded": kind, "source": "PATIENT_LINK", **extra}, "meta": {}}

SessionHeader = Header(default=None, alias="X-Patient-Session")

def _progress(case: Case) -> dict:
    """The four-step view for the patient, read from the case status (section 7)."""
    st = case.status
    reviewed = st not in (CaseStatus.NEW, CaseStatus.AWAITING_CLASSIFICATION)
    appointment_done = st in (CaseStatus.AWAITING_TREATMENT, CaseStatus.READY_TO_CLOSE, CaseStatus.CLOSED)
    treatment_done = st in (CaseStatus.READY_TO_CLOSE, CaseStatus.CLOSED)
    steps = [{"key": "RESULT_RECEIVED", "label": "Result received", "done": True}, {"key": "DOCTOR_REVIEWED", "label": "Doctor has reviewed", "done": reviewed},
             {"key": "APPOINTMENT", "label": "Appointment", "done": appointment_done}, {"key": "TREATMENT_OR_MONITORING", "label": "Treatment or monitoring", "done": treatment_done}]
    current = next((i for i, x in enumerate(steps) if not x["done"]), len(steps) - 1)
    return {"steps": steps, "currentStep": current}

def _contact(db, case: Case, facility) -> dict:
    owner = db.get(User, case.coordinator_id) if case.coordinator_id else None
    return {"name": owner.display_name if owner else None, "facility": facility.name, "phone": "+000 000 0000 (simulated)"}

@router.get("/{token}")
def view_link(token: str, session: str | None = SessionHeader, db: Session = Depends(get_db)):
    link, case, patient = context(db, token, session)
    link.last_accessed_at = _now()
    latest = {}
    for r in db.query(PatientResponse).filter(PatientResponse.link_id == link.id).order_by(PatientResponse.created_at).all():
        latest[r.kind] = r.value
    screening = db.get(Screening, case.screening_id) if case.screening_id else None
    facility = db.get(Facility, case.facility_id)
    db.commit()
    status = case.status.value
    priority = case.priority.value
    urgency_text = {
        "URGENT": "Your care team has been asked to act on this result urgently.",
        "HIGH": "This result needs attention soon.",
    }.get(priority, "Your care team is following up as planned.")
    reassurance_available = case.status in (CaseStatus.AWAITING_TREATMENT, CaseStatus.READY_TO_CLOSE, CaseStatus.CLOSED)
    # Only what the patient needs: no age, sex, ids of other records, coordinator or workflow detail.
    return {
        "success": True,
        "data": {
            "patient": {"displayLabel": patient.display_label},
            "facility": {"name": facility.name},
            "screening": {"displayLabel": screening.display_label} if screening else None,
            "nextAction": {"label": case.next_action_label} if case.next_action_label else None,
            "dueAt": case.due_at,
            "expiresAt": link.expires_at,
            "status": status,
            "priority": priority,
            "urgencyText": urgency_text,
            "contact": _contact(db, case, facility),
            "language": patient.preferred_language or "en",
            "reassuranceAvailable": reassurance_available,
            "progress": _progress(case),
            "responses": {
                "acknowledged": "ACKNOWLEDGEMENT" in latest,
                "understood": (latest.get("UNDERSTANDING") or {}).get("understood"),
                "confidence": (latest.get("CONFIDENCE") or {}).get("rating"),
                "explanationStatus": (latest.get("EXPLANATION_STATUS") or {}).get("status"),
                "callbackRequested": "CALLBACK_REQUEST" in latest,
            },
        },
        "meta": {},
    }

@router.post("/{token}/verify")
def verify(token: str, payload: VerifyBody, db: Session = Depends(get_db)):
    link, case, patient = context(db, token, None, require_session=False)
    if not needs_verification(patient):
        return {"success": True, "data": {"verificationRequired": False, "verified": True, "sessionToken": None}, "meta": {}}
    if payload.birthYear != patient.birth_year:
        link.failed_attempts += 1
        if link.failed_attempts >= settings.patient_link_max_attempts:
            link.status = LinkStatus.LOCKED.value; link.locked_at = _now()
            create_task(db, case, "LINK_LOCKED", "Patient link locked after incorrect birth-year attempts",
                        "Resend a new secure link or contact the patient by another route.", source_ref=link.id)
            record_patient_event(db, case_id=case.id, event_type="LINK_LOCKED", description="Link locked after incorrect birth-year attempts", new_values={"linkId": link.id})
            db.commit()
            _gone(423, "LINK_LOCKED", "This link is locked. Please contact your health facility")
        record_patient_event(db, case_id=case.id, event_type="LINK_VERIFICATION_FAILED", description="Incorrect birth year entered", new_values={"linkId": link.id, "attempts": link.failed_attempts})
        db.commit()
        _gone(403, "VERIFICATION_FAILED", "That birth year does not match", attemptsRemaining=attempts_remaining(link))
    link.verified_at = _now()
    record_patient_event(db, case_id=case.id, event_type="LINK_VERIFIED", description="Patient verified by birth year", new_values={"linkId": link.id})
    db.commit()
    return {"success": True, "data": {"verificationRequired": True, "verified": True, "sessionToken": create_patient_session_token(link.id), "expiresInMinutes": settings.patient_session_minutes}, "meta": {}}

@router.post("/{token}/ack")
def acknowledge(token: str, session: str | None = SessionHeader, db: Session = Depends(get_db)):
    link, case, _ = context(db, token, session)
    _record(db, link, case, "ACKNOWLEDGEMENT", {"acknowledged": True}); db.flush()
    after_patient_response(db, case, actor=sm.PATIENT, source="PATIENT_LINK"); db.commit()
    return _ok("ACKNOWLEDGEMENT")

@router.post("/{token}/understanding")
def understanding(token: str, payload: UnderstandingBody, session: str | None = SessionHeader, db: Session = Depends(get_db)):
    link, case, _ = context(db, token, session)
    _record(db, link, case, "UNDERSTANDING", {"level": payload.level, "understood": payload.level == "YES"}); db.flush()
    after_patient_response(db, case, actor=sm.PATIENT, source="PATIENT_LINK"); db.commit()
    return _ok("UNDERSTANDING", understood=payload.level == "YES", level=payload.level)

@router.post("/{token}/confidence")
def confidence(token: str, payload: ConfidenceBody, session: str | None = SessionHeader, db: Session = Depends(get_db)):
    link, case, _ = context(db, token, session)
    _record(db, link, case, "CONFIDENCE", {"rating": payload.rating}); db.commit()
    return _ok("CONFIDENCE", rating=payload.rating)

@router.post("/{token}/not-explained")
def not_explained(token: str, session: str | None = SessionHeader, db: Session = Depends(get_db)):
    link, case, _ = context(db, token, session)
    _record(db, link, case, "EXPLANATION_STATUS", {"status": "NOT_EXPLAINED"})
    case.flag_not_explained = True
    create_task(db, case, "NOT_EXPLAINED", "Patient says the information was not understood or explained",
                "Contact the patient and explain the result.", source_ref=link.id)
    db.commit()
    return _ok("EXPLANATION_STATUS", status="NOT_EXPLAINED")

@router.post("/{token}/callback")
def callback(token: str, payload: CallbackBody | None = None, session: str | None = SessionHeader, db: Session = Depends(get_db)):
    link, case, _ = context(db, token, session)
    value = {"preferredTime": payload.preferredTime if payload else None, "note": payload.note if payload else None}
    _record(db, link, case, "CALLBACK_REQUEST", value)
    detail = " ".join(x for x in (f"Preferred time: {value['preferredTime']}." if value["preferredTime"] else "", value["note"] or "") if x) or None
    create_task(db, case, "CALLBACK_REQUESTED", "Patient requested a call-back", detail, source_ref=link.id)
    from app.api.v1.endpoints.consultations import create_consultation  # a patient call-back consultation, addressed to the case owner (section 9)
    create_consultation(db, sm.PATIENT, case, type="PATIENT_CALLBACK", question=value["note"], recipient_id=case.coordinator_id, preferred_time=value["preferredTime"], source="PATIENT_LINK")
    db.commit()
    return _ok("CALLBACK_REQUEST")

@router.post("/{token}/reassurance")
def reassurance(token: str, payload: ReassuranceBody, session: str | None = SessionHeader, db: Session = Depends(get_db)):
    """R-34: 'Do you feel safely guided so far?' (1 to 5), asked after attendance is recorded. Feeds measure M6."""
    link, case, _ = context(db, token, session)
    if case.status not in (CaseStatus.AWAITING_TREATMENT, CaseStatus.READY_TO_CLOSE, CaseStatus.CLOSED):
        _gone(409, "NOT_YET", "This question is asked after the appointment has been attended")
    _record(db, link, case, "REASSURANCE", {"rating": payload.rating}); db.commit()
    return _ok("REASSURANCE", rating=payload.rating)
