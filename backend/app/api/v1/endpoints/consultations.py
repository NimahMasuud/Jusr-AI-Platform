"""Consultations (section 9, R-11, R-49 to R-52): a child object of the case with its own states. It never changes the case status (R-51)."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.core import clock
from app.core.database import get_db
from app.api.v1.deps import clinical_user
from app.api.v1.endpoints.cases import find_case
from app.core.permissions import GLOBAL_ROLES, can_view_case
from app.models.entities import (Case, CaseStatus, Consultation, ConsultationOutcomeType, ConsultationState as CS, ConsultationType as CT, Role, User)
from app.schemas.referrals import RequiredText
from app.services import settings_store
from app.services.audit import record_event, reject_and_log
from app.services.routing import normalize_specialty, qualified_clinicians
from app.services.state_machine import SYSTEM
from app.services.tasks import create_task

router = APIRouter()
CLINICIAN_ROLES = (Role.REFERRING_CLINICIAN, Role.RECEIVING_CLINICIAN)

class ConsultationCreate(BaseModel):
    caseId: str
    type: CT
    question: RequiredText | None = None
    recipientId: str | None = None
    recipientSpecialty: str | None = Field(default=None, max_length=60)
    preferredTime: str | None = Field(default=None, max_length=500)

class Reply(BaseModel):
    text: RequiredText

class Escalate(BaseModel):
    reason: RequiredText

class Outcome(BaseModel):
    """R-49: an outcome type and a note are both required. Missing ones are refused and logged."""
    outcomeType: ConsultationOutcomeType | None = None
    note: RequiredText | None = None

def due_at_for(db, case: Case, now, urgent=False):
    key = "consultation.limit_urgent" if (urgent or case.priority.value == "URGENT") else "consultation.limit"
    return settings_store.add_limit(now, settings_store.get(db, key, facility_id=case.facility_id))

def create_consultation(db, actor, case: Case, *, type: str, question=None, recipient_id=None, recipient_specialty=None, preferred_time=None,
                        source="STAFF", at=None) -> Consultation:
    now = at or clock.now()
    c = Consultation(case_id=case.id, type=type, state=CS.REQUESTED.value, source=source, requester_id=actor.id if actor and actor.id else None,
                     recipient_id=recipient_id, recipient_specialty=recipient_specialty, question=question, preferred_time=preferred_time,
                     urgent=case.priority.value == "URGENT", due_at=due_at_for(db, case, now), thread=[], created_at=now)
    db.add(c); db.flush()
    record_event(db, actor, case_id=case.id, event_type="CONSULTATION_REQUESTED", description=f"{type.replace('_', ' ').title()} consultation requested", at=now,
                 new_values={"consultationId": c.id, "type": type, "recipientId": recipient_id, "recipientSpecialty": recipient_specialty, "source": source})
    return c

def serialize(db, c: Consultation) -> dict:
    case = db.get(Case, c.case_id)
    def person(uid):
        u = db.get(User, uid) if uid else None
        return {"id": u.id, "displayName": u.display_name, "role": u.role.value} if u else None
    return {"id": c.id, "caseId": case.case_number, "trackerId": case.tracker_id, "type": c.type, "state": c.state, "source": c.source, "requester": person(c.requester_id),
            "recipient": person(c.recipient_id), "recipientSpecialty": c.recipient_specialty, "copiedToCoordinator": c.type == CT.PATIENT_CALLBACK.value,
            "question": c.question, "preferredTime": c.preferred_time, "thread": c.thread or [], "urgent": c.urgent, "dueAt": c.due_at, "escalationStage": c.escalation_stage,
            "acceptedBy": person(c.accepted_by_id), "acceptedAt": c.accepted_at,
            "outcome": ({"type": c.outcome_type, "note": c.outcome_note, "recordedBy": person(c.outcome_by_id), "recordedAt": c.outcome_at} if c.outcome_type else None),
            "escalatedAt": c.escalated_at, "referralId": c.referral_id, "createdAt": c.created_at}

def _load(db, user, cid) -> tuple[Consultation, Case]:
    c = db.get(Consultation, cid)
    if not c: raise HTTPException(404, "Consultation not found")
    case = db.get(Case, c.case_id)
    if not (can_view_case(user, case, db) or _may_answer(user, c, case)): raise HTTPException(404, "Consultation not found")  # a clinician asked by specialty sees it too
    return c, case

def _participant(user, c: Consultation) -> bool:
    return user.id in (c.requester_id, c.recipient_id, c.accepted_by_id) or user.role == Role.NATIONAL_ADMIN

def _may_answer(user, c: Consultation, case: Case) -> bool:
    """Who may accept or record the outcome: the named recipient, a clinician with the specialty, or (for call-backs) a coordinator or the case owner."""
    if user.role == Role.NATIONAL_ADMIN: return True
    if c.type == CT.PATIENT_CALLBACK.value:
        return user.role == Role.COORDINATOR and user.facility_id == case.facility_id or user.id in (c.recipient_id, case.coordinator_id) and user.role in CLINICIAN_ROLES
    if user.role not in CLINICIAN_ROLES: return False
    return user.id == c.recipient_id or (c.recipient_id is None and c.recipient_specialty and user.specialty == c.recipient_specialty)

@router.get("")
def list_consultations(page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100), state: CS | None = None, type: CT | None = None, caseId: str | None = None,
                       mine: bool = False, db: Session = Depends(get_db), user=Depends(clinical_user)):
    q = db.query(Consultation).join(Case, Consultation.case_id == Case.id)
    if user.role not in GLOBAL_ROLES:
        mine_clause = or_(Consultation.requester_id == user.id, Consultation.recipient_id == user.id, Consultation.accepted_by_id == user.id,
                          (Consultation.recipient_id.is_(None) & (Consultation.recipient_specialty == user.specialty)) if user.specialty else False)
        if user.role == Role.COORDINATOR and not mine:
            q = q.filter(or_(mine_clause, Case.facility_id == user.facility_id))
        else:
            q = q.filter(mine_clause)
    elif mine:
        q = q.filter(or_(Consultation.requester_id == user.id, Consultation.recipient_id == user.id))
    if state: q = q.filter(Consultation.state == state.value)
    if type: q = q.filter(Consultation.type == type.value)
    if caseId:
        case = find_case(db, caseId)
        q = q.filter(Consultation.case_id == (case.id if case else "-"))
    total = q.count()
    rows = q.order_by(Consultation.created_at.desc(), Consultation.id).offset((page - 1) * pageSize).limit(pageSize).all()
    return {"success": True, "data": [serialize(db, c) for c in rows], "meta": {"total": total, "page": page, "pageSize": pageSize}}

@router.get("/{consultation_id}")
def get_consultation(consultation_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)):
    c, _ = _load(db, user, consultation_id)
    return {"success": True, "data": serialize(db, c), "meta": {}}

@router.post("")
def request_consultation(payload: ConsultationCreate, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = find_case(db, payload.caseId)
    if not case or not can_view_case(user, case, db): raise HTTPException(404, "Case not found")
    if user.role not in CLINICIAN_ROLES + (Role.COORDINATOR, Role.NATIONAL_ADMIN):
        raise HTTPException(403, "Insufficient permissions")
    if case.status == CaseStatus.CLOSED:
        reject_and_log(db, user, case_id=case.id, attempted="consultation:request", status_code=409, code="CASE_CLOSED", message="A closed case is read-only")
    recipient_id, specialty = payload.recipientId, normalize_specialty(payload.recipientSpecialty)
    if payload.type == CT.PATIENT_CALLBACK:
        recipient_id = recipient_id or case.coordinator_id  # addressed to the case owner, copied to the coordinator
    else:
        if not payload.question:
            raise HTTPException(422, detail={"code": "QUESTION_REQUIRED", "message": "A clinician-to-clinician consultation needs a question"})
        if not (recipient_id or specialty):
            raise HTTPException(422, detail={"code": "RECIPIENT_REQUIRED", "message": "Name a person or a specialty to ask"})
    if recipient_id:
        r = db.get(User, recipient_id)
        if not r or not r.is_active or r.role not in CLINICIAN_ROLES + (Role.COORDINATOR,):
            raise HTTPException(422, detail={"code": "INVALID_RECIPIENT", "message": "The recipient must be an active clinician or coordinator"})
    c = create_consultation(db, user, case, type=payload.type.value, question=payload.question, recipient_id=recipient_id, recipient_specialty=specialty,
                            preferred_time=payload.preferredTime)
    db.commit()
    return {"success": True, "data": serialize(db, c), "meta": {}}

@router.post("/{consultation_id}/accept")
def accept(consultation_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)):
    c, case = _load(db, user, consultation_id)
    if not _may_answer(user, c, case):
        raise HTTPException(403, "Insufficient permissions")
    if c.state not in (CS.REQUESTED.value, CS.ESCALATED.value):
        reject_and_log(db, user, case_id=c.case_id, attempted="consultation:accept", status_code=409, code="INVALID_CONSULTATION_STATE", message=f"Cannot accept a consultation that is {c.state}")
    now = clock.now()
    c.state = CS.ACCEPTED.value; c.accepted_by_id = user.id; c.accepted_at = now
    if c.recipient_id is None: c.recipient_id = user.id
    record_event(db, user, case_id=c.case_id, event_type="CONSULTATION_ACCEPTED", description="Consultation accepted", new_values={"consultationId": c.id}, at=now)
    db.commit()
    return {"success": True, "data": serialize(db, c), "meta": {}}

@router.post("/{consultation_id}/reply")
def reply(consultation_id: str, payload: Reply, db: Session = Depends(get_db), user=Depends(clinical_user)):
    c, case = _load(db, user, consultation_id)
    if not _participant(user, c) and not _may_answer(user, c, case): raise HTTPException(403, "Insufficient permissions")
    if c.state == CS.OUTCOME_RECORDED.value:
        reject_and_log(db, user, case_id=c.case_id, attempted="consultation:reply", status_code=409, code="INVALID_CONSULTATION_STATE", message="The consultation is finished")
    now = clock.now()
    c.thread = list(c.thread or []) + [{"byId": user.id, "byName": user.display_name, "role": user.role.value, "text": payload.text, "at": now.isoformat()}]
    record_event(db, user, case_id=c.case_id, event_type="CONSULTATION_REPLY", description="Consultation reply", new_values={"consultationId": c.id}, at=now)
    db.commit()
    return {"success": True, "data": serialize(db, c), "meta": {}}

@router.post("/{consultation_id}/escalate")
def escalate(consultation_id: str, payload: Escalate, db: Session = Depends(get_db), user=Depends(clinical_user)):
    c, case = _load(db, user, consultation_id)
    if not (_participant(user, c) or user.role == Role.COORDINATOR): raise HTTPException(403, "Insufficient permissions")
    if c.state not in (CS.REQUESTED.value, CS.ACCEPTED.value):
        reject_and_log(db, user, case_id=c.case_id, attempted="consultation:escalate", status_code=409, code="INVALID_CONSULTATION_STATE", message=f"Cannot escalate a consultation that is {c.state}")
    _escalate(db, user, c, case, payload.reason)
    db.commit()
    return {"success": True, "data": serialize(db, c), "meta": {}}

def _escalate(db, actor, c: Consultation, case: Case, reason, at=None):
    now = at or clock.now()
    c.state = CS.ESCALATED.value; c.escalated_at = now; c.escalation_stage += 1
    c.due_at = due_at_for(db, case, now, c.urgent)
    create_task(db, case, "CONSULTATION_ESCALATED", "Consultation not answered in time", reason, source_ref=f"{c.id}:{c.escalation_stage}")
    record_event(db, actor, case_id=c.case_id, event_type="CONSULTATION_ESCALATED", description="Consultation escalated to the coordinator", at=now,
                 new_values={"consultationId": c.id, "stage": c.escalation_stage, "reason": reason})

@router.post("/{consultation_id}/outcome")
def record_outcome(consultation_id: str, payload: Outcome, db: Session = Depends(get_db), user=Depends(clinical_user)):
    c, case = _load(db, user, consultation_id)
    if not _may_answer(user, c, case): raise HTTPException(403, "Insufficient permissions")
    if c.state != CS.ACCEPTED.value:
        reject_and_log(db, user, case_id=c.case_id, attempted="consultation:outcome", status_code=409, code="INVALID_CONSULTATION_STATE",
                       message=f"An outcome can only be recorded once the consultation is accepted; it is {c.state}")
    if not payload.outcomeType or not payload.note:
        reject_and_log(db, user, case_id=c.case_id, attempted="consultation:outcome", status_code=422, code="OUTCOME_REQUIRED",
                       message="An outcome needs a type (advice given, test ordered, referral made, no action) and a note (R-49)")
    now = clock.now()
    c.state = CS.OUTCOME_RECORDED.value; c.outcome_type = payload.outcomeType.value; c.outcome_note = payload.note; c.outcome_by_id = user.id; c.outcome_at = now
    record_event(db, user, case_id=c.case_id, event_type="CONSULTATION_OUTCOME_RECORDED", description="Consultation outcome recorded", at=now,
                 new_values={"consultationId": c.id, "outcomeType": c.outcome_type, "note": c.outcome_note})
    prompt = {"TEST_ORDERED": "The outcome is 'test ordered': the owner should move the case to the matching step (for example awaiting confirmation).",
              "REFERRAL_MADE": "The outcome is 'referral made': the owner should send the matching referral."}.get(c.outcome_type)
    db.commit()
    data = serialize(db, c); data["prompt"] = prompt  # R-51: the status is not changed; the owner is prompted
    return {"success": True, "data": data, "meta": {}}

def process_consultation_escalations(db, now=None) -> int:
    """R-50: a consultation not answered in its limit becomes ESCALATED to the coordinator, then to the specialty backup (same ladder as R-29)."""
    now = now or clock.now()
    n = 0
    for c in db.query(Consultation).filter(Consultation.state.in_([CS.REQUESTED.value, CS.ESCALATED.value]), Consultation.due_at.isnot(None), Consultation.due_at <= now).all():
        case = db.get(Case, c.case_id)
        if c.state == CS.REQUESTED.value:
            _escalate(db, SYSTEM, c, case, "Not answered within its time limit", at=now); n += 1
        elif c.escalation_stage == 1 and c.recipient_specialty:
            backups = [u for u in qualified_clinicians(db, c.recipient_specialty) if u.id != c.recipient_id]
            if backups:
                c.recipient_id = backups[0].id
            _escalate(db, SYSTEM, c, case, "Escalated to the backup for the specialty", at=now); n += 1
    return n
