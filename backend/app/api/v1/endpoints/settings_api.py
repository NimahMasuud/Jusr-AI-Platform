"""Settings store (R-23) and the routing table (R-27). Time limits, templates, routing rules and reason codes are data: changing one needs no deployment."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core import clock
from app.core.database import get_db
from app.api.v1.deps import require_roles
from app.models.entities import Facility, Role, RoutingRule, Setting, SpecialtyBackup, User
from app.services import settings_store
from app.services import state_machine as sm
from app.services.audit import record_event
from app.services.routing import normalize_specialty

router = APIRouter()
VIEW = require_roles("COORDINATOR", "REFERRING_CLINICIAN", "RECEIVING_CLINICIAN", "FACILITY_ADMIN", "NATIONAL_ADMIN")
EDIT = require_roles("FACILITY_ADMIN", "NATIONAL_ADMIN")

class SettingPut(BaseModel):
    value: object = None
    scope: str = Field(default="global", max_length=100)

def _check_scope(db, user, scope: str):
    if scope == "global" or scope.startswith("specialty:"):
        if user.role != Role.NATIONAL_ADMIN:
            raise HTTPException(403, "Only a national administrator changes global or specialty settings")
        if scope.startswith("specialty:") and len(scope) <= len("specialty:"):
            raise HTTPException(422, "Give a specialty name")
        return
    if scope.startswith("facility:"):
        fid = scope.split(":", 1)[1]
        fac = db.get(Facility, fid)
        if not fac: raise HTTPException(404, "Facility not found")
        if user.role == Role.FACILITY_ADMIN and not (fid == user.facility_id or fac.created_by_id == user.id):
            raise HTTPException(403, "A facility administrator changes settings for their own facilities only")
        return
    raise HTTPException(422, detail={"code": "INVALID_SCOPE", "message": "scope must be global, facility:<id> or specialty:<NAME>"})

def _row(r: Setting):
    return {"key": r.key, "scope": r.scope, "value": r.value, "changedById": r.changed_by_id, "changedAt": r.changed_at}

# ---------------------------------------------------------------- named specialty catalog
# Administrators maintain the list of specialties used by routing and the named
# backups dropdown. National administrators edit the global list; facility
# administrators maintain their own facility list, which is merged on read.

CATALOG_KEY = "specialty.catalog"

def _catalog_scope(user) -> str:
    if user.role == Role.NATIONAL_ADMIN or not user.facility_id:
        return "global"
    return f"facility:{user.facility_id}"

def _catalog_row(db, scope):
    return db.query(Setting).filter(Setting.key == CATALOG_KEY, Setting.scope == scope).first()

def _catalog_entries(db, scope) -> list[dict]:
    row = _catalog_row(db, scope)
    entries = row.value if row and isinstance(row.value, list) else []
    return [
        {"name": e["name"], "label": e.get("label") or e["name"]}
        for e in entries
        if isinstance(e, dict) and e.get("name")
    ]

def _effective_catalog(db, user) -> list[dict]:
    merged: dict[str, dict] = {}
    own = _catalog_scope(user)
    scopes = ["global"] if own == "global" else ["global", own]
    for scope in scopes:
        for entry in _catalog_entries(db, scope):
            merged[entry["name"]] = {**entry, "scope": scope}
    return [merged[name] for name in sorted(merged)]

def _save_catalog(db, user, entries: list[dict]):
    scope = _catalog_scope(user)
    row = _catalog_row(db, scope)
    old = row.value if row else None
    if row:
        row.value = entries
        row.changed_by_id = user.id
        row.changed_at = clock.now()
    else:
        db.add(Setting(key=CATALOG_KEY, scope=scope, value=entries, changed_by_id=user.id, changed_at=clock.now()))
    record_event(db, user, case_id=None, event_type="SPECIALTY_CATALOG_CHANGED", description=f"Specialty list updated ({scope})",
                 old_values={"specialties": old}, new_values={"specialties": entries})
    db.commit()

def _catalog_out(entry: dict, user) -> dict:
    return {**entry, "editable": entry["scope"] == _catalog_scope(user)}

class SpecialtyBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    label: str | None = Field(default=None, max_length=80)

@router.get("/specialties")
def list_specialties(db: Session = Depends(get_db), user=Depends(VIEW)):
    return {"success": True, "data": [_catalog_out(e, user) for e in _effective_catalog(db, user)], "meta": {}}

@router.post("/specialties")
def add_specialty(body: SpecialtyBody, db: Session = Depends(get_db), user=Depends(EDIT)):
    name = normalize_specialty(body.name)
    if not name:
        raise HTTPException(422, "Give a specialty name")
    entries = _catalog_entries(db, _catalog_scope(user))
    if any(e["name"] == name for e in entries) or any(e["name"] == name for e in _effective_catalog(db, user)):
        raise HTTPException(409, detail={"code": "SPECIALTY_EXISTS", "message": f"{name} is already on the list"})
    entries.append({"name": name, "label": (body.label or body.name).strip()})
    _save_catalog(db, user, entries)
    return {"success": True, "data": _catalog_out({"name": name, "label": (body.label or body.name).strip(), "scope": _catalog_scope(user)}, user), "meta": {}}

@router.put("/specialties/{name}")
def edit_specialty(name: str, body: SpecialtyBody, db: Session = Depends(get_db), user=Depends(EDIT)):
    current = normalize_specialty(name)
    entries = _catalog_entries(db, _catalog_scope(user))
    index = next((i for i, e in enumerate(entries) if e["name"] == current), None)
    if index is None:
        raise HTTPException(403, detail={"code": "GLOBAL_SPECIALTY", "message": "A national administrator manages this specialty"})
    new_name = normalize_specialty(body.name)
    if not new_name:
        raise HTTPException(422, "Give a specialty name")
    if new_name != current and any(e["name"] == new_name for e in entries):
        raise HTTPException(409, detail={"code": "SPECIALTY_EXISTS", "message": f"{new_name} is already on the list"})
    entries[index] = {"name": new_name, "label": (body.label or body.name).strip()}
    _save_catalog(db, user, entries)
    return {"success": True, "data": _catalog_out({**entries[index], "scope": _catalog_scope(user)}, user), "meta": {}}

@router.delete("/specialties/{name}")
def delete_specialty(name: str, db: Session = Depends(get_db), user=Depends(EDIT)):
    current = normalize_specialty(name)
    entries = _catalog_entries(db, _catalog_scope(user))
    remaining = [e for e in entries if e["name"] != current]
    if len(remaining) == len(entries):
        if any(e["name"] == current for e in _effective_catalog(db, user)):
            raise HTTPException(403, detail={"code": "GLOBAL_SPECIALTY", "message": "A national administrator manages this specialty"})
        raise HTTPException(404, "Specialty not found")
    _save_catalog(db, user, remaining)
    return {"success": True, "data": {"name": current, "removed": True}, "meta": {}}

@router.get("")
def list_settings(db: Session = Depends(get_db), user=Depends(VIEW)):
    rows = db.query(Setting).order_by(Setting.key, Setting.scope).all()
    return {"success": True, "data": {"defaults": settings_store.DEFAULTS, "overrides": [_row(r) for r in rows]}, "meta": {}}

@router.get("/effective")
def effective(key: str, facilityId: str | None = None, specialty: str | None = None, db: Session = Depends(get_db), user=Depends(VIEW)):
    if key not in settings_store.DEFAULTS: raise HTTPException(404, "Unknown setting")
    return {"success": True, "data": {"key": key, "value": settings_store.get(db, key, facility_id=facilityId, specialty=specialty)}, "meta": {}}

@router.put("/{key}")
def put_setting(key: str, payload: SettingPut, db: Session = Depends(get_db), user=Depends(EDIT)):
    _check_scope(db, user, payload.scope)
    err = settings_store.validate(key, payload.value)
    if err: raise HTTPException(422, detail={"code": "INVALID_SETTING", "message": err})
    row = db.query(Setting).filter(Setting.key == key, Setting.scope == payload.scope).first()
    old = row.value if row else None
    if row:
        row.value = payload.value; row.changed_by_id = user.id; row.changed_at = clock.now()
    else:
        row = Setting(key=key, scope=payload.scope, value=payload.value, changed_by_id=user.id, changed_at=clock.now()); db.add(row)
    record_event(db, user, case_id=None, event_type="SETTING_CHANGED", description=f"Setting {key} changed ({payload.scope})", old_values={"key": key, "scope": payload.scope, "value": old},
                 new_values={"key": key, "scope": payload.scope, "value": payload.value})
    db.flush()
    if key.startswith("limit."): sm.refresh_due_dates(db, key.split(".", 1)[1])
    db.commit()
    return {"success": True, "data": _row(row), "meta": {}}

@router.delete("/{key}")
def delete_setting(key: str, scope: str = Query("global"), db: Session = Depends(get_db), user=Depends(EDIT)):
    """Remove an override so the value is inherited again."""
    _check_scope(db, user, scope)
    row = db.query(Setting).filter(Setting.key == key, Setting.scope == scope).first()
    if not row: raise HTTPException(404, "No override with that key and scope")
    record_event(db, user, case_id=None, event_type="SETTING_CHANGED", description=f"Setting {key} override removed ({scope})", old_values={"key": key, "scope": scope, "value": row.value}, new_values={"key": key, "scope": scope, "value": None})
    db.delete(row); db.flush()
    if key.startswith("limit."): sm.refresh_due_dates(db, key.split(".", 1)[1])
    db.commit()
    return {"success": True, "data": {"key": key, "scope": scope, "removed": True}, "meta": {}}

# ---------------------------------------------------------------- named specialty backups (R-29)

class BackupBody(BaseModel):
    clinicianId: str


def _backup_out(db, row: SpecialtyBackup):
    clinician = db.get(User, row.clinician_id)
    return {"specialty": row.specialty, "clinicianId": row.clinician_id, "clinicianName": clinician.display_name if clinician else None,
            "facilityId": row.facility_id, "changedById": row.changed_by_id, "changedAt": row.changed_at}


@router.get("/specialty-backups")
def list_specialty_backups(db: Session = Depends(get_db), user=Depends(VIEW)):
    rows = db.query(SpecialtyBackup).order_by(SpecialtyBackup.specialty).all()
    return {"success": True, "data": [_backup_out(db, r) for r in rows], "meta": {}}


@router.put("/specialty-backups/{specialty}")
def put_specialty_backup(specialty: str, body: BackupBody, db: Session = Depends(get_db), user=Depends(EDIT)):
    """Name the backup clinician for a specialty. The second escalation prefers this person (R-29)."""
    name = normalize_specialty(specialty)
    if not name:
        raise HTTPException(422, "Give a specialty name")
    clinician = db.get(User, body.clinicianId)
    if not clinician or clinician.role != Role.RECEIVING_CLINICIAN or not clinician.is_active:
        raise HTTPException(422, detail={"code": "INVALID_BACKUP", "message": "The backup must be an active receiving clinician"})
    if clinician.specialty != name:
        raise HTTPException(422, detail={"code": "SPECIALTY_MISMATCH", "message": f"{clinician.specialty or 'No specialty'} does not match {name}"})
    if user.role == Role.FACILITY_ADMIN:
        fac = db.get(Facility, clinician.facility_id) if clinician.facility_id else None
        if not fac or not (fac.id == user.facility_id or fac.created_by_id == user.id):
            raise HTTPException(403, "A facility administrator can only name staff from their own facilities")
    row = db.query(SpecialtyBackup).filter(SpecialtyBackup.specialty == name).first()
    old = row.clinician_id if row else None
    if row:
        row.clinician_id = clinician.id; row.facility_id = clinician.facility_id; row.changed_by_id = user.id; row.changed_at = clock.now()
    else:
        row = SpecialtyBackup(specialty=name, clinician_id=clinician.id, facility_id=clinician.facility_id, changed_by_id=user.id, changed_at=clock.now())
        db.add(row)
    record_event(db, user, case_id=None, event_type="SPECIALTY_BACKUP_CHANGED", description=f"Specialty backup set for {name}",
                 old_values={"specialty": name, "clinicianId": old}, new_values={"specialty": name, "clinicianId": clinician.id})
    db.commit()
    return {"success": True, "data": _backup_out(db, row), "meta": {}}


@router.delete("/specialty-backups/{specialty}")
def delete_specialty_backup(specialty: str, db: Session = Depends(get_db), user=Depends(EDIT)):
    name = normalize_specialty(specialty)
    row = db.query(SpecialtyBackup).filter(SpecialtyBackup.specialty == name).first()
    if not row:
        raise HTTPException(404, "No backup is named for that specialty")
    record_event(db, user, case_id=None, event_type="SPECIALTY_BACKUP_CHANGED", description=f"Specialty backup removed for {name}",
                 old_values={"specialty": name, "clinicianId": row.clinician_id})
    db.delete(row); db.commit()
    return {"success": True, "data": {"specialty": name, "removed": True}, "meta": {}}


# ---------------------------------------------------------------- routing table (R-27)

class RuleBody(BaseModel):
    pathway: str = Field(min_length=1, max_length=100)
    resultCategory: str = Field(min_length=1, max_length=200)
    suggestedUrgency: str | None = Field(default=None, max_length=20)
    confirmatoryRequired: bool = False
    specialty: str | None = Field(default=None, max_length=60)
    primaryPool: str | None = Field(default=None, max_length=100)
    backupPool: str | None = Field(default=None, max_length=100)
    timeToAcceptMinutes: int | None = Field(default=None, gt=0)
    timeToAppointmentDays: int | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=1000)

def rule_out(r: RoutingRule):
    return {"id": r.id, "pathway": r.pathway, "resultCategory": r.result_category, "suggestedUrgency": r.suggested_urgency, "confirmatoryRequired": r.confirmatory_required,
            "specialty": r.specialty, "primaryPool": r.primary_pool, "backupPool": r.backup_pool, "timeToAcceptMinutes": r.time_to_accept_minutes,
            "timeToAppointmentDays": r.time_to_appointment_days, "notes": r.notes, "changedAt": r.changed_at}

def _apply(r: RoutingRule, b: RuleBody, user):
    r.pathway, r.result_category, r.suggested_urgency, r.confirmatory_required = b.pathway, b.resultCategory, b.suggestedUrgency, b.confirmatoryRequired
    r.specialty, r.primary_pool, r.backup_pool, r.notes = b.specialty, b.primaryPool, b.backupPool, b.notes
    r.time_to_accept_minutes, r.time_to_appointment_days = b.timeToAcceptMinutes, b.timeToAppointmentDays
    r.changed_by_id = user.id; r.changed_at = clock.now()

@router.get("/routing-rules")
def list_rules(db: Session = Depends(get_db), user=Depends(VIEW)):
    return {"success": True, "data": [rule_out(r) for r in db.query(RoutingRule).order_by(RoutingRule.pathway, RoutingRule.result_category).all()], "meta": {}}

@router.post("/routing-rules")
def add_rule(body: RuleBody, db: Session = Depends(get_db), user=Depends(EDIT)):
    r = RoutingRule(); _apply(r, body, user); db.add(r); db.flush()
    record_event(db, user, case_id=None, event_type="ROUTING_RULE_CHANGED", description=f"Routing rule added: {body.pathway}", new_values=body.model_dump())
    db.commit()
    return {"success": True, "data": rule_out(r), "meta": {}}

@router.put("/routing-rules/{rule_id}")
def edit_rule(rule_id: str, body: RuleBody, db: Session = Depends(get_db), user=Depends(EDIT)):
    r = db.get(RoutingRule, rule_id)
    if not r: raise HTTPException(404, "Routing rule not found")
    old = rule_out(r); _apply(r, body, user)
    record_event(db, user, case_id=None, event_type="ROUTING_RULE_CHANGED", description=f"Routing rule changed: {body.pathway}", old_values={k: str(v) for k, v in old.items()}, new_values=body.model_dump())
    db.commit()
    return {"success": True, "data": rule_out(r), "meta": {}}

@router.delete("/routing-rules/{rule_id}")
def delete_rule(rule_id: str, db: Session = Depends(get_db), user=Depends(EDIT)):
    r = db.get(RoutingRule, rule_id)
    if not r: raise HTTPException(404, "Routing rule not found")
    record_event(db, user, case_id=None, event_type="ROUTING_RULE_CHANGED", description=f"Routing rule removed: {r.pathway}", old_values={"id": r.id})
    db.delete(r); db.commit()
    return {"success": True, "data": {"id": rule_id, "removed": True}, "meta": {}}
