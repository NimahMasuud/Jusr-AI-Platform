from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from uuid import uuid4
from app.core import clock
from app.core.database import get_db
from app.core.permissions import GLOBAL_ROLES, CREATE_ROLES, visible_cases
from app.api.v1.deps import clinical_user
from app.models.entities import Case, CaseStatus, Patient, Priority, Role, User, Facility, Screening
from app.schemas.patients import PatientCreate, SimulationCaseCreate
from app.services import settings_store
from app.services.ai_rules import generate_for_result_case
from app.services.audit import record_event
from app.services.workflow import create_case_record

router = APIRouter()

SIMULATED_STAGE_NEXT_ACTION = {
    "NOTIFYING": ("NOTIFY_PATIENT", "Notify the patient of the result"),
    "AWAITING_ACK": ("PATIENT_ACK", "Await the patient's acknowledgement"),
    "AWAITING_CONFIRMATION": ("CONFIRMATORY_TEST", "Arrange the confirmatory test"),
    "REFERRAL_PENDING": ("REFERRAL_ACCEPT", "Await the receiving clinic's acceptance"),
    "AWAITING_APPOINTMENT": ("APPOINTMENT", "Track the booked appointment"),
    "AWAITING_TREATMENT": ("TREATMENT_FOLLOW_UP", "Monitor treatment or follow-up"),
    "READY_TO_CLOSE": ("CLOSE_CASE", "Close the case once care is confirmed"),
}

def visible_patients(q, user):
    """Patients from the user's own facility, or on a case the user can see."""
    if user.role in GLOBAL_ROLES:
        return q
    on_visible_case = visible_cases(select(Case.patient_id), user)
    if user.role == Role.RECEIVING_CLINICIAN:
        return q.filter(Patient.id.in_(on_visible_case))
    return q.filter(or_(Patient.facility_id == user.facility_id, Patient.id.in_(on_visible_case)))

def _out(p):
    return {"id": p.id, "displayLabel": p.display_label, "ageYears": p.age_years, "sex": p.sex,
            "phone": p.phone, "recordNumber": p.record_number, "isSynthetic": p.is_synthetic}


@router.get("")
def list_patients(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1),
    db: Session = Depends(get_db),
    user=Depends(clinical_user),
):
    patients = (
        visible_patients(db.query(Patient), user)
        .order_by(Patient.display_label)
        .offset(skip)
        .limit(min(limit, 100))
        .all()
    )

    patient_items = []

    for patient in patients:
        # Only count cases visible to this logged-in user.
        cases = (
            visible_cases(db.query(Case), user)
            .filter(Case.patient_id == patient.id)
            .order_by(Case.created_at.desc())
            .all()
        )

        active_cases = [
            case for case in cases
            if case.status.value.upper() not in {"RESOLVED", "CLOSED"}
        ]

        # Patient's registered facility.
        facility = (
            db.get(Facility, patient.facility_id)
            if patient.facility_id else None
        )

        # Find the most recent case with a screening record.
        latest_screening = None

        for case in cases:
            if case.screening_id:
                screening = db.get(Screening, case.screening_id)
                if screening:
                    latest_screening = screening
                    break

        # Most recent case update.
        last_updated = max(
            (
                case.updated_at or case.created_at
                for case in cases
                if case.updated_at or case.created_at
            ),
            default=None,
        )

        patient_items.append({
            **_out(patient),
            "facility": facility.name if facility else "Not recorded",
            "activeCases": len(active_cases),
            "latestScreening": (
                f"{latest_screening.screening_type} — "
                f"{latest_screening.outcome}"
                if latest_screening
                else "Not available"
            ),
            "lastUpdated": last_updated,
        })

    return {
        "success": True,
        "data": patient_items,
        "meta": {},
    }

