
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.api.v1.deps import clinical_user
from app.models.entities import RoutingRule, Role
from app.services.audit import record_event

router = APIRouter()


class RoutingRuleInput(BaseModel):
    pathway: str = Field(min_length=1, max_length=100)
    resultCategory: str = Field(min_length=1, max_length=200)
    suggestedUrgency: str | None = None
    confirmatoryRequired: bool = False
    specialty: str | None = None
    primaryPool: str | None = None
    backupPool: str | None = None
    timeToAcceptMinutes: int | None = Field(default=None, ge=1)
    timeToAppointmentDays: int | None = Field(default=None, ge=1)
    notes: str | None = None


def require_authorised_staff(user):
    if user.role not in (
        Role.COORDINATOR,
        Role.REFERRING_CLINICIAN,
        Role.NATIONAL_ADMIN,
    ):
        raise HTTPException(403, "Insufficient permissions")


def rule_output(rule):
    return {
        "id": rule.id,
        "pathway": rule.pathway,
        "resultCategory": rule.result_category,
        "suggestedUrgency": rule.suggested_urgency,
        "confirmatoryRequired": rule.confirmatory_required,
        "specialty": rule.specialty,
        "primaryPool": rule.primary_pool,
        "backupPool": rule.backup_pool,
        "timeToAcceptMinutes": rule.time_to_accept_minutes,
        "timeToAppointmentDays": rule.time_to_appointment_days,
        "notes": rule.notes,
        "changedAt": rule.changed_at,
        "changedById": rule.changed_by_id,
    }


@router.get("")
def list_routing_rules(
    db: Session = Depends(get_db),
    user=Depends(clinical_user),
):
    require_authorised_staff(user)

    rules = (
        db.query(RoutingRule)
        .order_by(RoutingRule.pathway, RoutingRule.result_category)
        .all()
    )

    return {
        "success": True,
        "data": [rule_output(rule) for rule in rules],
        "meta": {"total": len(rules), "simulated": True},
    }


@router.post("")
def create_routing_rule(
    payload: RoutingRuleInput,
    db: Session = Depends(get_db),
    user=Depends(clinical_user),
):
    require_authorised_staff(user)

    rule = RoutingRule(
        pathway=payload.pathway.strip(),
        result_category=payload.resultCategory.strip(),
        suggested_urgency=payload.suggestedUrgency,
        confirmatory_required=payload.confirmatoryRequired,
        specialty=payload.specialty,
        primary_pool=payload.primaryPool,
        backup_pool=payload.backupPool,
        time_to_accept_minutes=payload.timeToAcceptMinutes,
        time_to_appointment_days=payload.timeToAppointmentDays,
        notes=payload.notes,
        changed_by_id=user.id,
    )

    db.add(rule)
    db.flush()

    record_event(
        db,
        user,
        case_id=None,
        event_type="ROUTING_RULE_CREATED",
        description="Routing rule created",
        new_values=rule_output(rule),
    )

    db.commit()
    db.refresh(rule)

    return {
        "success": True,
        "data": rule_output(rule),
        "meta": {"simulated": True},
    }


@router.put("/{rule_id}")
def update_routing_rule(
    rule_id: str,
    payload: RoutingRuleInput,
    db: Session = Depends(get_db),
    user=Depends(clinical_user),
):
    require_authorised_staff(user)

    rule = db.get(RoutingRule, rule_id)
    if not rule:
        raise HTTPException(404, "Routing rule not found")

    old_values = rule_output(rule)

    rule.pathway = payload.pathway.strip()
    rule.result_category = payload.resultCategory.strip()
    rule.suggested_urgency = payload.suggestedUrgency
    rule.confirmatory_required = payload.confirmatoryRequired
    rule.specialty = payload.specialty
    rule.primary_pool = payload.primaryPool
    rule.backup_pool = payload.backupPool
    rule.time_to_accept_minutes = payload.timeToAcceptMinutes
    rule.time_to_appointment_days = payload.timeToAppointmentDays
    rule.notes = payload.notes
    rule.changed_by_id = user.id

    db.flush()

    record_event(
        db,
        user,
        case_id=None,
        event_type="ROUTING_RULE_UPDATED",
        description="Routing rule updated",
        old_values=old_values,
        new_values=rule_output(rule),
    )

    db.commit()
    db.refresh(rule)

    return {
        "success": True,
        "data": rule_output(rule),
        "meta": {"simulated": True},
    }
