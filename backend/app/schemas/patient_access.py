from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, Field, StringConstraints

Text500 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Text1000 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]

class VerifyBody(BaseModel):
    birthYear: int = Field(ge=1850, le=2200)

class UnderstandingBody(BaseModel):
    """Yes, partly or no (section 7). A plain true or false is still accepted: true is YES, false is NO."""
    understood: bool | Literal["YES", "PARTLY", "NO"]

    @property
    def level(self) -> str:
        return ("YES" if self.understood else "NO") if isinstance(self.understood, bool) else self.understood

class ConfidenceBody(BaseModel):
    rating: int = Field(ge=1, le=5)

class CallbackBody(BaseModel):
    preferredTime: Text500 | None = None
    note: Text500 | None = None

class AssistedResponseCreate(BaseModel):
    """Every field is required (register section 5). Recorded as staff-assisted, never as the patient's own submission."""
    acknowledged: bool
    understood: bool | Literal["YES", "PARTLY", "NO"]
    confidence: int = Field(ge=1, le=5)
    explanationStatus: Literal["EXPLAINED", "NOT_EXPLAINED"]
    callbackRequested: bool
    note: Text1000 | None = None

    @property
    def understood_level(self) -> str:
        return ("YES" if self.understood else "NO") if isinstance(self.understood, bool) else self.understood

class ReassuranceBody(BaseModel):
    rating: int = Field(ge=1, le=5)
