"""Deterministic, rules-based demo AI suggestions.

The real AI helper lives in backend/ai and submits suggestions through
POST /ai/suggestions. This module gives the same demo capability without a
separate service: practitioners press "Generate suggestions" and the backend
produces CASE_SUMMARY / URGENCY / REFERRAL_TARGET / MESSAGE_DRAFT suggestions
that still require staff approval.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core import clock
from app.models.entities import (
    AiKind,
    AiSuggestion,
    Case,
    CaseStatus,
    Facility,
    Patient,
    Referral,
    ReferralStatus,
    Role,
    Screening,
    SuggestionStatus,
    User,
)

MODEL = "rules-demo-v1"

REFERRAL_STATUSES = {
    CaseStatus.AWAITING_ACK,
    CaseStatus.AWAITING_CONFIRMATION,
    CaseStatus.REFERRAL_PENDING,
}

ABNORMAL_MARKERS = (
    "positive",
    "abnormal",
    "suspect",
    "high-grade",
    "high grade",
    "hsil",
    "lsil",
    "cin2",
    "cin3",
    "malignant",
    "precancer",
)

INCONCLUSIVE_MARKERS = ("inconclusive", "inadequate", "unreadable", "indeterminate")


def _text(value) -> str:
    return str(value or "").replace("_", " ").strip().title()


def _ai_user(db: Session) -> User | None:
    return db.query(User).filter(User.role == Role.AI_SERVICE.value).first()


def _pending(db: Session, case: Case, kind: AiKind) -> bool:
    return (
        db.query(AiSuggestion.id)
        .filter(
            AiSuggestion.case_id == case.id,
            AiSuggestion.kind == kind.value,
            AiSuggestion.status == SuggestionStatus.PENDING.value,
        )
        .first()
        is not None
    )


def _add(db, ai_user, case, kind, payload, confidence=None) -> AiSuggestion:
    s = AiSuggestion(
        kind=kind.value,
        case_id=case.id,
        facility_id=case.facility_id,
        payload=payload,
        model=MODEL,
        confidence=confidence,
        created_by_id=ai_user.id,
    )
    db.add(s)
    return s


def _is_abnormal(*values: str | None) -> bool:
    blob = " ".join(v for v in values if v).lower()
    return any(marker in blob for marker in ABNORMAL_MARKERS)


def _is_inconclusive(*values: str | None) -> bool:
    blob = " ".join(v for v in values if v).lower()
    return any(marker in blob for marker in INCONCLUSIVE_MARKERS)


def generate_for_case(
    db: Session,
    case: Case,
    kinds: list[str] | None = None,
    *,
    include_message: bool = False,
) -> list[AiSuggestion]:
    """Create pending suggestions for one case. Caller commits."""
    ai_user = _ai_user(db)
    if ai_user is None:
        return []

    patient = db.get(Patient, case.patient_id)
    facility = db.get(Facility, case.facility_id)
    screening = db.get(Screening, case.screening_id) if case.screening_id else None

    wanted = {k.upper() for k in kinds} if kinds else {
        AiKind.CASE_SUMMARY.value,
        AiKind.URGENCY.value,
        AiKind.REFERRAL_TARGET.value,
    }
    if include_message:
        wanted.add(AiKind.MESSAGE_DRAFT.value)

    abnormal = _is_abnormal(
        screening.outcome if screening else None,
        screening.display_label if screening else None,
    )
    inconclusive = _is_inconclusive(
        screening.outcome if screening else None,
        screening.display_label if screening else None,
    )
    created: list[AiSuggestion] = []

    if AiKind.CASE_SUMMARY.value in wanted and not _pending(db, case, AiKind.CASE_SUMMARY):
        lines = [
            f"Patient {patient.display_label if patient else 'unknown'}"
            + (f", {patient.age_years} years" if patient and patient.age_years else "")
            + ".",
            f"Facility: {facility.name if facility else 'unknown'}.",
        ]
        if screening:
            lines.append(
                f"Screening: {screening.screening_type} — outcome {screening.outcome} "
                f"({screening.display_label})."
            )
        lines.append(
            f"Case {case.case_number}"
            + (f" (tracker {case.tracker_id})" if case.tracker_id else "")
            + f" is {_text(case.status.value)} with {_text(case.priority.value)} priority."
        )
        if case.confirmatory_required:
            lines.append("A confirmatory test is required.")
        if case.next_action_label:
            lines.append(f"Next action: {case.next_action_label}.")
        if case.due_at:
            lines.append(f"Due: {case.due_at:%Y-%m-%d %H:%M} UTC.")
        flags = [
            name
            for name, flag in (
                ("overdue", case.flag_overdue),
                ("exception", case.flag_exception),
                ("data missing", case.flag_data_missing),
                ("message failed", case.flag_message_failed),
            )
            if flag
        ]
        if flags:
            lines.append(f"Flags: {', '.join(flags)}.")
        citations = [
            {"sourceType": "CASE", "sourceId": case.id, "excerpt": case.case_number}
        ]
        if screening:
            citations.append(
                {
                    "sourceType": "SCREENING",
                    "sourceId": screening.id,
                    "excerpt": f"{screening.screening_type}: {screening.outcome}",
                }
            )
        created.append(
            _add(
                db,
                ai_user,
                case,
                AiKind.CASE_SUMMARY,
                {"summary": " ".join(lines), "citations": citations},
                confidence=0.6,
            )
        )

    if AiKind.URGENCY.value in wanted and not _pending(db, case, AiKind.URGENCY):
        if abnormal:
            priority, actionability = "URGENT", "ACTIONABLE"
            rationale = (
                "The screening outcome is marked abnormal/positive, so this case "
                "should be prioritised and treated as actionable."
            )
        elif inconclusive:
            priority, actionability = "NORMAL", "NEEDS_REVIEW"
            rationale = (
                "The screening outcome is inconclusive; the result needs review "
                "before actionability is confirmed."
            )
        else:
            priority, actionability = "NORMAL", "NOT_ACTIONABLE"
            rationale = (
                "The screening outcome does not contain abnormal markers; routine "
                "follow-up is suggested."
            )
        created.append(
            _add(
                db,
                ai_user,
                case,
                AiKind.URGENCY,
                {
                    "priority": priority,
                    "actionability": actionability,
                    "rationale": rationale,
                    "confirmatoryTestRequired": bool(case.confirmatory_required),
                    "sourceFields": {
                        "screeningOutcome": screening.outcome if screening else None,
                        "screeningType": screening.screening_type if screening else None,
                    },
                },
                confidence=0.55,
            )
        )

    has_active_referral = (
        db.query(Referral.id)
        .filter(
            Referral.case_id == case.id,
            Referral.status.in_(
                (ReferralStatus.SENT.value, ReferralStatus.ACCEPTED.value)
            ),
        )
        .first()
        is not None
    )
    if (
        AiKind.REFERRAL_TARGET.value in wanted
        and not has_active_referral
        and not _pending(db, case, AiKind.REFERRAL_TARGET)
        and case.status in REFERRAL_STATUSES
    ):
        candidates = (
            db.query(Facility)
            .filter(Facility.id != case.facility_id)
            .order_by(Facility.name)
            .all()
        )
        ranked = []
        for f in candidates:
            clinician = (
                db.query(User)
                .filter(
                    User.facility_id == f.id,
                    User.role == Role.RECEIVING_CLINICIAN.value,
                    User.is_active.is_(True),
                )
                .order_by(User.display_name)
                .first()
            )
            ranked.append((f, clinician))
        ranked.sort(key=lambda item: item[1] is None)
        if ranked:
            target, clinician = ranked[0]
            alternatives = [
                {
                    "receivingFacilityId": f.id,
                    "rationale": "Alternative receiving facility from the demo facility list.",
                }
                for f, _ in ranked[1:3]
            ]
            created.append(
                _add(
                    db,
                    ai_user,
                    case,
                    AiKind.REFERRAL_TARGET,
                    {
                        "receivingFacilityId": target.id,
                        "receivingClinicianId": clinician.id if clinician else None,
                        "rationale": (
                            f"Refer to {target.name} because the case needs care at "
                            "another facility"
                            + (
                                " and an active receiving clinician is available."
                                if clinician
                                else "; the referral will be unassigned until a clinician accepts."
                            )
                        ),
                        "alternatives": alternatives,
                    },
                    confidence=0.5,
                )
            )

    if AiKind.MESSAGE_DRAFT.value in wanted and not _pending(
        db, case, AiKind.MESSAGE_DRAFT
    ):
        urgent = abnormal or case.priority.value == "URGENT"
        opening = (
            "Your care team has marked this follow-up as urgent. Please contact us as soon as possible."
            if urgent
            else "A screening result from your recent visit needs a follow-up step."
        )
        next_step = case.next_action_label or "Contact your health facility to discuss your result."
        body = (
            "Hello,\n\n"
            f"{opening}\n"
            f"Next step: {next_step}\n\n"
            "Please reply to confirm you received this message. "
            "If anything is unclear, a member of the care team will explain it.\n\n"
            "This is a simulated message for demonstration only."
        )
        created.append(
            _add(
                db,
                ai_user,
                case,
                AiKind.MESSAGE_DRAFT,
                {
                    "channel": "SMS",
                    "body": body,
                    "purpose": f"RESULT_NOTICE_{'URGENT' if urgent else 'ROUTINE'}_rules_demo",
                    "language": patient.preferred_language if patient and patient.preferred_language in ("en", "ar") else "en",
                    "templateVersion": "v1",
                },
                confidence=None,
            )
        )

    return created


def generate_for_result_case(db: Session, case: Case) -> list[AiSuggestion]:
    """Called after CSV/event ingestion so the review queue is populated."""
    try:
        with db.begin_nested():
            created = generate_for_case(
                db, case, [AiKind.CASE_SUMMARY.value, AiKind.URGENCY.value]
            )
        return created
    except Exception:  # never break event ingestion because of suggestions
        return []
