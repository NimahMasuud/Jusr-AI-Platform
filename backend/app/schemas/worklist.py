from datetime import datetime
from pydantic import BaseModel
from typing import Any

class WorklistPatient(BaseModel):
    id: str
    displayLabel: str
    ageYears: int | None = None
    sex: str | None = None

class WorklistCase(BaseModel):
    id: str
    caseId: str
    patient: WorklistPatient
    screening: dict[str, Any] | None = None
    priority: str
    status: str
    assignedCoordinator: dict[str, Any] | None = None
    facility: dict[str, Any]
    nextAction: dict[str, Any] | None = None
    dueAt: datetime | None = None
    updatedAt: datetime
    delayReason: dict[str, Any] | None = None
    delayReasonRequired: bool = False
    specialty: str | None = None
    routingStatus: str | None = None
    routing: dict[str, Any] | None = None
    patientLabel: str | None = None
    age: int | None = None
    sex: str | None = None
    screeningType: str | None = None
    assignedTo: str | None = None

class WorklistSummary(BaseModel):
    totalCases: int
    urgentCases: int
    overdueCases: int
    unassignedCases: int

class WorklistResponse(BaseModel):
    summary: WorklistSummary
    cases: list[WorklistCase]
    total: int
    page: int
    pageSize: int
    totalPages: int
