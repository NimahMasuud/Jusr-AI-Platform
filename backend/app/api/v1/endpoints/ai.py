import re

"""AI-assisted workflows. The AI service may only submit suggestions; every effect needs a staff member's approval (R-02, R-08)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.core import clock
from app.core.database import get_db
from app.core.permissions import (
    CREATE_ROLES,
    GLOBAL_ROLES,
    can_modify_case,
    can_view_case,
    visible_cases,
)
from app.api.v1.deps import clinical_user, require_roles
from app.api.v1.endpoints.patients import visible_patients
from app.models.entities import (
    AiKind,
    AiSuggestion,
    AuditEvent,
    Case,
    CaseStatus,
    Consultation,
    Facility,
    Message,
    MessageStatus,
    Patient,
    PatientResponse,
    Referral,
    Role,
    SuggestionStatus,
    User,
)
from app.schemas.ai import (
    PAYLOAD_MODELS,
    SuggestionApprove,
    SuggestionCreate,
    SuggestionReject,
)
from app.services import ai_rules
from app.services.audit import record_event, reject_and_log
from app.services.workflow import create_case_record, create_referral_record
from app.schemas.ai import (
    PAYLOAD_MODELS,
    SuggestionApprove,
    SuggestionCreate,
    SuggestionReject,
    DocumentReadRequest,
)

router = APIRouter()


def _now():
    return clock.now()


# Who may approve each kind (Part 1 matrix): the coordinator approves intake and messages, a clinician sets urgency, the referring clinician approves a referral.
APPROVERS = {
    AiKind.INTAKE: (Role.COORDINATOR, Role.NATIONAL_ADMIN),
    AiKind.MESSAGE_DRAFT: (Role.COORDINATOR, Role.NATIONAL_ADMIN),
    AiKind.URGENCY: (
        Role.REFERRING_CLINICIAN,
        Role.RECEIVING_CLINICIAN,
        Role.NATIONAL_ADMIN,
    ),
    AiKind.REFERRAL_TARGET: (Role.REFERRING_CLINICIAN, Role.NATIONAL_ADMIN),
    AiKind.CASE_SUMMARY: tuple(CREATE_ROLES),
}


def out(s: AiSuggestion) -> dict:
    return {
        "id": s.id,
        "kind": s.kind,
        "status": s.status,
        "caseId": s.case_id,
        "facilityId": s.facility_id,
        "payload": s.payload,
        "model": s.model,
        "confidence": s.confidence,
        "createdAt": s.created_at,
        "decidedById": s.decided_by_id,
        "decidedAt": s.decided_at,
        "decisionNote": s.decision_note,
        "applied": s.applied,
        "requiresStaffApproval": s.status == SuggestionStatus.PENDING.value,
    }


def _visible(q, user):
    if user.role in GLOBAL_ROLES:
        return q
    return q.filter(
        or_(
            AiSuggestion.facility_id == user.facility_id,
            AiSuggestion.case_id.in_(visible_cases(select(Case.id), user)),
        )
    )


def _load(db, user, suggestion_id) -> AiSuggestion:
    s = (
        _visible(db.query(AiSuggestion), user)
        .filter(AiSuggestion.id == suggestion_id)
        .first()
    )
    if not s:
        raise HTTPException(404, "Suggestion not found")
    return s


def _verify_citations(db, case: Case, citations) -> None:
    """Every citation must point at a real record belonging to this case."""
    checks = {
        "CASE": lambda i: i == case.id,
        "SCREENING": lambda i: case.screening_id is not None and i == case.screening_id,
        "AUDIT_EVENT": lambda i: db.query(AuditEvent.id)
        .filter(AuditEvent.id == i, AuditEvent.case_id == case.id)
        .first()
        is not None,
        "REFERRAL": lambda i: db.query(Referral.id)
        .filter(Referral.id == i, Referral.case_id == case.id)
        .first()
        is not None,
        "CONSULTATION": lambda i: db.query(Consultation.id)
        .filter(Consultation.id == i, Consultation.case_id == case.id)
        .first()
        is not None,
        "PATIENT_RESPONSE": lambda i: db.query(PatientResponse.id)
        .filter(PatientResponse.id == i, PatientResponse.case_id == case.id)
        .first()
        is not None,
    }
    for c in citations:
        if not checks[c.sourceType](c.sourceId):
            raise HTTPException(
                422,
                detail={
                    "code": "INVALID_CITATION",
                    "message": f"Citation {c.sourceType} {c.sourceId} does not exist for this case",
                    "sourceType": c.sourceType,
                    "sourceId": c.sourceId,
                },
            )


# ---------- submission (AI service only) ----------


@router.post("")
def submit_suggestion(
    payload: SuggestionCreate,
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.AI_SERVICE.value)),
):
    try:
        data = PAYLOAD_MODELS[payload.kind].model_validate(payload.payload)
    except ValidationError as exc:
        raise HTTPException(
            422,
            detail={
                "code": "INVALID_SUGGESTION_PAYLOAD",
                "message": f"Payload does not match a {payload.kind.value} suggestion",
                "errors": exc.errors(
                    include_url=False, include_context=False, include_input=False
                ),
            },
        )
    case = None
    if payload.kind == AiKind.INTAKE:
        if payload.caseId:
            raise HTTPException(
                422,
                detail={
                    "code": "CASE_NOT_ALLOWED",
                    "message": "An INTAKE suggestion proposes a new case; omit caseId",
                },
            )
        if not data.facilityId or not db.get(Facility, data.facilityId):
            raise HTTPException(
                422,
                detail={
                    "code": "INVALID_FACILITY",
                    "message": "INTAKE needs a valid facilityId in the payload",
                },
            )
        if not db.get(Patient, data.patientId):
            raise HTTPException(404, "Patient not found")
        facility_id = data.facilityId
    else:
        if not payload.caseId:
            raise HTTPException(
                422,
                detail={
                    "code": "CASE_REQUIRED",
                    "message": f"{payload.kind.value} needs a caseId",
                },
            )
        case = (
            db.query(Case)
            .filter((Case.id == payload.caseId) | (Case.case_number == payload.caseId))
            .first()
        )
        if not case:
            raise HTTPException(404, "Case not found")
        facility_id = case.facility_id
        if payload.kind == AiKind.CASE_SUMMARY:
            _verify_citations(db, case, data.citations)
        if payload.kind == AiKind.REFERRAL_TARGET:
            for fid in [data.receivingFacilityId] + [
                a.receivingFacilityId for a in data.alternatives
            ]:
                if not db.get(Facility, fid):
                    raise HTTPException(404, "Receiving facility not found")
    s = AiSuggestion(
        kind=payload.kind.value,
        case_id=case.id if case else None,
        facility_id=facility_id,
        payload=data.model_dump(mode="json"),
        model=payload.model,
        confidence=payload.confidence,
        created_by_id=user.id,
    )
    db.add(s)
    db.flush()
    record_event(
        db,
        user,
        case_id=s.case_id,
        event_type="AI_SUGGESTION_SUBMITTED",
        description=f"AI suggestion submitted: {s.kind}",
        new_values={"suggestionId": s.id, "kind": s.kind, "model": payload.model},
    )
    db.commit()
    return {"success": True, "data": out(s), "meta": {}}


# ---------- message drafting (coordinator approval required) ----------


@router.post("/message-draft")
def create_message_draft(
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(clinical_user),
):
    # Only coordinators and national administrators may create drafts.
    if user.role not in (Role.COORDINATOR, Role.NATIONAL_ADMIN):
        raise HTTPException(
            403, "Only an authorised coordinator can draft patient messages"
        )

    required = ("caseId", "nextStep", "contact")
    if any(not str(payload.get(key, "")).strip() for key in required):
        raise HTTPException(422, "Case, next step and contact are required")

    language = payload.get("language", "en")
    channel = payload.get("channel", "SMS")

    if language not in ("en", "ar"):
        raise HTTPException(422, "Language must be en or ar")

    if channel not in ("SMS", "EMAIL"):
        raise HTTPException(422, "Channel must be SMS or EMAIL")

    case = (
        db.query(Case)
        .filter(
            (Case.id == payload["caseId"]) | (Case.case_number == payload["caseId"])
        )
        .first()
    )

    if not case or not can_view_case(user, case, db):
        raise HTTPException(404, "Case not found")

    if not can_modify_case(user, case):
        raise HTTPException(403, "You cannot draft messages for this case")

    if case.status == CaseStatus.CLOSED:
        raise HTTPException(409, "Cannot draft a message for a closed case")

    # R-68: only synthetic patient data is permitted.
    patient = db.get(Patient, case.patient_id)

    if (
        not patient
        or patient.is_synthetic is not True
        or patient.data_origin != "SYNTHETIC"
    ):
        raise HTTPException(
            403, "Message drafting is restricted to synthetic demo patients"
        )

    next_step = str(payload["nextStep"]).strip()[:500]
    contact = str(payload["contact"]).strip()[:200]

    # Urgency comes from the clinician-set case priority.
    # The message helper cannot independently set urgency (R-36).
    urgency = "urgent" if case.priority.value == "URGENT" else "routine"

    if language == "ar":
        body = (
            "مرحباً،\n\n"
            "تحتاج نتيجة الفحص الأخيرة إلى متابعة.\n"
            f"الخطوة التالية: {next_step}\n\n"
            f"للمساعدة، يرجى التواصل معنا: {contact}\n\n"
            "يرجى الرد لتأكيد استلام هذه الرسالة. "
            "إذا كان هناك أي شيء غير واضح، سيقوم فريق الرعاية بمساعدتك.\n\n"
            "هذه رسالة تجريبية لبيئة العرض فقط."
        )
    else:
        opening = (
            "Your care team has marked this follow-up as urgent. "
            "Please contact us as soon as possible."
            if urgency == "urgent"
            else "A screening result from your recent visit needs a follow-up step."
        )

        body = (
            "Hello,\n\n"
            f"{opening}\n"
            f"Next step: {next_step}\n\n"
            f"For help, please contact us: {contact}\n\n"
            "Please reply to confirm you received this message. "
            "If anything is unclear, a member of the care team will explain it.\n\n"
            "This is a simulated message for demonstration only."
        )

    ai_user = db.query(User).filter(User.role == Role.AI_SERVICE.value).first()

    if not ai_user:
        raise HTTPException(503, "AI suggestion service account is not configured")

    suggestion = AiSuggestion(
        kind=AiKind.MESSAGE_DRAFT.value,
        case_id=case.id,
        facility_id=case.facility_id,
        payload={
            "channel": channel,
            "body": body,
            "purpose": f"RESULT_NOTICE_{urgency.upper()}_template_v1",
            "language": language,
            "templateVersion": "v1",
        },
        model="rules-template-v1",
        confidence=None,
        created_by_id=ai_user.id,
    )

    db.add(suggestion)
    db.flush()

    record_event(
        db,
        user,
        case_id=case.id,
        event_type="AI_MESSAGE_DRAFT_REQUESTED",
        description="Simulated message draft generated; coordinator approval required",
        new_values={
            "suggestionId": suggestion.id,
            "language": language,
            "channel": channel,
            "urgency": urgency,
            "templateVersion": "v1",
            "simulated": True,
        },
    )

    db.commit()
    db.refresh(suggestion)

    return {
        "success": True,
        "data": out(suggestion),
        "meta": {
            "simulated": True,
            "language": language,
            "templateVersion": "v1",
            "requiresStaffApproval": True,
            "message": "Draft created. Coordinator approval is required before sending.",
        },
    }


# ---------- document reading (staff review required) ----------


@router.post("/document-read")
def read_document(
    payload: DocumentReadRequest,
    db: Session = Depends(get_db),
    user=Depends(clinical_user),
):
    case = (
        db.query(Case)
        .filter((Case.id == payload.caseId) | (Case.case_number == payload.caseId))
        .first()
    )

    if not case or not can_view_case(user, case, db):
        raise HTTPException(404, "Case not found")

    if not can_modify_case(user, case):
        raise HTTPException(403, "You cannot process documents for this case")

    if payload.facilityId and payload.facilityId != case.facility_id:
        raise HTTPException(422, "Document facility does not match the case")

    if payload.patientId and payload.patientId != case.patient_id:
        raise HTTPException(422, "Patient does not match the case")

    patient = db.get(Patient, case.patient_id)

    if not patient or not patient.is_synthetic or patient.data_origin != "SYNTHETIC":
        raise HTTPException(
            403, "Document processing is restricted to synthetic demo patients."
        )

    # Deterministic extraction only. No diagnosis or clinical interpretation.
    text = payload.documentText
    fields = {}

    patterns = {
        "resultDate": r"(?im)^\s*(?:result date|date of result|date)\s*[:\-]\s*(.+)$",
        "testName": r"(?im)^\s*(?:test name|test|investigation)\s*[:\-]\s*(.+)$",
        "resultValue": r"(?im)^\s*(?:result|result value|finding)\s*[:\-]\s*(.+)$",
        "orderingClinician": r"(?im)^\s*(?:ordering clinician|requested by|referring clinician)\s*[:\-]\s*(.+)$",
        "specialtyNeeded": r"(?im)^\s*(?:specialty|specialty needed)\s*[:\-]\s*(.+)$",
    }

    for field, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            fields[field] = match.group(1).strip()[:500]

    # The linked case's patient is a candidate, not an automatic match.
    candidates = [
        {
            "patientId": patient.id,
            "displayName": patient.display_label,
            "matchReason": "Patient linked to the selected case; staff verification required.",
        }
    ]

    record_event(
        db,
        user,
        case_id=case.id,
        event_type="AI_DOCUMENT_READ_REQUESTED",
        description="Document text processed using simulated field extraction; staff review required",
        new_values={
            "documentId": payload.documentId,
            "extractedFieldNames": list(fields.keys()),
            "simulated": True,
        },
    )
    db.commit()

    return {
        "success": True,
        "data": {
            "extractedText": text,
            "patientMatchCandidates": candidates,
            "extractedFields": fields,
            "notices": [
                "SIMULATED DATA ONLY.",
                "This is rule-based field extraction, not a live AI model.",
                "Verify every extracted field against the original document.",
                "Patient matching is not confirmed. Staff approval is required.",
                "No case status, priority, ownership or clinical decision was changed.",
            ],
            "simulated": True,
        },
        "meta": {},
    }


# ---------- rules-based generation (demo staff action) ----------


@router.post("/generate")
def generate_suggestions(
    payload: dict | None = None,
    db: Session = Depends(get_db),
    user=Depends(clinical_user),
):
    """Generate pending suggestions for one case or for the visible open cases.

    Deterministic rules only; every result still needs approval from the role
    named in the approver matrix.
    """
    body = payload or {}
    kinds = body.get("kinds")
    if kinds is not None:
        if not isinstance(kinds, list):
            raise HTTPException(422, "kinds must be a list")
        kinds = [str(k).upper() for k in kinds]
        if not set(kinds) <= {k.value for k in AiKind}:
            raise HTTPException(422, "Unknown suggestion kind")

    raw_case = body.get("caseId")
    if raw_case:
        case = (
            db.query(Case)
            .filter((Case.id == raw_case) | (Case.case_number == raw_case))
            .first()
        )
        if not case or not can_view_case(user, case, db):
            raise HTTPException(404, "Case not found")
        cases = [case]
    else:
        q = db.query(Case).filter(Case.status != CaseStatus.CLOSED)
        if user.role not in GLOBAL_ROLES:
            q = q.filter(Case.id.in_(visible_cases(select(Case.id), user)))
        cases = q.order_by(Case.updated_at.desc()).limit(25).all()

    created: list[AiSuggestion] = []
    for case in cases:
        created.extend(ai_rules.generate_for_case(db, case, kinds))
    db.commit()
    return {
        "success": True,
        "data": [out(s) for s in created],
        "meta": {"cases": len(cases), "created": len(created)},
    }


# ---------- reads ----------


@router.get("")
def list_suggestions(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    kind: AiKind | None = None,
    status: SuggestionStatus | None = None,
    caseId: str | None = None,
    db: Session = Depends(get_db),
    user=Depends(clinical_user),
):
    q = _visible(db.query(AiSuggestion), user)
    if kind:
        q = q.filter(AiSuggestion.kind == kind.value)
    if status:
        q = q.filter(AiSuggestion.status == status.value)
    if caseId:
        q = q.filter(
            AiSuggestion.case_id.in_(
                select(Case.id).where(
                    (Case.id == caseId) | (Case.case_number == caseId)
                )
            )
        )
    total = q.count()
    rows = (
        q.order_by(AiSuggestion.created_at.desc(), AiSuggestion.id)
        .offset((page - 1) * pageSize)
        .limit(pageSize)
        .all()
    )
    return {
        "success": True,
        "data": [out(s) for s in rows],
        "meta": {"total": total, "page": page, "pageSize": pageSize},
    }


@router.get("/cases/{case_id}/summary")
def approved_summary(
    case_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)
):
    """The latest staff-approved AI case summary, with its source citations."""
    case = (
        db.query(Case)
        .filter((Case.id == case_id) | (Case.case_number == case_id))
        .first()
    )
    if not case or not can_view_case(user, case, db):
        raise HTTPException(404, "Case not found")
    s = (
        db.query(AiSuggestion)
        .filter(
            AiSuggestion.case_id == case.id,
            AiSuggestion.kind == AiKind.CASE_SUMMARY.value,
            AiSuggestion.status == SuggestionStatus.APPROVED.value,
        )
        .order_by(AiSuggestion.decided_at.desc())
        .first()
    )
    if not s:
        raise HTTPException(404, "No approved summary for this case")
    return {
        "success": True,
        "data": {**out(s), "approvedBy": s.decided_by_id},
        "meta": {},
    }


@router.get("/facilities")
def list_facilities_for_ai(
    db: Session = Depends(get_db),
    user=Depends(require_roles(Role.AI_SERVICE.value)),
):
    """Read-only facility map for the AI helper service, so referral suggestions use real facility IDs."""
    rows = db.query(Facility).order_by(Facility.name).all()
    return {
        "success": True,
        "data": [{"id": f.id, "code": f.code, "name": f.name} for f in rows],
        "meta": {},
    }


@router.get("/{suggestion_id}")
def get_suggestion(
    suggestion_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)
):
    return {"success": True, "data": out(_load(db, user, suggestion_id)), "meta": {}}


# ---------- staff decision ----------


@router.post("/{suggestion_id}/approve")
def approve_suggestion(
    suggestion_id: str,
    payload: SuggestionApprove | None = None,
    db: Session = Depends(get_db),
    user=Depends(clinical_user),
):
    s = _load(db, user, suggestion_id)
    if user.role not in CREATE_ROLES:
        raise HTTPException(403, "Insufficient permissions")
    case = db.get(Case, s.case_id) if s.case_id else None
    if case and not can_modify_case(user, case):
        raise HTTPException(403, "Insufficient permissions")
    if (
        not case
        and user.role != Role.NATIONAL_ADMIN
        and s.facility_id != user.facility_id
    ):
        raise HTTPException(403, "Insufficient permissions")
    kind = AiKind(s.kind)
    if user.role not in APPROVERS[kind]:
        raise HTTPException(403, "Insufficient permissions")
    if payload and payload.editedBody and kind != AiKind.MESSAGE_DRAFT:
        raise HTTPException(
            422,
            detail={
                "code": "EDIT_NOT_ALLOWED",
                "message": "Only a MESSAGE_DRAFT can be edited before approval",
            },
        )
    if s.status != SuggestionStatus.PENDING.value:
        reject_and_log(
            db,
            user,
            case_id=s.case_id,
            attempted="suggestion:approve",
            status_code=409,
            code="SUGGESTION_ALREADY_DECIDED",
            message=f"Suggestion is already {s.status}",
        )
    data = PAYLOAD_MODELS[kind].model_validate(s.payload)
    ref = {"suggestionId": s.id}
    applied: dict = {}
    if kind == AiKind.INTAKE:
        patient = (
            visible_patients(db.query(Patient), user)
            .filter(Patient.id == data.patientId)
            .first()
        )
        if not patient:
            raise HTTPException(404, "Patient not found")
        new_case = create_case_record(
            db,
            user,
            patient=patient,
            case_number=data.caseId,
            facility_id=s.facility_id,
            priority=data.priority,
            next_action_code=data.nextActionCode,
            next_action_label=data.nextActionLabel,
            extra_event=ref,
        )
        s.case_id = new_case.id
        applied = {"caseId": new_case.id, "caseNumber": new_case.case_number}
    elif kind == AiKind.URGENCY:
        if case.status == CaseStatus.CLOSED:
            reject_and_log(
                db,
                user,
                case_id=case.id,
                attempted="suggestion:urgency",
                status_code=409,
                code="CASE_CLOSED",
                message="Cannot change the priority of a closed case",
            )
        old = case.priority.value
        case.priority = data.priority
        case.updated_at = _now()
        record_event(
            db,
            user,
            case_id=case.id,
            event_type="CASE_PRIORITY_CHANGED",
            description="Case priority changed on approving an AI suggestion",
            old_values={"priority": old},
            new_values={"priority": data.priority.value, **ref},
        )
        applied = {"priority": data.priority.value, "actionability": data.actionability}

    elif kind == AiKind.MESSAGE_DRAFT:
        body = payload.editedBody if payload and payload.editedBody else data.body

        template_version = s.payload.get("templateVersion", "v1")
        language = s.payload.get("language", "en")

        m = Message(
            case_id=case.id,
            facility_id=case.facility_id,
            channel=data.channel,
            body=body,
            kind=(
                "RESULT_NOTICE_URGENT"
                if case.priority.value == "URGENT"
                else "RESULT_NOTICE_ROUTINE"
            ),
            status=MessageStatus.APPROVED.value,
            source="AI_SUGGESTION",
            suggestion_id=s.id,
            created_by_id=s.created_by_id,
            approved_by_id=user.id,
            approved_at=_now(),
        )

        db.add(m)
        db.flush()

        record_event(
            db,
            user,
            case_id=case.id,
            event_type="MESSAGE_APPROVED",
            description="Message draft reviewed and approved; no external message sent",
            new_values={
                "messageId": m.id,
                "suggestionId": s.id,
                "edited": body != data.body,
                "channel": data.channel,
                "language": language,
                "templateVersion": template_version,
                "approvedBy": user.id,
                "approvedAt": _now().isoformat(),
                "externalDelivery": False,
            },
        )

        applied = {
            "messageId": m.id,
            "edited": body != data.body,
            "language": language,
            "templateVersion": template_version,
            "externalDelivery": False,
        }

        applied = {"messageId": m.id, "edited": body != data.body}
    elif kind == AiKind.REFERRAL_TARGET:
        r = create_referral_record(
            db,
            user,
            case,
            facility_id=data.receivingFacilityId,
            clinician_id=data.receivingClinicianId,
            reason=data.rationale,
            extra_event=ref,
        )
        applied = {"referralId": r.id}
    s.status = SuggestionStatus.APPROVED.value
    s.decided_by_id = user.id
    s.decided_at = _now()
    s.decision_note = payload.note if payload else None
    s.applied = applied
    record_event(
        db,
        user,
        case_id=s.case_id,
        event_type="AI_SUGGESTION_APPROVED",
        description=f"AI suggestion approved: {s.kind}",
        new_values={**ref, "kind": s.kind, "applied": applied},
    )
    db.commit()
    return {"success": True, "data": out(s), "meta": {}}


@router.post("/{suggestion_id}/reject")
def reject_suggestion(
    suggestion_id: str,
    payload: SuggestionReject,
    db: Session = Depends(get_db),
    user=Depends(clinical_user),
):
    s = _load(db, user, suggestion_id)
    if user.role not in CREATE_ROLES:
        raise HTTPException(403, "Insufficient permissions")
    case = db.get(Case, s.case_id) if s.case_id else None
    if case and not can_modify_case(user, case):
        raise HTTPException(403, "Insufficient permissions")
    if (
        not case
        and user.role != Role.NATIONAL_ADMIN
        and s.facility_id != user.facility_id
    ):
        raise HTTPException(403, "Insufficient permissions")
    if s.status != SuggestionStatus.PENDING.value:
        reject_and_log(
            db,
            user,
            case_id=s.case_id,
            attempted="suggestion:reject",
            status_code=409,
            code="SUGGESTION_ALREADY_DECIDED",
            message=f"Suggestion is already {s.status}",
        )
    s.status = SuggestionStatus.REJECTED.value
    s.decided_by_id = user.id
    s.decided_at = _now()
    s.decision_note = payload.reason
    record_event(
        db,
        user,
        case_id=s.case_id,
        event_type="AI_SUGGESTION_REJECTED",
        description=f"AI suggestion rejected: {s.kind}",
        new_values={"suggestionId": s.id, "kind": s.kind, "reason": payload.reason},
    )
    db.commit()
    return {"success": True, "data": out(s), "meta": {}}
