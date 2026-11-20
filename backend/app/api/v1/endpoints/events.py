"""Event ingestion (section 5, R-24 to R-26), the rejected-items list, and the event log export used to check the measures (A-22)."""
import csv, io, json
from datetime import datetime
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core import clock
from app.core.database import get_db
from app.api.v1.deps import clinical_user, require_roles
from app.api.v1.endpoints.admin import managed_facility_ids
from app.api.v1.endpoints.case_actions import record_attendance, record_treatment_start
from app.api.v1.endpoints.cases import find_case
from app.core.permissions import GLOBAL_ROLES, visible_cases
from app.models.entities import (Appointment, Attendance, AuditEvent, Case, CaseStatus, DelayReason, Facility, InboundEvent, Patient, Priority, Result, Role,
                                 RoutingRule, Screening, User)
from app.services import state_machine as sm
from app.services.ai_rules import generate_for_result_case
from app.services.audit import record_event
from app.services.tasks import create_task
from app.services.workflow import create_case_record
from sqlalchemy import func

router = APIRouter()

EVENT_TYPES = ("RESULT_RECEIVED", "CONFIRMATORY_RESULT_RECEIVED", "APPOINTMENT_UPDATE", "TREATMENT_START_RECORDED", "PATIENT_TRANSFERRED", "FEED_MISSING", "TEST_EVENT")

class InboundBody(BaseModel):
    eventId: str = Field(min_length=1, max_length=80)
    type: Literal["RESULT_RECEIVED", "CONFIRMATORY_RESULT_RECEIVED", "APPOINTMENT_UPDATE", "TREATMENT_START_RECORDED", "PATIENT_TRANSFERRED", "FEED_MISSING", "TEST_EVENT"]
    facilityId: str | None = None
    occurredAt: datetime | None = None
    payload: dict = Field(default_factory=dict)

class BatchBody(BaseModel):
    events: list[InboundBody] = Field(min_length=1, max_length=500)

