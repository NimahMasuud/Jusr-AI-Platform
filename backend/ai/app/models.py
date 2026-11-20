from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """JSON keys are camelCase to match the rest of the API. Snake_case input is still accepted."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class HelperType(str, Enum):
    document_read = "document_read"
    message_draft = "message_draft"
    urgency = "urgency"
    summary = "summary"
    referral_target = "referral_target"


class SuggestionStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    edited = "edited"
    rejected = "rejected"


class Role(str, Enum):
    patient = "patient"
    coordinator = "coordinator"
    referring_clinician = "referring_clinician"
    receiving_clinician = "receiving_clinician"
    facility_admin = "facility_admin"
    ai_service = "ai_service"


class Actor(CamelModel):
    staff_id: str
    role: Role
    specialty: Optional[str] = None
    facility: Optional[str] = None


class Source(CamelModel):
    kind: str  # document | event | config | input
    ref: str  # document id, event id, config rule id, or input name
    quote: Optional[str] = None  # exact text from the document, when there is one


class Suggestion(CamelModel):
    id: str
    case_id: str
    helper: HelperType
    content: dict[str, Any]
    sources: list[Source]
    completeness: str  # complete | partial (set by rules, not guessed by the AI)
    provider: str
    notices: list[str] = Field(default_factory=list)
    status: SuggestionStatus = SuggestionStatus.pending
    requested_by: str
    created_at: str
    decided_by: Optional[str] = None
    decided_role: Optional[str] = None
    decided_at: Optional[str] = None
    decision_note: Optional[str] = None
    edited_content: Optional[dict[str, Any]] = None  # the original in `content` is never overwritten
    simulated: bool = True


class HelperResponse(CamelModel):
    status: str  # suggested | no_suggestion | unavailable
    message: str  # plain-language explanation for the screen
    suggestion: Optional[Suggestion] = None
    manual_instruction: Optional[str] = None  # R-04: what staff do by hand


# ---- Requests ----
class DocumentReadRequest(CamelModel):
    case_id: str
    document_id: str
    document_text: str
    patient_id: Optional[str] = None  # backend patient ID. Needed only when submitting an intake suggestion
    facility_id: Optional[str] = None


class MessageDraftRequest(CamelModel):
    case_id: str
    language: str = "en"
    urgency: str = "routine"  # "routine" or "urgent", as set by a clinician
    next_step: str
    contact: str
    channel: str = "SMS"  # SMS or EMAIL. Used when submitting to the backend
    plain_result_summary: Optional[str] = None  # only text a clinician has approved


class ResultItem(CamelModel):
    test: str  # the test name as listed, for example "PCV - HAEM"
    value: Optional[float] = None  # numeric result
    text: Optional[str] = None  # qualitative result, for example "Negative"
    unit: Optional[str] = None
    upper_limit: Optional[float] = None  # the lab's own upper limit of normal, for enzyme tests


class UrgencyRequest(CamelModel):
    case_id: str
    results: list[ResultItem]


class CaseEvent(CamelModel):
    event_id: str
    timestamp: str
    type: str
    actor_staff_id: Optional[str] = None
    text: str


class SummaryRequest(CamelModel):
    case_id: str
    events: list[CaseEvent]


class ReferralTargetRequest(CamelModel):
    case_id: str
    specialty_needed: str


class DecisionRequest(CamelModel):
    decision: str  # approve | edit | reject
    edited_content: Optional[dict[str, Any]] = None
    note: Optional[str] = None
