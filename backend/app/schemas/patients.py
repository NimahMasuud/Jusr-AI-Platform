from typing import Literal
from pydantic import BaseModel, Field

class PatientCreate(BaseModel):
    displayLabel: str = Field(min_length=1, max_length=120)
    ageYears: int | None = Field(default=None, ge=0, le=130)
    sex: str | None = Field(default=None, max_length=30)
    birthYear: int | None = Field(default=None, ge=1850, le=2200)
    recordNumber: str | None = Field(default=None, max_length=60)
    phone: str | None = Field(default=None, max_length=40)
    preferredLanguage: Literal["en", "ar"] | None = None

class SimulationCaseCreate(BaseModel):
    """A coordinator-style onboarding: patient + screening + case in one step."""

    displayLabel: str = Field(min_length=1, max_length=120)
    ageYears: int | None = Field(default=None, ge=0, le=130)
    sex: str | None = Field(default=None, max_length=30)
    birthYear: int | None = Field(default=None, ge=1850, le=2200)
    recordNumber: str | None = Field(default=None, max_length=60)
    phone: str | None = Field(default=None, max_length=40)
    preferredLanguage: Literal["en", "ar"] = "en"
    facilityId: str | None = None
    screeningType: str = Field(default="Cervical screening", min_length=1, max_length=100)
    outcome: str = Field(default="Abnormal", min_length=1, max_length=100)
    priority: Literal["NORMAL", "URGENT"] = "NORMAL"
    confirmatoryRequired: bool | None = None
    nextActionLabel: str | None = Field(default=None, max_length=200)
    requiredSpecialty: str | None = Field(default=None, max_length=60)
    initialStatus: Literal[
        "AWAITING_CLASSIFICATION",
        "NOTIFYING",
        "AWAITING_ACK",
        "AWAITING_CONFIRMATION",
        "REFERRAL_PENDING",
        "AWAITING_APPOINTMENT",
        "AWAITING_TREATMENT",
        "READY_TO_CLOSE",
    ] | None = None
