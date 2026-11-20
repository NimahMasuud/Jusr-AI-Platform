"""R-66: demo clock controls. Only available when DEMO_MODE is on, and only to a national admin."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.api.v1.deps import require_roles
from app.core import clock
from app.core.config import settings
from app.core.database import get_db
from app.scheduler import run_once

router = APIRouter()

class AdvanceBody(BaseModel):
    minutes: float = Field(gt=0, le=60 * 24 * 60)

def _state():
    return {"active": clock.is_active(), "offsetMinutes": clock.offset_minutes(), "now": clock.now().isoformat(), "banner": "Demo clock is ahead of real time" if clock.is_active() else None}

def _guard():
    if not settings.demo_mode:
        raise HTTPException(404, "Not found")

@router.get("/clock")
def get_clock(user=Depends(require_roles("NATIONAL_ADMIN"))):
    _guard(); return {"success": True, "data": _state()}

@router.post("/clock/advance")
def advance(body: AdvanceBody, user=Depends(require_roles("NATIONAL_ADMIN"))):
    """Moves demo time forward and runs the scheduled jobs once so overdue flags, timeouts and escalations appear at once."""
    _guard(); clock.advance(body.minutes)
    return {"success": True, "data": {**_state(), "jobs": run_once()}}

@router.post("/clock/reset")
def reset(user=Depends(require_roles("NATIONAL_ADMIN"))):
    _guard(); clock.reset(); return {"success": True, "data": _state()}
