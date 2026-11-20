"""Urgent specialty routing. Staff route and reassign under /cases; the receiving clinician lists and accepts under /urgent-cases."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.permissions import CREATE_ROLES, can_modify_case, can_view_case, visible_cases
from app.api.v1.deps import clinical_user
from app.models.entities import Case, Facility, Patient, Role, RoutingStatus, Screening
from app.schemas.urgent import RerouteRequest, RouteRequest
from app.services import routing

case_router = APIRouter()      # mounted at /cases
router = APIRouter()           # mounted at /urgent-cases

def _case(db, user, case_id, *, modify):
    from app.api.v1.endpoints.cases import find_case
    case = find_case(db, case_id)
    if not case or not can_view_case(user, case, db): raise HTTPException(404, "Case not found")
    if modify and (user.role not in CREATE_ROLES or not can_modify_case(user, case)): raise HTTPException(403, "Insufficient permissions")
    return case

def _out(db, case):
    return {"success": True, "data": {"id": case.id, "caseId": case.case_number, "priority": case.priority.value, "routing": routing.summary(db, case)}, "meta": {}}

# ---------- staff: route, inspect, reassign ----------

@case_router.post("/{case_id}/urgent-routing")
def route_urgent_case(case_id: str, payload: RouteRequest | None = None, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = _case(db, user, case_id, modify=True)
    p = payload or RouteRequest()
    routing.route_case(db, user, case, clinician_id=p.receivingClinicianId, specialty=p.specialty, first_limit=p.firstLimitMinutes, second_limit=p.secondLimitMinutes)
    db.commit()
    return _out(db, case)

@case_router.get("/{case_id}/urgent-routing")
def get_urgent_routing(case_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)):
    return _out(db, _case(db, user, case_id, modify=False))

@case_router.post("/{case_id}/urgent-routing/reassign")
def reassign_urgent_case(case_id: str, payload: RerouteRequest, db: Session = Depends(get_db), user=Depends(clinical_user)):
    case = _case(db, user, case_id, modify=True)
    routing.reassign_case(db, user, case, clinician_id=payload.receivingClinicianId, reason=payload.reason)
    db.commit()
    return _out(db, case)

# ---------- receiving clinician ----------

def _need_receiving(user):
    if user.role != Role.RECEIVING_CLINICIAN: raise HTTPException(403, "Insufficient permissions")

def _item(db, case):
    patient = db.get(Patient, case.patient_id)
    screening = db.get(Screening, case.screening_id) if case.screening_id else None
    facility = db.get(Facility, case.facility_id)
    return {"id": case.id, "caseId": case.case_number, "priority": case.priority.value, "status": case.status.value,
            "patientLabel": patient.display_label, "age": patient.age_years, "sex": patient.sex,
            "screening": {"type": screening.screening_type, "outcome": screening.outcome, "displayLabel": screening.display_label} if screening else None,
            "facility": {"id": facility.id, "name": facility.name},
            "nextAction": {"code": case.next_action_code, "label": case.next_action_label} if case.next_action_code or case.next_action_label else None,
            "specialty": case.required_specialty, "routingStatus": case.routing_status, "routingDueAt": case.routing_due_at,
            "dueAt": case.due_at, "routing": routing.summary(db, case)}

@router.get("")
def my_urgent_cases(page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100), status: RoutingStatus | None = None,
                    db: Session = Depends(get_db), user=Depends(clinical_user)):
    """Urgent cases routed to the authenticated receiving clinician (awaiting acceptance first, then accepted)."""
    _need_receiving(user)
    q = db.query(Case).filter(Case.routed_clinician_id == user.id, Case.routing_status.in_([RoutingStatus.AWAITING_ACCEPTANCE.value, RoutingStatus.ACCEPTED.value]))
    if status: q = q.filter(Case.routing_status == status.value)
    total = q.count()
    rows = q.order_by(Case.routing_status.asc(), Case.routing_due_at.asc(), Case.id).offset((page - 1) * pageSize).limit(pageSize).all()
    return {"success": True, "data": [_item(db, c) for c in rows], "meta": {"total": total, "page": page, "pageSize": pageSize}}

@router.post("/process-due")
def process_due(db: Session = Depends(get_db), user=Depends(clinical_user)):
    """Apply expired acceptance limits now. The background scheduler does this automatically; staff can trigger it too."""
    if user.role not in (Role.COORDINATOR, Role.NATIONAL_ADMIN): raise HTTPException(403, "Insufficient permissions")
    counts = routing.process_due_routing(db, user, visible_cases(db.query(Case), user))
    db.commit()
    return {"success": True, "data": counts, "meta": {}}

@router.post("/{case_id}/accept")
def accept_urgent_case(case_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)):
    _need_receiving(user)
    case = db.query(Case).filter(((Case.id == case_id) | (Case.case_number == case_id)), Case.routed_clinician_id == user.id).first()
    if not case: raise HTTPException(404, "Urgent case not found")  # not routed to this clinician
    routing.accept_case(db, user, case)
    db.commit()
    return {"success": True, "data": _item(db, case), "meta": {}}
