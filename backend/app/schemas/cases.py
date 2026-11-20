from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator
from app.models.entities import ClosureType, DelayReason, Priority
from app.schemas.referrals import RequiredText

def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None

OptText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]

class CaseCreate(BaseModel):
    patientId: str
    caseId: str = Field(min_length=1, max_length=40)
    facilityId: str | None = None
    priority: Priority = Priority.NORMAL
    nextActionCode: str | None = Field(default=None, max_length=80)
    nextActionLabel: str | None = Field(default=None, max_length=200)
    requiredSpecialty: str | None = Field(default=None, max_length=60)
    confirmatoryRequired: bool = False

class CaseAssign(BaseModel):
    coordinatorId: str | None = None  # the named owner (any active coordinator or clinician); ownerId is the same field
    ownerId: str | None = None

    @model_validator(mode="after")
    def one_of(self):
        if not (self.coordinatorId or self.ownerId):
            raise ValueError("coordinatorId or ownerId is required")
        return self

class ClassifyBody(BaseModel):
    """T3, T4 or T6: a person marks the result actionable (routine or urgent) or not actionable (R-28a)."""
    actionable: bool = True
    urgent: bool = False
    priority: Priority | None = None  # routine cases may be NORMAL or HIGH; urgent cases are URGENT
    specialty: str | None = Field(default=None, max_length=60)
    reason: RequiredText | None = None
    confirmatoryRequired: bool | None = None

class ConfirmMatchBody(BaseModel):
    patientId: str | None = None  # choose a different candidate patient; omitted confirms the current match

class ConfirmatoryOutcomeBody(BaseModel):
    """T11: the confirmatory result shows no further care is needed."""
    outcome: RequiredText
    reason: RequiredText

class DelayReasonRecord(BaseModel):
    code: DelayReason
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("note")
    @classmethod
    def blank_note(cls, v):
        return _clean(v)

    @model_validator(mode="after")
    def other_needs_note(self):
        if self.code == DelayReason.OTHER and not self.note:
            raise ValueError("A note is required when the code is OTHER")
        return self

class ExplainedBody(BaseModel):
    note: RequiredText

class ContactConfirmedBody(BaseModel):
    route: Literal["PHONE", "SMS", "EMAIL", "VISIT", "OTHER"]
    note: RequiredText | None = None

class ResultBody(BaseModel):
    kind: Literal["ORIGINAL", "CONFIRMATORY"] = "CONFIRMATORY"
    testCode: str = Field(min_length=1, max_length=60)
    testName: str | None = Field(default=None, max_length=200)
    value: str = Field(min_length=1, max_length=200)
    abnormal: bool = False
    issuedAt: datetime | None = None

class AppointmentCreate(BaseModel):
    scheduledAt: datetime

class AttendanceBody(BaseModel):
    attendance: Literal["ATTENDED", "MISSED"]
    reasonCode: DelayReason | None = None  # required when MISSED (R-47)
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("note")
    @classmethod
    def blank_note(cls, v):
        return _clean(v)

class TreatmentStartBody(BaseModel):
    kind: Literal["TREATMENT", "MONITORING"]
    startDate: datetime
    note: str | None = Field(default=None, max_length=2000)
    attachmentRef: str | None = Field(default=None, max_length=300)

    @field_validator("note", "attachmentRef")
    @classmethod
    def blank(cls, v):
        return _clean(v)

class ContactAttemptBody(BaseModel):
    route: Literal["PHONE", "SMS", "EMAIL", "VISIT", "OTHER"]
    outcome: Literal["REACHED", "NOT_REACHED"] = "NOT_REACHED"
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("note")
    @classmethod
    def blank_note(cls, v):
        return _clean(v)

class CloseBody(BaseModel):
    closureType: ClosureType
    reason: RequiredText
    decision: str | None = Field(default=None, max_length=2000)
    evidence: str | None = Field(default=None, max_length=2000)
    secondApproverId: str | None = None

    @field_validator("decision", "evidence")
    @classmethod
    def blank(cls, v):
        return _clean(v)

    @field_validator("secondApproverId")
    @classmethod
    def clean_approver_id(cls, v):
        return _clean(v)

class LinkedCaseBody(BaseModel):
    caseId: str = Field(min_length=1, max_length=40)
    reason: RequiredText

class TransferBody(BaseModel):
    newFacilityId: str
    newOwnerId: str | None = None
    reason: RequiredText