class Invalid(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message

# ---------------------------------------------------------------- patient matching (R-37)

def match_patient(db, facility_id, ident: dict):
    """A fixed rule, not an AI score: an exact match on at least two identifiers (or a known patient id) is high confidence.
    Anything weaker goes to a coordinator with the candidates listed. Returns (patient, confidence, candidates)."""
    if ident.get("patientId"):
        p = db.get(Patient, ident["patientId"])
        if not p or (p.facility_id and p.facility_id != facility_id):
            raise Invalid("NO_PATIENT_MATCH", "The patient id is not known at this facility")
        return p, 1.0, [p]
    name, year, rec = (ident.get("name") or "").strip(), ident.get("birthYear"), (ident.get("recordNumber") or "").strip()
    if not (name and year) and not rec and not name:
        raise Invalid("MISSING_PATIENT_IDENTIFIERS", "The event has no patient identifiers (need a patient id, a record number, or a name with a birth year)")
    scored = []
    for p in db.query(Patient).filter(Patient.facility_id == facility_id).all():
        hits = (name and p.display_label.lower() == name.lower()) + (bool(year) and p.birth_year == year) + (bool(rec) and p.record_number == rec)
        if hits: scored.append((hits, p))
    if not scored:
        raise Invalid("NO_PATIENT_MATCH", "No patient at this facility matches the identifiers")
    scored.sort(key=lambda x: -x[0])
    strong = [p for h, p in scored if h >= 2]
    if len(strong) == 1:
        return strong[0], 1.0, strong
    return scored[0][1], 0.5, [p for _, p in scored[:5]]

# ---------------------------------------------------------------- handlers

def _need(payload, key, code="MISSING_FIELD"):
    v = payload.get(key)
    if v in (None, "", {}):
        raise Invalid(code, f"The event has no {key}")
    return v

def _case_in_facility(db, payload, facility_id) -> Case:
    key = _need(payload, "caseId", "MISSING_CASE")
    case = find_case(db, str(key))
    if not case or case.facility_id != facility_id:
        raise Invalid("CASE_NOT_FOUND", f"No case {key} at this facility")
    if case.status == CaseStatus.CLOSED:
        raise Invalid("CASE_CLOSED", "The case is closed and read-only")
    return case

def _test(payload):
    t = payload.get("test") or {"code": payload.get("testCode"), "name": payload.get("testName"), "value": payload.get("testValue")}
    if "abnormal" not in t and "abnormal" in payload:
        t["abnormal"] = payload["abnormal"]
    if not (t.get("code") and str(t.get("value", "")).strip()):
        raise Invalid("UNREADABLE_RESULT", "The result has no test code or value")
    return t

def _parse_dt(v):
    if not v: return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        raise Invalid("INVALID_DATE", f"'{v}' is not a valid date and time")

def _first_coordinator(db, facility_id):
    return db.query(User).filter(User.facility_id == facility_id, User.role == Role.COORDINATOR, User.is_active.is_(True)).order_by(User.email).first()

def h_result(db, actor, facility, body, now):
    p = body.payload
    ident = p.get("patient") or {k: p[k] for k in ("patientId", "name", "birthYear", "recordNumber") if k in p}
    test = _test(p)
    patient, conf, candidates = match_patient(db, facility.id, ident)
    stype = (p.get("screeningType") or "").strip() or "Unspecified screening"
    outcome = (p.get("outcome") or "Abnormal").strip()
    case_number = str(p.get("caseNumber") or f"C-{uuid4().hex[:8].upper()}")
    rule = db.query(RoutingRule).filter(RoutingRule.pathway.ilike(f"%{stype.split()[0]}%")).first() if p.get("screeningType") else None
    conf_required = bool(p["confirmatoryRequired"]) if "confirmatoryRequired" in p else bool(rule and rule.confirmatory_required)
    owner = _first_coordinator(db, facility.id)
    case = create_case_record(db, actor, patient=patient, case_number=case_number, facility_id=facility.id, priority=Priority.NORMAL,
                              confirmatory_required=conf_required, owner_id=owner.id if owner else None, match_confidence=conf, at=now,
                              extra_event={"eventId": body.eventId, "source": "FEED", "matchConfidence": conf})
    sc = Screening(patient_id=patient.id, screening_type=stype, outcome=outcome, display_label=f"{stype}: {outcome}")
    db.add(sc); db.flush(); case.screening_id = sc.id
    db.add(Result(case_id=case.id, facility_id=facility.id, kind="ORIGINAL", test_code=str(test["code"]), test_name=test.get("name"), value=str(test.get("value")),
                  abnormal=bool(test.get("abnormal", True)), issued_at=_parse_dt(p.get("issuedAt")), source="FEED", event_id=body.eventId, received_at=now))
    if conf < 1.0:
        create_task(db, case, "CONFIRM_PATIENT_MATCH", "Confirm the patient match", "Candidates: " + ", ".join(c.display_label for c in candidates), source_ref=body.eventId)
    db.flush()
    generate_for_result_case(db, case)
    return case

def h_confirmatory(db, actor, facility, body, now):
    p = body.payload
    case = _case_in_facility(db, p, facility.id)
    test = _test(p)
    r = Result(case_id=case.id, facility_id=facility.id, kind="CONFIRMATORY", test_code=str(test["code"]), test_name=test.get("name"), value=str(test.get("value")),
               abnormal=bool(test.get("abnormal", True)), issued_at=_parse_dt(p.get("issuedAt")), source="FEED", event_id=body.eventId, received_at=now)
    db.add(r); db.flush()
    record_event(db, actor, case_id=case.id, event_type="RESULT_STORED", description="Confirmatory result stored", at=now, new_values={"resultId": r.id, "kind": "CONFIRMATORY", "eventId": body.eventId})
    return case

def _case_any_facility(db, payload, facility_id):
    """Appointment and treatment events come from the receiving facility, so the case may belong to another facility."""
    key = _need(payload, "caseId", "MISSING_CASE")
    case = find_case(db, str(key))
    if not case:
        raise Invalid("CASE_NOT_FOUND", f"No case {key}")
    from app.models.entities import Referral, ReferralStatus
    ok = case.facility_id == facility_id or db.query(Referral.id).filter(Referral.case_id == case.id, Referral.receiving_facility_id == facility_id, Referral.status == ReferralStatus.ACCEPTED.value).first()
    if not ok:
        raise Invalid("CASE_NOT_FOUND", f"Case {key} is not handled at this facility")
    if case.status == CaseStatus.CLOSED:
        raise Invalid("CASE_CLOSED", "The case is closed and read-only")
    return case

def h_appointment(db, actor, facility, body, now):
    p = body.payload
    case = _case_any_facility(db, p, facility.id)
    att = str(_need(p, "attendance", "MISSING_FIELD")).upper()
    if att not in ("BOOKED", "ATTENDED", "MISSED"):
        raise Invalid("INVALID_ATTENDANCE", "attendance must be BOOKED, ATTENDED or MISSED")
    when = _parse_dt(_need(p, "scheduledAt"))
    if case.status != CaseStatus.AWAITING_APPOINTMENT:
        raise Invalid("INVALID_STATUS", f"Appointment events apply while the case is AWAITING_APPOINTMENT; it is {case.status.value}")
    appt = db.query(Appointment).filter(Appointment.case_id == case.id, Appointment.attendance == Attendance.BOOKED.value).order_by(Appointment.scheduled_at.desc()).first()
    if att == "BOOKED":
        if appt: raise Invalid("APPOINTMENT_ALREADY_BOOKED", "An appointment is already booked")
        a = Appointment(case_id=case.id, facility_id=facility.id, scheduled_at=when, created_at=now); db.add(a); db.flush()
        record_event(db, actor, case_id=case.id, event_type="APPOINTMENT_BOOKED", description="Appointment booked (feed)", at=now, new_values={"appointmentId": a.id, "eventId": body.eventId})
        return case
    if not appt:
        appt = Appointment(case_id=case.id, facility_id=facility.id, scheduled_at=when, created_at=now); db.add(appt); db.flush()
    code = p.get("reasonCode")
    if att == "MISSED":
        if code not in [r.value for r in DelayReason]:
            raise Invalid("REASON_CODE_REQUIRED", "A missed appointment needs a reason-for-delay code")
        code = DelayReason(code)
    record_attendance(db, actor, case, appt, att, code, p.get("note"), at=now)
    return case

def h_treatment(db, actor, facility, body, now):
    p = body.payload
    case = _case_any_facility(db, p, facility.id)
    kind = str(_need(p, "kind")).upper()
    if kind not in ("TREATMENT", "MONITORING"):
        raise Invalid("INVALID_KIND", "kind must be TREATMENT or MONITORING")
    start = _parse_dt(_need(p, "startDate"))
    if case.status != CaseStatus.AWAITING_TREATMENT:
        raise Invalid("INVALID_STATUS", f"A start record applies while the case is AWAITING_TREATMENT; it is {case.status.value}")
    if not (p.get("note") or p.get("attachmentRef")):
        raise Invalid("START_RECORD_INCOMPLETE", "The start record needs a note or a document")
    record_treatment_start(db, actor, case, kind=kind, start_date=start, note=p.get("note"), attachment_ref=p.get("attachmentRef"), at=now)
    return case

def h_transfer(db, actor, facility, body, now):
    """R-17: the patient moves to another facility. The owner is cleared and a coordinator task starts the reassignment."""
    p = body.payload
    case = _case_in_facility(db, p, facility.id)
    new_fac = db.get(Facility, str(_need(p, "newFacilityId")))
    if not new_fac: raise Invalid("FACILITY_NOT_FOUND", "The new facility is not known")
    case.coordinator_id = None; case.updated_at = now
    create_task(db, case, "REASSIGN_CASE", "Patient moved: reassign this case", f"New facility: {new_fac.name} ({new_fac.id})", source_ref=body.eventId)
    record_event(db, actor, case_id=case.id, event_type="PATIENT_TRANSFER_REPORTED", description="Patient reported as moved to another facility", at=now,
                 new_values={"newFacilityId": new_fac.id, "eventId": body.eventId})
    return case

def set_data_missing(db, actor, facility, now, reason="Facility feed missing") -> int:
    n = 0
    for c in db.query(Case).filter(Case.facility_id == facility.id, Case.status != CaseStatus.CLOSED, Case.flag_data_missing.is_(False)).all():
        c.flag_data_missing = True; n += 1
        record_event(db, actor, case_id=c.id, event_type="CASE_FLAG_SET", description=f"DATA_MISSING: {reason}", at=now, new_values={"flag": "DATA_MISSING"})
    facility.connection_status = "MISSING"
    return n

def clear_data_missing(db, actor, facility, now) -> int:
    n = 0
    for c in db.query(Case).filter(Case.facility_id == facility.id, Case.flag_data_missing.is_(True)).all():
        c.flag_data_missing = False; n += 1
        record_event(db, actor, case_id=c.id, event_type="CASE_FLAG_CLEARED", description="DATA_MISSING cleared: the feed event arrived", at=now, new_values={"flag": "DATA_MISSING"})
    return n

HANDLERS = {"RESULT_RECEIVED": h_result, "CONFIRMATORY_RESULT_RECEIVED": h_confirmatory, "APPOINTMENT_UPDATE": h_appointment,
            "TREATMENT_START_RECORDED": h_treatment, "PATIENT_TRANSFERRED": h_transfer}

# ---------------------------------------------------------------- ingestion

def _log_refusal(db, actor, body, facility_id, code, message, status):
    db.rollback()
    row = InboundEvent(event_id=body.eventId, type=body.type, facility_id=facility_id, status=status, error_code=code, error_message=message, payload=body.payload,
                       received_by_id=actor.id, received_at=clock.now())
    db.add(row)
    record_event(db, actor, case_id=None, event_type="INBOUND_EVENT_DUPLICATE" if status == "DUPLICATE" else "INBOUND_EVENT_REFUSED",
                 description=message, new_values={"eventId": body.eventId, "type": body.type, "facilityId": facility_id, "code": code})
    db.commit()
    return row

def ingest(db, actor, body: InboundBody, *, raise_on_error=True) -> dict:
    """Process one event. A repeated event id changes nothing and is logged (R-24, A-12). An invalid event is refused, logged and listed (R-25, A-13)."""
    if db.query(InboundEvent.id).filter(InboundEvent.event_id == body.eventId, InboundEvent.status == "ACCEPTED").first():
        _log_refusal(db, actor, body, body.facilityId, "DUPLICATE_EVENT", f"Event {body.eventId} was already received; nothing changed", "DUPLICATE")
        return {"status": "DUPLICATE", "eventId": body.eventId, "message": "Already received; no new record was created"}
    try:
        if not body.facilityId:
            raise Invalid("MISSING_FACILITY", "The event has no facility")
        facility = db.get(Facility, body.facilityId)
        if not facility:
            raise Invalid("UNKNOWN_FACILITY", f"Facility {body.facilityId} is not known")
        if actor.role == Role.COORDINATOR and actor.facility_id != facility.id:
            raise Invalid("FACILITY_NOT_ALLOWED", "A coordinator can only submit events for their own facility")
        now = body.occurredAt or clock.now()
        case = None
        with db.begin_nested():
            if body.type == "FEED_MISSING":
                affected = set_data_missing(db, sm.SYSTEM, facility, now)
                result = {"flagged": affected}
            else:
                if body.type != "TEST_EVENT":
                    case = HANDLERS[body.type](db, sm.SYSTEM, facility, body, now)  # state changes from a feed are made by the system
                cleared = clear_data_missing(db, sm.SYSTEM, facility, now)
                facility.connection_status = "CONNECTED"; facility.last_event_at = now
                result = {"dataMissingCleared": cleared}
        db.add(InboundEvent(event_id=body.eventId, type=body.type, facility_id=facility.id, status="ACCEPTED", payload=body.payload, case_id=case.id if case else None,
                            received_by_id=actor.id, received_at=clock.now()))
        db.commit()
        return {"status": "ACCEPTED", "eventId": body.eventId, "type": body.type, "caseId": case.case_number if case else None,
                "trackerId": case.tracker_id if case else None, "caseStatus": case.status.value if case else None, **result}
    except Invalid as e:
        row = _log_refusal(db, actor, body, body.facilityId, e.code, e.message, "REJECTED")
        if raise_on_error:
            raise HTTPException(422, detail={"code": e.code, "message": e.message, "rejectedItemId": row.id})
        return {"status": "REJECTED", "eventId": body.eventId, "code": e.code, "message": e.message, "rejectedItemId": row.id}
    except HTTPException as e:  # a state-machine refusal already rolled back and logged itself
        if raise_on_error:
            raise
        d = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
        return {"status": "REJECTED", "eventId": body.eventId, "code": d.get("code", "REFUSED"), "message": d.get("message")}

def _admin_manages(db, user, facility_id) -> bool:
    """A facility administrator manages their own facility and any facility they added (OpenMRS onboarding handshake)."""
    f = db.get(Facility, facility_id) if facility_id else None
    return bool(f and (f.id == user.facility_id or f.created_by_id == user.id))

def _may_ingest(db, user, body):
    if user.role == Role.FACILITY_ADMIN and body.type == "TEST_EVENT" and _admin_manages(db, user, body.facilityId):
        return True
    return user.role in (Role.COORDINATOR, Role.NATIONAL_ADMIN)

@router.post("")
def post_event(body: InboundBody, db: Session = Depends(get_db), user=Depends(require_roles("COORDINATOR", "NATIONAL_ADMIN", "FACILITY_ADMIN"))):
    if not _may_ingest(db, user, body): raise HTTPException(403, "Insufficient permissions")
    return {"success": True, "data": ingest(db, user, body), "meta": {}}

@router.post("/batch")
def post_events(body: BatchBody, db: Session = Depends(get_db), user=Depends(require_roles("COORDINATOR", "NATIONAL_ADMIN"))):
    """Each event is processed on its own; one refusal does not stop the rest."""
    out = [ingest(db, user, e, raise_on_error=False) for e in body.events]
    counts = {s: sum(1 for o in out if o["status"] == s) for s in ("ACCEPTED", "DUPLICATE", "REJECTED")}
    return {"success": True, "data": {"results": out, "counts": counts}, "meta": {}}

CSV_FIELDS = ("patientId", "name", "birthYear", "recordNumber", "caseId", "testCode", "testName", "testValue", "abnormal", "issuedAt", "screeningType", "outcome",
              "confirmatoryRequired", "scheduledAt", "attendance", "reasonCode", "note", "startDate", "kind", "attachmentRef", "newFacilityId")


@router.get("/csv/template")
def events_csv_template(db: Session = Depends(get_db), user=Depends(require_roles("COORDINATOR", "NATIONAL_ADMIN"))):
    """A ready-to-upload example row that uses real facility/patient ids from this workspace."""
    patient = db.query(Patient).filter(Patient.facility_id.isnot(None)).order_by(Patient.display_label).first()
    if not patient:
        raise HTTPException(422, detail={"code": "NO_PATIENT", "message": "Register a patient before downloading a template"})
    facility = db.get(Facility, patient.facility_id)
    if not facility:
        raise HTTPException(422, detail={"code": "NO_FACILITY", "message": "Add a facility before downloading a template"})
    from datetime import timezone
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["eventId", "type", "facilityId", "patientId", "testCode", "testName", "testValue", "abnormal",
                     "screeningType", "outcome", "confirmatoryRequired", "issuedAt"])
    writer.writerow([f"EMR-{uuid4().hex[:10].upper()}", "RESULT_RECEIVED", facility.id, patient.id, "VIA", "Visual inspection with acetic acid",
                     "Positive", "true", "Cervical screening", "Abnormal", "true", datetime.now(timezone.utc).isoformat()])
    return {"success": True, "data": {"csv": buf.getvalue(), "facility": facility.name, "patient": patient.display_label}, "meta": {}}


