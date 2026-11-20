from app.models.entities import Case, Task

def create_task(db, case: Case, type: str, title: str, detail: str | None = None, source_ref: str | None = None) -> Task | None:
    """Open a coordinator task for a case. A matching open task is not duplicated. Caller commits."""
    existing = db.query(Task).filter(Task.case_id == case.id, Task.type == type, Task.source_ref == source_ref, Task.status == "OPEN").first()
    if existing:
        return existing
    task = Task(case_id=case.id, facility_id=case.facility_id, type=type, title=title, detail=detail,
                assigned_to_id=case.coordinator_id, source_ref=source_ref)
    db.add(task)
    return task
