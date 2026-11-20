from typing import Annotated, Literal
from pydantic import BaseModel, Field, StringConstraints
from app.models.entities import AiKind, Priority
from app.schemas.referrals import RequiredText

Body2000 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Summary = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]

# ---- payloads, one per suggestion kind ----
class IntakePayload(BaseModel):
    patientId: str
    caseId: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]  # proposed case number
    facilityId: str | None = None
    priority: Priority = Priority.NORMAL
    nextActionCode: str | None = Field(default=None, max_length=80)
    nextActionLabel: str | None = Field(default=None, max_length=200)
    rationale: RequiredText | None = None

class UrgencyPayload(BaseModel):
    priority: Priority
    actionability: Literal["ACTIONABLE", "NEEDS_REVIEW", "NOT_ACTIONABLE"]
    rationale: RequiredText
    specialtyNeeded: str | None = Field(default=None, max_length=60)
    confirmatoryTestRequired: bool | None = None
    sourceFields: dict = Field(default_factory=dict)


class MessageDraftPayload(BaseModel):
    channel: Literal["SMS", "EMAIL"]
    body: Body2000
    purpose: str | None = Field(default=None, max_length=200)
    language: Literal["en", "ar"] = "en"
    templateVersion: str = Field(default="v1", max_length=20)

class Citation(BaseModel):
    sourceType: Literal["CASE", "SCREENING", "AUDIT_EVENT", "REFERRAL", "CONSULTATION", "PATIENT_RESPONSE"]
    sourceId: str
    excerpt: str | None = Field(default=None, max_length=500)

class CaseSummaryPayload(BaseModel):
    summary: Summary
    citations: list[Citation] = Field(min_length=1, max_length=50)

class Alternative(BaseModel):
    receivingFacilityId: str
    rationale: RequiredText

class ReferralTargetPayload(BaseModel):
    receivingFacilityId: str
    receivingClinicianId: str | None = None
    rationale: RequiredText
    alternatives: list[Alternative] = Field(default_factory=list, max_length=5)

PAYLOAD_MODELS = {AiKind.INTAKE: IntakePayload, AiKind.URGENCY: UrgencyPayload, AiKind.MESSAGE_DRAFT: MessageDraftPayload,
                  AiKind.CASE_SUMMARY: CaseSummaryPayload, AiKind.REFERRAL_TARGET: ReferralTargetPayload}

class SuggestionCreate(BaseModel):
    kind: AiKind
    caseId: str | None = None  # case id or number; omitted for INTAKE
    payload: dict
    model: str | None = Field(default=None, max_length=80)
    confidence: float | None = Field(default=None, ge=0, le=1)

class SuggestionApprove(BaseModel):
    editedBody: Body2000 | None = None  # MESSAGE_DRAFT only: staff may edit the wording before approving
    note: RequiredText | None = None

class SuggestionReject(BaseModel):
    reason: RequiredText

# ---- messages ----
MESSAGE_KINDS = ("RESULT_NOTICE_ROUTINE", "RESULT_NOTICE_URGENT", "ACK_REMINDER", "APPOINTMENT", "CALLBACK_CONFIRMATION", "CLOSURE_NOTICE")

class MessageCreate(BaseModel):
    caseId: str
    channel: Literal["SMS", "EMAIL"]
    body: Body2000
    kind: Literal["RESULT_NOTICE_ROUTINE", "RESULT_NOTICE_URGENT", "ACK_REMINDER", "APPOINTMENT", "CALLBACK_CONFIRMATION", "CLOSURE_NOTICE"] | None = None
    language: Literal["en", "ar"] = "en"
    templateVersion: str = Field(default="v1", max_length=20)

class MessageApprove(BaseModel):
    editedBody: Body2000 | None = None

class MessageReject(BaseModel):
    reason: RequiredText

class DocumentReadRequest(BaseModel):
    caseId: str
    documentId: str | None = Field(default=None, max_length=120)
    documentText: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30000)]
    patientId: str | None = None
    facilityId: str | None = None