@router.post("/csv")
async def post_events_csv(request: Request, db: Session = Depends(get_db), user=Depends(require_roles("COORDINATOR", "NATIONAL_ADMIN", "FACILITY_ADMIN"))):
    """R-24/R-25: import a CSV file of inbound events. Every row goes through the same validation as the API,
    so an unreadable row is refused and listed without stopping the rest. Columns: eventId, type, facilityId,
    occurredAt (optional) and payload (optional JSON). Common event fields may also be their own columns."""
    raw = (await request.body()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise HTTPException(422, detail={"code": "EMPTY_CSV", "message": "The CSV has no header row"})
    missing = {"eventId", "type", "facilityId"} - {f.strip() for f in reader.fieldnames}
    if missing:
        raise HTTPException(422, detail={"code": "MISSING_COLUMNS", "message": f"The CSV is missing: {', '.join(sorted(missing))}"})

    results = []
    for index, row in enumerate(reader, start=2):
        if index > 501:
            results.append({"row": index, "status": "REJECTED", "code": "TOO_MANY_ROWS", "message": "Only 500 rows are processed per file"})
            break
        clean = {str(k).strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
        if not any(clean.values()):
            continue
        payload = {}
        if clean.get("payload"):
            try:
                payload = json.loads(clean["payload"])
            except (TypeError, ValueError):
                results.append({"row": index, "status": "REJECTED", "code": "INVALID_PAYLOAD", "message": "payload is not valid JSON"})
                continue
            if not isinstance(payload, dict):
                results.append({"row": index, "status": "REJECTED", "code": "INVALID_PAYLOAD", "message": "payload must be a JSON object"})
                continue
        for field in CSV_FIELDS:
            if clean.get(field) not in (None, ""):
                payload.setdefault(field, clean[field])
        if "abnormal" in payload and isinstance(payload["abnormal"], str):
            payload["abnormal"] = payload["abnormal"].strip().lower() in ("1", "true", "yes", "y")
        if "confirmatoryRequired" in payload and isinstance(payload["confirmatoryRequired"], str):
            payload["confirmatoryRequired"] = payload["confirmatoryRequired"].strip().lower() in ("1", "true", "yes", "y")
        try:
            body = InboundBody(eventId=clean.get("eventId") or f"CSV-{uuid4().hex[:10].upper()}", type=clean["type"], facilityId=clean["facilityId"] or None,
                               occurredAt=clean.get("occurredAt") or None, payload=payload)
        except Exception as exc:  # pydantic validation: an unknown type or malformed date
            results.append({"row": index, "status": "REJECTED", "code": "INVALID_ROW", "message": str(exc).splitlines()[0][:300]})
            continue
        if user.role == Role.FACILITY_ADMIN:
            if not _admin_manages(db, user, body.facilityId):
                results.append({"row": index, "status": "REJECTED", "code": "FACILITY_NOT_ALLOWED", "message": "You can upload events only for facilities you manage"})
                continue
            facility = db.get(Facility, body.facilityId)
            if not facility or facility.connector_type != "CSV":
                results.append({"row": index, "status": "REJECTED", "code": "CONNECTOR_NOT_CSV", "message": "This facility is not set up for CSV upload"})
                continue
        outcome = ingest(db, user, body, raise_on_error=False)
        results.append({"row": index, **outcome})

    counts = {s: sum(1 for o in results if o["status"] == s) for s in ("ACCEPTED", "DUPLICATE", "REJECTED")}
    return {"success": True, "data": {"results": results, "counts": counts}, "meta": {}}

# ---------------------------------------------------------------- rejected items, export

@router.get("/rejected")
def rejected_items(facilityId: str | None = None, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100), db: Session = Depends(get_db),
                   user=Depends(require_roles("COORDINATOR", "NATIONAL_ADMIN", "FACILITY_ADMIN"))):
    """Coordinators see the rejected items. The facility administrator sees counts only, no clinical content (R-09)."""
    q = db.query(InboundEvent).filter(InboundEvent.status == "REJECTED")
    if user.role == Role.FACILITY_ADMIN:
        # Every facility the administrator manages, not just their own, so the
        # feed reflects errors from every connector they added.
        managed = managed_facility_ids(db, user) or set()
        q = q.filter(InboundEvent.facility_id.in_(managed))
        rows = q.with_entities(InboundEvent.error_code, func.count(InboundEvent.id)).group_by(InboundEvent.error_code).all()
        return {"success": True, "data": {"total": sum(n for _, n in rows), "byErrorCode": {c: n for c, n in rows}}, "meta": {}}
    fid = facilityId if user.role == Role.NATIONAL_ADMIN else user.facility_id
    if fid: q = q.filter(InboundEvent.facility_id == fid)
    total = q.count()
    rows = q.order_by(InboundEvent.received_at.desc(), InboundEvent.id).offset((page - 1) * pageSize).limit(pageSize).all()
    return {"success": True, "data": [{"id": r.id, "eventId": r.event_id, "type": r.type, "facilityId": r.facility_id, "errorCode": r.error_code, "message": r.error_message,
                                       "payload": r.payload, "receivedAt": r.received_at} for r in rows], "meta": {"total": total, "page": page, "pageSize": pageSize}}

def log_rows(db, user, *, type=None, since=None, until=None):
    q = visible_cases(db.query(AuditEvent, Case).join(Case, AuditEvent.case_id == Case.id), user)
    if type: q = q.filter(AuditEvent.event_type == type)
    if since: q = q.filter(AuditEvent.occurred_at >= since)
    if until: q = q.filter(AuditEvent.occurred_at <= until)
    out = []
    for e, c in q.order_by(AuditEvent.occurred_at, AuditEvent.id).all():
        nv, ov = e.new_values or {}, e.old_values or {}
        out.append({"eventId": e.id, "trackerId": c.tracker_id, "caseId": c.case_number, "time": e.occurred_at.isoformat(), "actorId": e.actor_id, "actorRole": e.actor_role,
                    "type": e.event_type, "transition": nv.get("transition"), "fromStatus": ov.get("status"), "toStatus": nv.get("status"),
                    "reasonCode": nv.get("code") or nv.get("declineCode") or nv.get("closureType"), "details": nv})
    return out

@router.get("/export")
def export_log(format: Literal["json", "csv"] = "json", type: str | None = None, since: datetime | None = None, until: datetime | None = None,
               db: Session = Depends(get_db), user=Depends(clinical_user)):
    """The event log (R-21) as JSON or CSV, so measures can be recalculated by hand (A-22)."""
    rows = log_rows(db, user, type=type, since=since, until=until)
    if format == "csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["eventId", "trackerId", "caseId", "time", "actorId", "actorRole", "type", "transition", "fromStatus", "toStatus", "reasonCode", "details"])
        w.writeheader()
        for r in rows: w.writerow({**r, "details": json.dumps(r["details"], default=str)})
        return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=event-log.csv"})
    return {"success": True, "data": rows, "meta": {"total": len(rows)}}
