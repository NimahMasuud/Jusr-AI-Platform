"""A small stand-in for the Jusr AI backend's POST /api/v1/ai/suggestions.

The payload models below are copied from the backend package (app/schemas/ai.py, v4) so these tests fail if
our payloads stop matching what the backend accepts. If the backend changes, update the copy.
"""
import socket
import threading
import time
from typing import Annotated, Literal, Optional
import uvicorn
from fastapi import FastAPI, Form, Header, HTTPException, Request
from pydantic import BaseModel, Field, StringConstraints, ValidationError

RequiredText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Body2000 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Summary = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
Priority = Literal["URGENT", "HIGH", "NORMAL"]


class IntakePayload(BaseModel):
    patientId: str
    caseId: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    facilityId: Optional[str] = None
    priority: Priority = "NORMAL"
    nextActionCode: Optional[str] = Field(default=None, max_length=80)
    nextActionLabel: Optional[str] = Field(default=None, max_length=200)
    rationale: Optional[RequiredText] = None


class UrgencyPayload(BaseModel):
    priority: Priority
    actionability: Literal["ACTIONABLE", "NEEDS_REVIEW", "NOT_ACTIONABLE"]
    rationale: RequiredText


class MessageDraftPayload(BaseModel):
    channel: Literal["SMS", "EMAIL"]
    body: Body2000
    purpose: Optional[str] = Field(default=None, max_length=200)


class Citation(BaseModel):
    sourceType: Literal["CASE", "SCREENING", "AUDIT_EVENT", "REFERRAL", "CONSULTATION", "PATIENT_RESPONSE"]
    sourceId: str
    excerpt: Optional[str] = Field(default=None, max_length=500)


class CaseSummaryPayload(BaseModel):
    summary: Summary
    citations: list[Citation] = Field(min_length=1, max_length=50)


class Alternative(BaseModel):
    receivingFacilityId: str
    rationale: RequiredText


class ReferralTargetPayload(BaseModel):
    receivingFacilityId: str
    receivingClinicianId: Optional[str] = None
    rationale: RequiredText
    alternatives: list[Alternative] = Field(default_factory=list, max_length=5)


MODELS = {"INTAKE": IntakePayload, "URGENCY": UrgencyPayload, "MESSAGE_DRAFT": MessageDraftPayload,
          "CASE_SUMMARY": CaseSummaryPayload, "REFERRAL_TARGET": ReferralTargetPayload}
KNOWN_EVENT_IDS = {"E1", "E2", "E3"}
KNOWN_FACILITIES = {"fac-a", "fac-b", "fac-c", "fac-d"}
FACILITY_ROWS = [
    {"id": "fac-a", "code": "JUSR-DEMO", "name": "Health Centre"},
    {"id": "fac-b", "code": "DEMO-RRH", "name": "Regional Referral Hospital"},
    {"id": "fac-c", "code": "DEMO-DC", "name": "District Clinic"},
]
EMAIL, PASSWORD = "ai@jusr.local", "ai-secret"


def make_app(state: dict) -> FastAPI:
    app = FastAPI()

    @app.post("/api/v1/auth/login")
    def login(username: str = Form(...), password: str = Form(...)):
        if (username, password) != (EMAIL, PASSWORD):
            raise HTTPException(401, "Invalid credentials")
        state["logins"] += 1
        state["token"] = f"tok-{state['logins']}"
        return {"success": True, "data": {"accessToken": state["token"], "tokenType": "bearer"}, "meta": {}}

    @app.post("/api/v1/ai/suggestions")
    async def submit(request: Request, authorization: Optional[str] = Header(default=None)):
        if state.get("expire_next"):
            state["expire_next"] = False
            state["token"] = None
        if authorization != f"Bearer {state.get('token')}":
            raise HTTPException(401, "Not authenticated")
        if state.get("reject"):
            raise HTTPException(422, detail={"code": "INVALID_SUGGESTION_PAYLOAD", "message": "Payload does not match"})
        body = await request.json()
        kind = body["kind"]
        try:
            data = MODELS[kind].model_validate(body["payload"])
        except ValidationError as exc:
            raise HTTPException(422, detail={"code": "INVALID_SUGGESTION_PAYLOAD", "message": str(exc)})
        if kind == "INTAKE" and body.get("caseId"):
            raise HTTPException(422, detail={"code": "CASE_NOT_ALLOWED", "message": "INTAKE omits caseId"})
        if kind != "INTAKE" and not body.get("caseId"):
            raise HTTPException(422, detail={"code": "CASE_REQUIRED", "message": "caseId needed"})
        if kind == "CASE_SUMMARY":
            for c in data.citations:
                if c.sourceType == "AUDIT_EVENT" and c.sourceId not in KNOWN_EVENT_IDS:
                    raise HTTPException(422, detail={"code": "INVALID_CITATION", "message": f"Unknown event {c.sourceId}"})
        if kind == "REFERRAL_TARGET":
            for fid in [data.receivingFacilityId] + [a.receivingFacilityId for a in data.alternatives]:
                if fid not in KNOWN_FACILITIES:
                    raise HTTPException(404, "Receiving facility not found")
        state["received"].append(body)
        return {"success": True, "data": {"id": f"ai-{len(state['received'])}", "kind": kind, "status": "PENDING",
                                          "caseId": body.get("caseId"), "payload": data.model_dump(mode="json"),
                                          "model": body.get("model"), "requiresStaffApproval": True}, "meta": {}}

    @app.get("/api/v1/ai/suggestions/facilities")
    def facilities(authorization: Optional[str] = Header(default=None)):
        if authorization != f"Bearer {state.get('token')}":
            raise HTTPException(401, "Not authenticated")
        return {"success": True, "data": FACILITY_ROWS, "meta": {}}
    return app


class FakeBackend:
    def __init__(self):
        self.state = {"logins": 0, "token": None, "received": [], "reject": False, "expire_next": False}
        s = socket.socket(); s.bind(("127.0.0.1", 0)); self.port = s.getsockname()[1]; s.close()
        self.server = uvicorn.Server(uvicorn.Config(make_app(self.state), host="127.0.0.1", port=self.port, log_level="error"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self):
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                return
            time.sleep(0.05)
        raise RuntimeError("fake backend did not start")

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=5)
