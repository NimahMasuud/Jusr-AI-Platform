"""Seeds the demonstration database: three facilities, a user for each role and about 60 simulated cases.

The case log is built by driving the real API with the demo clock set in the past (see app/demo_data.py), so every status
change, flag and measure comes from the same state machine the live system uses. All people and results are synthetic."""
import logging
import os
from fastapi.testclient import TestClient
from app import demo_data
from app.core import clock
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models.entities import Role, User

log = logging.getLogger("app.seed")

def ensure_ai_service_user(db) -> bool:
    """Idempotent: existing databases seeded before the AI helper existed still get the service account."""
    if db.query(User).filter(User.role == Role.AI_SERVICE).first():
        return False
    db.add(User(email="ai@jusr.local", display_name="Demo AI Service",
                password_hash=hash_password(os.environ.get("AI_SERVICE_PASSWORD", "National123!")),
                role=Role.AI_SERVICE, facility_id=None))
    db.commit()
    log.info("Added the AI_SERVICE demo account (ai@jusr.local)")
    return True

def seed(with_cases: bool = True) -> int:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(User).first():
            ensure_ai_service_user(db)
            return 0
        ids = demo_data.build_org(db)
        demo_data.add_patients(db, ids["hc"], 75)
        demo_data.add_patients(db, ids["dc"], 3, start=101)
        db.commit()
    finally:
        db.close()
    if not with_cases:
        return 0
    from app.main import app
    from app.scheduler import run_once
    clock.reset()
    try:
        with TestClient(app) as client:
            s = demo_data.Seeder(demo_data.Driver(client, ids))
            s.run()
        clock.reset()
        run_once()  # sets the OVERDUE flags and any referral time-outs that have passed
        log.info("Seeded %s simulated cases", len(s.log))
        return len(s.log)
    finally:
        clock.reset()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Seeded {seed()} simulated cases")