@router.post("")
def create_patient(payload: PatientCreate, db: Session = Depends(get_db), user=Depends(clinical_user)):
    if user.role not in CREATE_ROLES:
        raise HTTPException(403, "Insufficient permissions")
    patient = Patient(display_label=payload.displayLabel, age_years=payload.ageYears, birth_year=payload.birthYear, sex=payload.sex,
                      phone=payload.phone, record_number=payload.recordNumber, is_synthetic=True, data_origin="SYNTHETIC",
                      facility_id=user.facility_id,
                      preferred_language=payload.preferredLanguage or "en")
    db.add(patient); db.commit(); db.refresh(patient)
    return {"success": True, "data": _out(patient), "meta": {}}


@router.post("/simulation-case")
def create_simulation_case(payload: SimulationCaseCreate, db: Session = Depends(get_db), user=Depends(clinical_user)):
    """Coordinator onboarding: register a patient and open an actionable simulated case."""
    if user.role not in (Role.COORDINATOR, Role.NATIONAL_ADMIN):
        raise HTTPException(403, "Only a coordinator can onboard a simulated case")
    facility_id = payload.facilityId or user.facility_id
    facility = db.get(Facility, facility_id) if facility_id else None
    if not facility:
        raise HTTPException(422, detail={"code": "FACILITY_REQUIRED", "message": "Choose a facility for the patient"})
    now = clock.now()
    patient = Patient(display_label=payload.displayLabel, age_years=payload.ageYears, birth_year=payload.birthYear,
                      sex=payload.sex, phone=payload.phone, record_number=payload.recordNumber,
                      is_synthetic=True, data_origin="SYNTHETIC", facility_id=facility.id,
                      preferred_language=payload.preferredLanguage)
    db.add(patient)
    db.flush()
    case = create_case_record(
        db,
        user,
        patient=patient,
        case_number=f"C-{uuid4().hex[:8].upper()}",
        facility_id=facility.id,
        priority=Priority(payload.priority),
        next_action_code="REVIEW_RESULT",
        next_action_label=payload.nextActionLabel or "Review the screening result with the patient",
        required_specialty=payload.requiredSpecialty,
        confirmatory_required=bool(payload.confirmatoryRequired) if payload.confirmatoryRequired is not None else "abnormal" in payload.outcome.lower() or "positive" in payload.outcome.lower(),
        match_confidence=1.0,
        at=now,
    )
    screening = Screening(patient_id=patient.id, screening_type=payload.screeningType, outcome=payload.outcome,
                          display_label=f"{payload.screeningType}: {payload.outcome}")
    db.add(screening)
    db.flush()
    case.screening_id = screening.id
    case.due_at = settings_store.due_for(db, case.status, now, facility_id=facility.id)
    if payload.initialStatus and payload.initialStatus != case.status.value:
        # Demo seeding: start the synthetic case at a later care stage so staff
        # can preview the patient page at that stage. Real cases still move only
        # through the guarded state machine; this bypass is simulation-only and
        # is recorded as a simulated stage, never as a clinical transition.
        old_status = case.status
        case.status = CaseStatus(payload.initialStatus)
        case.status_entered_at = now
        case.due_at = settings_store.due_for(db, case.status, now, facility_id=facility.id)
        case.next_action_code, case.next_action_label = SIMULATED_STAGE_NEXT_ACTION.get(
            payload.initialStatus, (case.next_action_code, case.next_action_label)
        )
        record_event(db, user, case_id=case.id, event_type="SIMULATED_STAGE_SET",
                     description=f"Simulated case started at stage {case.status.value}",
                     old_values={"status": old_status.value}, new_values={"status": case.status.value, "simulated": True})
    db.flush()
    generate_for_result_case(db, case)
    db.commit()
    db.refresh(case)
    return {
        "success": True,
        "data": {
            "patientId": patient.id,
            "caseId": case.case_number,
            "caseNumber": case.case_number,
            "trackerId": case.tracker_id,
            "status": case.status.value,
            "priority": case.priority.value,
            "facilityId": facility.id,
        },
        "meta": {},
    }

