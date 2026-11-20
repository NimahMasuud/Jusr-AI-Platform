from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.v1.deps import require_roles
from app.services import measures

router = APIRouter()

@router.get("")
def get_measures(facilityId: str | None = None, pathway: str | None = None, since: datetime | None = None, until: datetime | None = None,
                 db: Session = Depends(get_db), user=Depends(require_roles("COORDINATOR", "REFERRING_CLINICIAN", "RECEIVING_CLINICIAN", "FACILITY_ADMIN", "NATIONAL_ADMIN"))):
    """M1 to M6 calculated from the event log. Coordinators and facility administrators see their facility, clinicians their own cases, national administrators everything.
    Only aggregates are returned, never case content (R-09)."""
    return {"success": True, "data": measures.compute(db, user, facility_id=facilityId, pathway=pathway, since=since, until=until), "meta": {}}
