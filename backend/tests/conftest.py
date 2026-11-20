import os

os.environ.setdefault("SCHEDULER_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import demo_data
from app.core import clock
from app.core.database import Base, get_db
from app.core.security import hash_password, pwd_context
from app.main import app
from app.models.entities import (
    Case,
    CaseStatus,
    Facility,
    Patient,
    Priority,
    Referral,
    Role,
    Screening,
    User,
)

pwd_context.update(bcrypt__rounds=4)


@pytest.fixture(autouse=True)
def _clock():
    clock.reset()
    yield
    clock.reset()


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override

    with TestClient(app) as test_client:
        test_client.session_factory = Session
        yield test_client

    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def org(client):
    db = client.session_factory()
    ids = demo_data.build_org(db)

    db.get(Facility, ids["hc"]).name = "A"
    db.get(Facility, ids["rrh"]).name = "B"
    db.get(Facility, ids["dc"]).name = "C"

    # Seed patient identifiers used by event-ingestion and AI tests.
    patients = demo_data.add_patients(db, ids["hc"], 110, start=1)

    # Seed Patient 101 at Facility C for the district-clinic demo scenario.
    demo_data.add_patients(db, ids["dc"], 1, start=101)

    # The primary receiving clinician is at Facility A; backups are at Facility B.
    db.get(User, ids["recv"]).facility_id = ids["hc"]

    # Add a receiving clinician at Facility C for cross-facility permission tests.
    recv_c = User(
        email="receiving.c@jusr.local",
        display_name="Demo Facility C Receiving Clinician",
        password_hash=hash_password("Receiving123!"),
        role=Role.RECEIVING_CLINICIAN,
        facility_id=ids["dc"],
    )
    db.add(recv_c)
    db.flush()

    # Facility A and Facility B test patients.
    pa = Patient(
        display_label="PA",
        age_years=36,
        birth_year=None,
        sex="F",
        is_synthetic=True,
        data_origin="SYNTHETIC",
        facility_id=ids["hc"],
    )
    pb = Patient(
        display_label="PB",
        age_years=40,
        birth_year=1986,
        sex="F",
        is_synthetic=True,
        data_origin="SYNTHETIC",
        facility_id=ids["rrh"],
    )
    db.add_all([pa, pb])
    db.flush()

    sa = Screening(
        patient_id=pa.id,
        screening_type="Cervical screening",
        outcome="Abnormal",
        display_label="Abnormal cervical screening",
    )
    sb = Screening(
        patient_id=pb.id,
        screening_type="Cervical screening",
        outcome="Abnormal",
        display_label="Abnormal cervical screening",
    )
    db.add_all([sa, sb])
    db.flush()

    ca = Case(
        case_number="CA",
        patient_id=pa.id,
        screening_id=sa.id,
        facility_id=ids["hc"],
        coordinator_id=ids["coord"],
        priority=Priority.URGENT,
        status=CaseStatus.AWAITING_ACK,
        flag_overdue=True,
        required_specialty="COLPOSCOPY",
        due_at=clock.now(),
    )
    cb = Case(
        case_number="CB",
        patient_id=pb.id,
        screening_id=sb.id,
        facility_id=ids["rrh"],
        coordinator_id=ids["coordR"],
        priority=Priority.NORMAL,
        status=CaseStatus.REFERRAL_PENDING,
    )
    db.add_all([ca, cb])
    db.flush()

    referral = Referral(
        case_id=cb.id,
        status="SENT",
        target_specialty="COLPOSCOPY",
        receiving_facility_id=ids["hc"],
        referred_by_id=ids["refer"],
        reason="Specialist review required",
    )
    db.add(referral)

    patient_user = User(
        email="patient@jusr.local",
        display_name="Demo Patient",
        password_hash=hash_password("Patient123!"),
        role=Role.PATIENT,
        facility_id=ids["hc"],
    )
    db.add(patient_user)
    db.commit()

    ids.update(
        {
            "pa": pa.id,
            "pb": pb.id,
            "ca": ca.id,
            "cb": cb.id,
            "patient": patient_user.id,
            "fadmin": ids["admin"],
            "coordB": ids["coordR"],
            "fa": ids["hc"],
            "fb": ids["rrh"],
            "fc": ids["dc"],
            "patients": patients,
            "recvB": ids["recv2"],
            "recvB2": ids["recv3"],
            "recvC": recv_c.id,
        }
    )

    driver = demo_data.Driver(client, ids)
    driver.emails["fadmin"] = driver.emails["admin"]
    driver.emails["coordB"] = driver.emails["coordR"]
    driver.emails["patient"] = "patient@jusr.local"
    driver.emails["recvB"] = driver.emails["recv2"]
    driver.emails["recvB2"] = driver.emails["recv3"]
    driver.emails["recvC"] = "receiving.c@jusr.local"

    def auth(who):
        if who == "fadmin":
            return driver.auth("admin")

        if who == "patient":
            if "patient" not in driver.h:
                response = client.post(
                    "/api/v1/auth/login",
                    data={
                        "username": "patient@jusr.local",
                        "password": "Patient123!",
                    },
                )
                assert response.status_code == 200, response.text
                driver.h["patient"] = {
                    "Authorization": (
                        "Bearer " + response.json()["data"]["accessToken"]
                    )
                }
            return driver.h["patient"]

        return driver.auth(who)

    db.close()
    return {"ids": ids, "auth": auth}


@pytest.fixture()
def d(client):
    """A clean organisation for tests that create their own cases via the event API.

    Do not depend on `org`: that fixture intentionally contains CA and CB for
    patient-link, access-control and referral tests, which contaminates tests
    that assert their event-created case list starts empty.
    """
    db = client.session_factory()
    ids = demo_data.build_org(db)
    ids["patients"] = demo_data.add_patients(db, ids["hc"], 110, start=1)
    db.commit()
    db.close()
    return demo_data.Driver(client, ids)
