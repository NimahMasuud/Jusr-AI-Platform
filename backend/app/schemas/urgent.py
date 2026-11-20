from typing import Annotated
from pydantic import BaseModel, Field, StringConstraints
from app.models.entities import RoutingStatus
from app.schemas.referrals import RequiredText

Specialty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]

class RouteRequest(BaseModel):
    """Route an URGENT case. Omit receivingClinicianId to pick a qualified clinician automatically.
    The limits default to URGENT_ACCEPTANCE_MINUTES and URGENT_ESCALATION_MINUTES."""
    receivingClinicianId: str | None = None
    specialty: Specialty | None = None
    firstLimitMinutes: int | None = Field(default=None, ge=1, le=10080)
    secondLimitMinutes: int | None = Field(default=None, ge=1, le=10080)

class RerouteRequest(BaseModel):
    receivingClinicianId: str
    reason: RequiredText
