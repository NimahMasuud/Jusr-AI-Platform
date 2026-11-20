from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.permissions import CREATE_ROLES, GLOBAL_ROLES
from app.api.v1.deps import clinical_user
from app.models.entities import Case, Task
from app.services.audit import record_event, reject_and_log

router = APIRouter()

def _visible(q, user):
    if user.role in GLOBAL_ROLES: return q
    return q.filter(or_(Task.facility_id == user.facility_id, Task.assigned_to_id == user.id))

def _out(t: Task):
    return {"id": t.id, "caseId": t.case_id, "type": t.type, "title": t.title, "detail": t.detail, "status": t.status,
            "assignedToId": t.assigned_to_id, "createdAt": t.created_at, "completedAt": t.completed_at}

@router.get("")
def list_tasks(page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100), status: str | None = Query(None, pattern="^(OPEN|DONE)$"),
               type: str | None = None, db: Session = Depends(get_db), user=Depends(clinical_user)):
    q = _visible(db.query(Task), user)
    if status: q = q.filter(Task.status == status)
    if type: q = q.filter(Task.type == type)
    total = q.count()
    rows = q.order_by(Task.created_at.desc(), Task.id).offset((page - 1) * pageSize).limit(pageSize).all()
    return {"success": True, "data": [_out(t) for t in rows], "meta": {"total": total, "page": page, "pageSize": pageSize}}

@router.post("/{task_id}/complete")
def complete_task(task_id: str, db: Session = Depends(get_db), user=Depends(clinical_user)):
    if user.role not in CREATE_ROLES:
        raise HTTPException(403, "Insufficient permissions")

    t = _visible(db.query(Task), user).filter(Task.id == task_id).first()
    if not t:
        raise HTTPException(404, "Task not found")

    if t.status != "OPEN":
        reject_and_log(
            db,
            user,
            case_id=t.case_id,
            attempted="task:complete",
            status_code=409,
            code="TASK_ALREADY_DONE",
            message="Task is already completed",
        )

    t.status = "DONE"
    t.completed_at = datetime.now(timezone.utc)
    t.completed_by_id = user.id

    record_event(
        db,
        user,
        case_id=t.case_id,
        event_type="TASK_COMPLETED",
        description=f"Task completed: {t.type}",
        new_values={"taskId": t.id},
    )

    db.commit()
    return {"success": True, "data": _out(t), "meta": {}}