@router.get("/{patient_id}")
def get_patient(patient_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)):
    # 404 (not 403) for patients outside the user's scope, so existence is not disclosed.
    p = visible_patients(db.query(Patient), user).filter(Patient.id == patient_id).first()
    if not p: raise HTTPException(404, "Patient not found")
    return {"success": True, "data": _out(p), "meta": {}}

@router.get("/{patient_id}/profile")
def get_patient_profile(
    patient_id: str,
    db: Session = Depends(get_db),
    user=Depends(clinical_user),
):
    from app.core import clock
    from app.core.permissions import visible_cases
    from app.models.entities import (
        Case,
        Facility,
        Screening,
        PatientLink,
        Message,
    )

    # Confirm that the patient is within this user's permitted scope.
    patient = visible_patients(
        db.query(Patient), user
    ).filter(Patient.id == patient_id).first()

    if not patient:
        raise HTTPException(404, "Patient not found")

    # Only include cases the logged-in user is allowed to see.
    cases = (
        visible_cases(db.query(Case), user)
        .filter(Case.patient_id == patient_id)
        .order_by(Case.created_at.desc())
        .all()
    )

    case_items = []
    screenings = []
    messages = []
    patient_links = []

    seen_screenings = set()

    for case in cases:
        facility = db.get(Facility, case.facility_id)
        screening = (
            db.get(Screening, case.screening_id)
            if case.screening_id else None
        )

        owner = db.get(User, case.coordinator_id) if case.coordinator_id else None

        case_items.append({
            "id": case.id,
            "caseNumber": case.case_number,
            "screeningType": screening.screening_type if screening else "Not recorded",
            "screeningResult": screening.outcome if screening else "Not recorded",
            "priority": str(case.priority.value).lower(),
            "status": case.status.value,
            "assignedTo": owner.display_name if owner else None,
            "facility": facility.name if facility else "Not recorded",
            "createdAt": case.created_at,
            "lastUpdated": case.updated_at,
            "nextAction": case.next_action_label or case.next_action_code,
        })

        if screening and screening.id not in seen_screenings:
            seen_screenings.add(screening.id)
            screenings.append({
                "id": screening.id,
                "screeningType": screening.screening_type,
                "result": screening.outcome,
                "date": case.created_at,
                "facility": facility.name if facility else "Not recorded",
            })

        # Communications belonging to this visible case only.
        case_messages = (
            db.query(Message)
            .filter(Message.case_id == case.id)
            .order_by(Message.created_at.desc())
            .all()
        )

        for message in case_messages:
            status = str(message.status.value if hasattr(message.status, "value") else message.status).upper()

            messages.append({
                "id": message.id,
                "channel": message.channel,
                "description": message.body,
                "status": (
                    "Delivered" if status == "SENT"
                    else "Failed" if status == "FAILED"
                    else "Pending"
                ),
                "date": message.created_at,
            })

        # Links are case-specific. Never expose tokens or token hashes.
        links = (
            db.query(PatientLink)
            .filter(PatientLink.case_id == case.id)
            .order_by(PatientLink.created_at.desc())
            .all()
        )

        for link in links:
            status = str(link.status.value if hasattr(link.status, "value") else link.status).upper()

            if status == "ACTIVE" and link.expires_at and link.expires_at <= clock.now():
                status = "EXPIRED"

            patient_links.append({
                "id": link.id,
                "caseId": case.id,
                "status": status,
                "createdAt": link.created_at,
                "expiresAt": link.expires_at,
            })

    latest_link = patient_links[0] if patient_links else None

    return {
        "success": True,
        "data": {
            "patient": _out(patient),
            "cases": case_items,
            "screenings": screenings,
            "communications": messages,
            "patientLink": {
                "status": (
                    latest_link["status"].title()
                    if latest_link else "Not generated"
                ),
                "expiresAt": latest_link["expiresAt"] if latest_link else None,
            },
            "patientLinks": patient_links,
        },
        "meta": {},
    }