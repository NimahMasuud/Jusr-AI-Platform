from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core import clock
from app.core.database import get_db
from app.core.permissions import CREATE_ROLES, can_modify_case, can_view_case, visible_cases
from app.api.v1.deps import clinical_user
from app.models.entities import Case, Message, MessageStatus, Role
from app.schemas.ai import MessageApprove, MessageCreate, MessageReject
from app.services.audit import record_event, reject_and_log
from app.services.messaging import attempt_delivery, get_message_provider, process_due_messages

router = APIRouter()

# R-28: a coordinator approves and sends patient messages (Part 1 matrix); clinicians do not.
MESSAGE_ROLES = (Role.COORDINATOR, Role.NATIONAL_ADMIN)

def message_out(m: Message) -> dict:
    return {"id": m.id, "caseId": m.case_id, "channel": m.channel, "kind": m.kind, "language": m.language, "templateVersion": m.template_version, "body": m.body, "status": m.status, "source": m.source, "suggestionId": m.suggestion_id,
            "createdById": m.created_by_id, "approvedById": m.approved_by_id, "approvedAt": m.approved_at, "rejectionReason": m.rejection_reason,
            "attempts": m.attempts, "nextRetryAt": m.next_retry_at, "lastError": m.last_error, "sentAt": m.sent_at, "createdAt": m.created_at}

def _load(db, user, message_id, *, modify) -> tuple[Message, Case]:
    row = visible_cases(db.query(Message, Case).join(Case, Message.case_id == Case.id), user).filter(Message.id == message_id).first()
    if not row: raise HTTPException(404, "Message not found")
    m, case = row
    if modify and (user.role not in MESSAGE_ROLES or not can_modify_case(user, case)): raise HTTPException(403, "Insufficient permissions")
    return m, case

@router.get("")
def list_messages(page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100), status: MessageStatus | None = None, caseId: str | None = None,
                  db: Session = Depends(get_db), user=Depends(clinical_user)):
    q = visible_cases(db.query(Message).join(Case, Message.case_id == Case.id), user)
    if status: q = q.filter(Message.status == status.value)
    if caseId: q = q.filter((Case.id == caseId) | (Case.case_number == caseId))
    total = q.count()
    rows = q.order_by(Message.created_at.desc(), Message.id).offset((page - 1) * pageSize).limit(pageSize).all()
    return {"success": True, "data": [message_out(m) for m in rows], "meta": {"total": total, "page": page, "pageSize": pageSize}}

@router.post("")
def create_message(payload: MessageCreate, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = db.query(Case).filter((Case.id == payload.caseId) | (Case.case_number == payload.caseId)).first()
    if not case or not can_view_case(user, case, db): raise HTTPException(404, "Case not found")
    if user.role not in MESSAGE_ROLES or not can_modify_case(user, case): raise HTTPException(403, "Insufficient permissions")
    kind = payload.kind or ("RESULT_NOTICE_URGENT" if case.priority.value == "URGENT" else "RESULT_NOTICE_ROUTINE")
    m = Message(case_id=case.id, facility_id=case.facility_id, channel=payload.channel, kind=kind, language=payload.language, template_version=payload.templateVersion,
                body=payload.body, source="STAFF", created_by_id=user.id)
    db.add(m); db.flush()
    record_event(db, user, case_id=case.id, event_type="MESSAGE_DRAFTED", description="Message drafted", new_values={"messageId": m.id, "channel": m.channel})
    db.commit()
    return {"success": True, "data": message_out(m), "meta": {}}

@router.post("/process-due")
def process_due(db: Session = Depends(get_db), user=Depends(clinical_user), provider=Depends(get_message_provider)):
    """Retry messages whose retry time has arrived (R-19). Call from a scheduler; no background worker runs inside the API."""
    if user.role not in (Role.COORDINATOR, Role.NATIONAL_ADMIN): raise HTTPException(403, "Insufficient permissions")
    counts = process_due_messages(db, user, provider, visible_cases(db.query(Message).join(Case, Message.case_id == Case.id), user))
    db.commit()
    return {"success": True, "data": counts, "meta": {}}

@router.get("/{message_id}")
def get_message(message_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)):
    m, _ = _load(db, user, message_id, modify=False)
    return {"success": True, "data": message_out(m), "meta": {}}

@router.post("/{message_id}/approve")
def approve_message(message_id: str, payload: MessageApprove | None = None, db: Session = Depends(get_db), user=Depends(clinical_user)):
    m, case = _load(db, user, message_id, modify=True)
    if m.status != MessageStatus.DRAFT.value:
        reject_and_log(db, user, case_id=case.id, attempted="message:approve", status_code=409, code="INVALID_MESSAGE_STATE", message=f"Cannot approve a {m.status} message")
    edited = payload.editedBody if payload else None
    old = m.body
    if edited: m.body = edited
    m.status = MessageStatus.APPROVED.value; m.approved_by_id = user.id; m.approved_at = clock.now()
    record_event(db, user, case_id=case.id, event_type="MESSAGE_APPROVED", description="Message approved for sending",
                 new_values={"messageId": m.id, "edited": bool(edited and edited != old), "templateVersion": m.template_version, "kind": m.kind})
    db.commit()
    return {"success": True, "data": message_out(m), "meta": {}}

@router.post("/{message_id}/reject")
def reject_message(message_id: str, payload: MessageReject, db: Session = Depends(get_db), user=Depends(clinical_user)):
    m, case = _load(db, user, message_id, modify=True)
    if m.status != MessageStatus.DRAFT.value:
        reject_and_log(db, user, case_id=case.id, attempted="message:reject", status_code=409, code="INVALID_MESSAGE_STATE", message=f"Cannot reject a {m.status} message")
    m.status = MessageStatus.REJECTED.value; m.rejection_reason = payload.reason
    record_event(db, user, case_id=case.id, event_type="MESSAGE_REJECTED", description="Message rejected", new_values={"messageId": m.id, "reason": payload.reason})
    db.commit()
    return {"success": True, "data": message_out(m), "meta": {}}

@router.post("/{message_id}/send")
def send_message(message_id: str, db: Session = Depends(get_db), user=Depends(clinical_user), provider=Depends(get_message_provider)):
    m, case = _load(db, user, message_id, modify=True)
    if m.status != MessageStatus.APPROVED.value or not m.approved_by_id:  # R-28: no message may be sent without approval
        reject_and_log(db, user, case_id=case.id, attempted="message:send", status_code=409, code="MESSAGE_NOT_APPROVED", message=f"Only an APPROVED message can be sent; this one is {m.status}")
    attempt_delivery(db, user, m, provider)
    db.commit()
    return {"success": True, "data": message_out(m), "meta": {}}
