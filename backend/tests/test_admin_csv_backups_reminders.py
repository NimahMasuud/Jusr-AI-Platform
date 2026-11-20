import csv
import io
import json
from datetime import timedelta

from app.core import clock
from app.models.entities import Case, CaseStatus, Message, Setting
from app.services.messaging import SimulatedProvider
from app.services.reminders import process_ack_reminders
from app.services.routing import SYSTEM_ACTOR


def _csv(rows, fieldnames):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def test_events_csv_import_processes_valid_and_invalid_rows(d):
    patient_id = d.ids["patients"][0]
    payload = {
        "caseNumber": "CSV-001",
        "screeningType": "Cervical screening",
        "outcome": "Abnormal",
        "patient": {"patientId": patient_id},
        "test": {"code": "HPV16", "value": "Positive"},
    }
    text = _csv(
        [
            {"eventId": "EV-CSV-1", "type": "RESULT_RECEIVED", "facilityId": d.ids["hc"], "payload": json.dumps(payload)},
            {"eventId": "EV-CSV-2", "type": "RESULT_RECEIVED", "facilityId": "", "payload": "{}"},
        ],
        ["eventId", "type", "facilityId", "payload"],
    )
    r = d.c.post("/api/v1/events/csv", headers={**d.auth("coord"), "Content-Type": "text/csv"}, content=text)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["counts"]["ACCEPTED"] == 1
    assert data["counts"]["REJECTED"] == 1
    assert data["results"][0]["caseId"] == "CSV-001"


def test_staff_csv_import_creates_profiles(d):
    text = _csv(
        [
            {"email": "csv.staff@jusr.local", "displayName": "CSV Clinician", "password": "Password123!",
             "role": "RECEIVING_CLINICIAN", "facilityId": d.ids["hc"], "specialty": "colposcopy", "authorisedToClose": "false"},
            {"email": "csv.staff@jusr.local", "displayName": "Duplicate", "password": "Password123!",
             "role": "COORDINATOR"},
        ],
        ["email", "displayName", "password", "role", "facilityId", "specialty", "authorisedToClose"],
    )
    r = d.c.post("/api/v1/admin/staff/csv", headers={**d.auth("admin"), "Content-Type": "text/csv"}, content=text)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["counts"] == {"created": 1, "rejected": 1}
    assert data["created"][0]["specialty"] == "COLPOSCOPY"
    assert "already exists" in data["rejected"][0]["message"]


def test_named_specialty_backup_is_used_for_the_second_escalation(client, org):
    # A third colposcopist created for this test is named as the specialty backup.
    text = _csv(
        [{"email": "backup@jusr.local", "displayName": "Named Backup", "password": "Password123!",
          "role": "RECEIVING_CLINICIAN", "facilityId": org["ids"]["rrh"], "specialty": "COLPOSCOPY"}],
        ["email", "displayName", "password", "role", "facilityId", "specialty"],
    )
    created = client.post("/api/v1/admin/staff/csv", headers={**org["auth"]("national"), "Content-Type": "text/csv"}, content=text)
    assert created.status_code == 200, created.text
    created_data = created.json()["data"]
    assert created_data["created"], created_data["rejected"]
    backup_id = created_data["created"][0]["id"]

    put = client.put("/api/v1/settings/specialty-backups/COLPOSCOPY", headers=org["auth"]("national"), json={"clinicianId": backup_id})
    assert put.status_code == 200, put.text
    listed = client.get("/api/v1/settings/specialty-backups", headers=org["auth"]("national")).json()["data"]
    assert listed[0]["clinicianId"] == backup_id

    # Route CA and let both limits expire; the named backup must receive the case.
    db = client.session_factory()
    case = db.get(Case, org["ids"]["ca"])
    case.status = CaseStatus.URGENT_ROUTING
    db.commit(); db.close()
    routed = client.post(f"/api/cases/{org['ids']['ca']}/urgent-routing", headers=org["auth"]("coord"), json={"specialty": "COLPOSCOPY"})
    assert routed.status_code == 200, routed.text

    for _ in range(2):
        db = client.session_factory()
        case = db.get(Case, org["ids"]["ca"])
        case.routing_due_at = clock.now() - timedelta(seconds=1)
        db.commit(); db.close()
        processed = client.post("/api/urgent-cases/process-due", headers=org["auth"]("coord"))
        assert processed.status_code == 200, processed.text

    routing = client.get(f"/api/cases/{org['ids']['ca']}/urgent-routing", headers=org["auth"]("coord")).json()["data"]["routing"]
    assert routing["stage"] == 2
    assert routing["routedClinician"]["id"] == backup_id


def test_ack_reminders_follow_the_approved_schedule(client, org):
    db = client.session_factory()
    served = db.get(Case, org["ids"]["ca"])
    served.status = CaseStatus.AWAITING_ACK
    served.status_entered_at = clock.now() - timedelta(days=2)  # past 50% of the 3-day limit
    db.add(Setting(key="reminder.ack_schedule_approved", scope=f"facility:{served.facility_id}", value=True))
    db.commit()
    db.close()

    db = client.session_factory()
    result = process_ack_reminders(db, SYSTEM_ACTOR, SimulatedProvider())
    db.commit()
    reminders = db.query(Message).filter(Message.case_id == org["ids"]["ca"], Message.kind == "ACK_REMINDER").all()
    assert result["created"] == 1 and result["sent"] == 1
    assert len(reminders) == 1 and reminders[0].status == "SENT"

    # A second pass does not repeat the same threshold.
    again = process_ack_reminders(db, SYSTEM_ACTOR, SimulatedProvider())
    db.commit()
    assert again["created"] == 0
    db.close()
