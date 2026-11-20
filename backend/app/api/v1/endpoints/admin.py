"""Facility administration (section 5, A-11): facilities, staff profiles. The facility administrator sees staff and settings, never clinical content (R-09)."""
import csv
import io
import re
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password
from app.api.v1.deps import current_user, require_roles
from app.models.entities import Case, Facility, InboundEvent, Patient, Role, User
from app.services.audit import record_event
from app.services.routing import normalize_specialty

router = APIRouter()
ADMIN = require_roles("FACILITY_ADMIN", "NATIONAL_ADMIN")
STAFF_ROLES = (Role.COORDINATOR, Role.REFERRING_CLINICIAN, Role.RECEIVING_CLINICIAN, Role.FACILITY_ADMIN)

def managed_facility_ids(db, user) -> set[str] | None:
    """None means every facility (national admin). A facility administrator manages their own facility and any they added."""
    if user.role == Role.NATIONAL_ADMIN: return None
    ids = {f.id for f in db.query(Facility).filter(Facility.created_by_id == user.id).all()}
    if user.facility_id: ids.add(user.facility_id)
    return ids

def facility_out(f: Facility):
    return {"id": f.id, "name": f.name, "code": f.code, "type": f.facility_type, "connectorType": f.connector_type, "connectionStatus": f.connection_status,
            "timeZone": f.time_zone, "workingDays": f.working_days, "lastEventAt": f.last_event_at}

def staff_out(u: User):
    return {"id": u.id, "email": u.email, "displayName": u.display_name, "role": u.role.value, "facilityId": u.facility_id, "specialty": u.specialty,
            "authorisedToClose": u.authorised_to_close, "isActive": u.is_active}

# ---------------------------------------------------------------- facilities

@router.get("/facilities")
def list_facilities(db: Session = Depends(get_db), user=Depends(current_user)):
    """Every signed-in staff member can list facilities for the filters and the routing table."""
    if user.role in (Role.PATIENT, Role.AI_SERVICE): raise HTTPException(403, "Insufficient permissions")
    return {"success": True, "data": [facility_out(f) for f in db.query(Facility).order_by(Facility.name).all()], "meta": {}}

class FacilityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: str | None = Field(default=None, max_length=60)
    timeZone: str | None = Field(default=None, max_length=60)
    workingDays: list[Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]] | None = None
    connectorType: Literal["FEED_SIMULATOR", "CSV"] = "FEED_SIMULATOR"

@router.post("/facilities")
def add_facility(body: FacilityCreate, db: Session = Depends(get_db), user=Depends(ADMIN)):
    """A new facility appears in filters and routing with no code change or restart (A-11). Its status turns CONNECTED after a first event."""
    base = re.sub(r"[^A-Z0-9]+", "-", body.name.upper()).strip("-")[:30] or "FACILITY"
    code, n = base, 1
    while db.query(Facility.id).filter(Facility.code == code).first():
        n += 1; code = f"{base}-{n}"
    f = Facility(name=body.name, code=code, facility_type=body.type, time_zone=body.timeZone, working_days=body.workingDays, connector_type=body.connectorType,
                 connection_status="NOT_CONNECTED", created_by_id=user.id)
    db.add(f); db.flush()
    record_event(db, user, case_id=None, event_type="FACILITY_ADDED", description=f"Facility added: {f.name}", new_values=facility_out(f) | {"lastEventAt": None})
    db.commit()
    return {"success": True, "data": facility_out(f), "meta": {}}

class FacilityPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = Field(default=None, max_length=60)
    timeZone: str | None = Field(default=None, max_length=60)
    workingDays: list[Literal["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]] | None = None
    connectorType: Literal["FEED_SIMULATOR", "CSV"] | None = None

@router.patch("/facilities/{facility_id}")
def patch_facility(facility_id: str, body: FacilityPatch, db: Session = Depends(get_db), user=Depends(ADMIN)):
    f = db.get(Facility, facility_id)
    ids = managed_facility_ids(db, user)
    if not f or (ids is not None and f.id not in ids):
        raise HTTPException(404, "Facility not found")
    old = facility_out(f)
    if body.name is not None: f.name = body.name
    if "type" in body.model_fields_set: f.facility_type = body.type
    if body.timeZone is not None: f.time_zone = body.timeZone
    if "workingDays" in body.model_fields_set: f.working_days = body.workingDays
    if body.connectorType is not None: f.connector_type = body.connectorType
    auditable = lambda d: d | {"lastEventAt": d["lastEventAt"].isoformat() if d["lastEventAt"] else None}
    record_event(db, user, case_id=None, event_type="FACILITY_UPDATED", description=f"Facility updated: {f.name}", old_values=auditable(old), new_values=auditable(facility_out(f)))
    db.commit()
    return {"success": True, "data": facility_out(f), "meta": {}}

@router.delete("/facilities/{facility_id}")
def delete_facility(facility_id: str, db: Session = Depends(get_db), user=Depends(ADMIN)):
    """Remove a facility the administrator added. History keeps it from being deleted while in use."""
    f = db.get(Facility, facility_id)
    ids = managed_facility_ids(db, user)
    if not f or (ids is not None and f.id not in ids):
        raise HTTPException(404, "Facility not found")
    in_use = (
        db.query(Case.id).filter(Case.facility_id == f.id).first()
        or db.query(Patient.id).filter(Patient.facility_id == f.id).first()
        or db.query(User.id).filter(User.facility_id == f.id).first()
    )
    if in_use:
        raise HTTPException(409, detail={"code": "FACILITY_IN_USE",
                                         "message": "This facility still has patients, staff or cases. Move or remove them first."})
    db.query(InboundEvent).filter(InboundEvent.facility_id == f.id).delete()
    old = facility_out(f) | {"lastEventAt": f.last_event_at.isoformat() if f.last_event_at else None}
    record_event(db, user, case_id=None, event_type="FACILITY_DELETED", description=f"Facility removed: {f.name}", old_values=old)
    db.delete(f)
    db.commit()
    return {"success": True, "data": {"id": facility_id, "removed": True}, "meta": {}}

# ---------------------------------------------------------------- staff profiles

@router.get("/staff")
def list_staff(facilityId: str | None = None, role: Role | None = None, specialty: str | None = None, db: Session = Depends(get_db),
               user=Depends(require_roles("FACILITY_ADMIN", "NATIONAL_ADMIN", "COORDINATOR"))):
    q = db.query(User).filter(User.role.in_(STAFF_ROLES))
    ids = managed_facility_ids(db, user) if user.role != Role.COORDINATOR else {user.facility_id}
    if ids is not None: q = q.filter(User.facility_id.in_(ids))
    if facilityId: q = q.filter(User.facility_id == facilityId)
    if role: q = q.filter(User.role == role)
    if specialty: q = q.filter(User.specialty == normalize_specialty(specialty))
    return {"success": True, "data": [staff_out(u) for u in q.order_by(User.display_name).all()], "meta": {}}

@router.get("/closure-authorised-staff")
def list_closure_authorised_staff(
    db: Session = Depends(get_db),
    user=Depends(require_roles("COORDINATOR", "REFERRING_CLINICIAN")),
):
    """Return active, authorised closure approvers within the user's facility."""
    if not user.facility_id:
        return {"success": True, "data": [], "meta": {}}

    staff = (
        db.query(User)
        .filter(
            User.facility_id == user.facility_id,
            User.role.in_((Role.COORDINATOR, Role.REFERRING_CLINICIAN)),
            User.authorised_to_close.is_(True),
            User.is_active.is_(True),
        )
        .order_by(User.display_name)
        .all()
    )

    return {
        "success": True,
        "data": [
            {
                "id": str(member.id),
                "displayName": member.display_name,
                "role": member.role.value,
            }
            for member in staff
        ],
        "meta": {},
    }

class StaffCreate(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    displayName: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["COORDINATOR", "REFERRING_CLINICIAN", "RECEIVING_CLINICIAN", "FACILITY_ADMIN"]
    facilityId: str | None = None
    specialty: str | None = Field(default=None, max_length=60)
    authorisedToClose: bool = False

class StaffPatch(BaseModel):
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    displayName: str | None = Field(default=None, min_length=1, max_length=160)
    role: Literal["COORDINATOR", "REFERRING_CLINICIAN", "RECEIVING_CLINICIAN", "FACILITY_ADMIN"] | None = None
    facilityId: str | None = None
    specialty: str | None = Field(default=None, max_length=60)
    authorisedToClose: bool | None = None
    isActive: bool | None = None

def _managed_user(db, admin, user_id) -> User:
    u = db.get(User, user_id)
    ids = managed_facility_ids(db, admin)
    if not u or u.role not in STAFF_ROLES or (ids is not None and u.facility_id not in ids):
        raise HTTPException(404, "Staff member not found")
    return u

@router.post("/staff")
def create_staff(body: StaffCreate, db: Session = Depends(get_db), user=Depends(ADMIN)):
    fid = body.facilityId or user.facility_id
    ids = managed_facility_ids(db, user)
    if not fid or not db.get(Facility, fid) or (ids is not None and fid not in ids):
        raise HTTPException(404, "Facility not found")
    if db.query(User.id).filter(User.email == body.email).first():
        raise HTTPException(409, detail={"code": "EMAIL_IN_USE", "message": "A user with this email already exists"})
    u = User(email=body.email, display_name=body.displayName, password_hash=hash_password(body.password), role=Role(body.role), facility_id=fid,
             specialty=normalize_specialty(body.specialty), authorised_to_close=body.authorisedToClose)
    db.add(u); db.flush()
    record_event(db, user, case_id=None, event_type="STAFF_CREATED", description=f"Staff profile created: {u.display_name}", new_values=staff_out(u))
    db.commit()
    return {"success": True, "data": staff_out(u), "meta": {}}

@router.post("/staff/csv")
async def import_staff_csv(request: Request, db: Session = Depends(get_db), user=Depends(ADMIN)):
    """Create staff profiles from a CSV (A-11). Columns: email, displayName, password, role, facilityId (optional),
    specialty (optional), authorisedToClose (optional true/false). Each row is validated like the single-create form."""
    raw = (await request.body()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise HTTPException(422, detail={"code": "EMPTY_CSV", "message": "The CSV has no header row"})
    required = {"email", "displayName", "password", "role"}
    missing = required - {f.strip() for f in reader.fieldnames}
    if missing:
        raise HTTPException(422, detail={"code": "MISSING_COLUMNS", "message": f"The CSV is missing: {', '.join(sorted(missing))}"})

    ids = managed_facility_ids(db, user)
    created, rejected = [], []
    for index, row in enumerate(reader, start=2):
        if index > 501:
            break
        clean = {str(k).strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
        if not any(clean.values()):
            continue
        try:
            body = StaffCreate(
                email=clean.get("email") or "",
                displayName=clean.get("displayName") or "",
                password=clean.get("password") or "",
                role=(clean.get("role") or "").upper(),
                facilityId=clean.get("facilityId") or None,
                specialty=clean.get("specialty") or None,
                authorisedToClose=(clean.get("authorisedToClose") or "").lower() in ("1", "true", "yes", "y"),
            )
        except ValidationError as exc:
            rejected.append({"row": index, "email": clean.get("email"), "message": exc.errors()[0].get("msg", "Invalid row")})
            continue
        fid = body.facilityId or user.facility_id
        if not fid or not db.get(Facility, fid) or (ids is not None and fid not in ids):
            rejected.append({"row": index, "email": body.email, "message": "Facility not found"})
            continue
        if db.query(User.id).filter(User.email == body.email).first():
            rejected.append({"row": index, "email": body.email, "message": "A user with this email already exists"})
            continue
        try:
            with db.begin_nested():
                u = User(email=body.email, display_name=body.displayName, password_hash=hash_password(body.password), role=Role(body.role), facility_id=fid,
                         specialty=normalize_specialty(body.specialty), authorised_to_close=body.authorisedToClose)
                db.add(u); db.flush()
                record_event(db, user, case_id=None, event_type="STAFF_CREATED", description=f"Staff profile created from CSV: {u.display_name}", new_values=staff_out(u) | {"source": "CSV_IMPORT"})
            created.append(staff_out(u))
        except Exception:
            rejected.append({"row": index, "email": body.email, "message": "Could not create this profile"})
    db.commit()
    return {"success": True, "data": {"created": created, "rejected": rejected,
                                       "counts": {"created": len(created), "rejected": len(rejected)}}, "meta": {}}

@router.patch("/staff/{user_id}")
def patch_staff(user_id: str, body: StaffPatch, db: Session = Depends(get_db), user=Depends(ADMIN)):
    u = _managed_user(db, user, user_id)
    old = staff_out(u)
    if body.email is not None and body.email != u.email:
        if db.query(User.id).filter(User.email == body.email, User.id != u.id).first():
            raise HTTPException(409, detail={"code": "EMAIL_IN_USE", "message": "A user with this email already exists"})
        u.email = body.email
    if body.displayName is not None: u.display_name = body.displayName
    if body.role is not None: u.role = Role(body.role)
    if body.facilityId is not None and body.facilityId != u.facility_id:
        ids = managed_facility_ids(db, user)
        if not db.get(Facility, body.facilityId) or (ids is not None and body.facilityId not in ids):
            raise HTTPException(404, "Facility not found")
        u.facility_id = body.facilityId
    if "specialty" in body.model_fields_set: u.specialty = normalize_specialty(body.specialty)
    if body.authorisedToClose is not None: u.authorised_to_close = body.authorisedToClose
    if body.isActive is not None: u.is_active = body.isActive
    record_event(db, user, case_id=None, event_type="STAFF_UPDATED", description=f"Staff profile updated: {u.display_name}", old_values=old, new_values=staff_out(u))
    db.commit()
    return {"success": True, "data": staff_out(u), "meta": {}}

@router.delete("/staff/{user_id}")
def delete_staff(user_id: str, db: Session = Depends(get_db), user=Depends(ADMIN)):
    """Remove a staff profile from the directory.

    The account is deactivated rather than erased so past cases and the audit
    trail keep pointing at a real person.
    """
    u = _managed_user(db, user, user_id)
    if u.id == user.id:
        raise HTTPException(422, detail={"code": "SELF_REMOVAL", "message": "You cannot remove your own account"})
    u.is_active = False
    record_event(db, user, case_id=None, event_type="STAFF_REMOVED", description=f"Staff profile removed: {u.display_name}", old_values=staff_out(u))
    db.commit()
    return {"success": True, "data": {"id": u.id, "removed": True, "deactivated": True}, "meta": {}}
