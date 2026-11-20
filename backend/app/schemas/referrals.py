from typing import Annotated, Literal
from pydantic import BaseModel, Field, StringConstraints
from app.models.entities import DeclineCode, ReferralStatus

# Mandatory free text: whitespace-only is rejected.
RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]

class ReferralCreate(BaseModel):
    caseId: str  # the case's id, or its case number
    receivingFacilityId: str
    receivingClinicianId: str | None = None
    reason: RequiredText | None = None
    targetSpecialty: str | None = Field(default=None, max_length=60)
    packet: dict | None = None  # the referral packet (section 9): history summary, attachments and so on

class ReferralAssign(BaseModel):
    receivingClinicianId: str

class ReferralAccept(BaseModel):
    note: RequiredText | None = None

class ReferralReject(BaseModel):
    """R-44: a code from the list, with a note for OTHER. Refused (and logged) when neither is given."""
    code: DeclineCode | None = None
    reason: RequiredText | None = None

class ReferralEscalate(BaseModel):
    reason: RequiredText

class ReferralReassign(BaseModel):
    receivingFacilityId: str
    reason: RequiredText

class ConsultationOutcome(BaseModel):
    outcome: RequiredText
