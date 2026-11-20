"""R-32: acknowledgement reminders at 50% and 100% of the AWAITING_ACK limit.

Reminders use the pre-approved template and the facility's approved schedule, so they go out without a
per-message staff approval; nothing else about the case changes. Only one reminder per threshold is sent.
"""
from app.core import clock
from app.models.entities import Case, CaseStatus, Facility, Message, MessageStatus, Patient
from app.services import settings_store
from app.services.audit import record_event
from app.services.messaging import attempt_delivery

TEMPLATE = {
    "en": ("Reminder: please confirm that you received the screening result message for tracker {tracker}. "
           "If you have not seen it, contact {facility}. This message contains no result details."),
    "ar": ("تذكير: يُرجى تأكيد استلام رسالة نتيجة الفحص الخاصة بالملف {tracker}. "
           "إذا لم تصلك، يُرجى التواصل مع {facility}. لا تحتوي هذه الرسالة على تفاصيل النتيجة."),
}


def _already_sent(db, case_id: str) -> int:
    return db.query(Message).filter(Message.case_id == case_id, Message.kind == "ACK_REMINDER", Message.status != MessageStatus.REJECTED.value).count()


def process_ack_reminders(db, actor, provider, now=None) -> dict:
    """Create and send the 50% / 100% reminders for cases waiting for acknowledgement. Caller commits."""
    now = now or clock.now()
    created = sent = 0
    cases = db.query(Case).filter(Case.status == CaseStatus.AWAITING_ACK).all()
    for case in cases:
        if not settings_store.get(db, "reminder.ack_schedule_approved", facility_id=case.facility_id):
            continue
        start = case.status_entered_at
        if not start:
            continue
        due = settings_store.due_for(db, CaseStatus.AWAITING_ACK, start, facility_id=case.facility_id)
        total = (due - start).total_seconds() if due else 0
        if total <= 0:
            continue
        elapsed = (now - start).total_seconds()
        stage = 2 if elapsed >= total else (1 if elapsed >= total * 0.5 else 0)
        if stage == 0 or _already_sent(db, case.id) >= stage:
            continue
        patient = db.get(Patient, case.patient_id)
        facility = db.get(Facility, case.facility_id)
        language = (patient.preferred_language if patient else None) or "en"
        template = TEMPLATE.get(language, TEMPLATE["en"])
        body = template.format(tracker=case.tracker_id or case.case_number, facility=facility.name if facility else "your facility")
        message = Message(case_id=case.id, facility_id=case.facility_id, channel="SMS", kind="ACK_REMINDER", language=language,
                          template_version="reminder-v1", body=body, status=MessageStatus.APPROVED.value, source="SYSTEM")
        db.add(message)
        db.flush()
        created += 1
        record_event(db, actor, case_id=case.id, event_type="ACK_REMINDER_CREATED", description=f"Acknowledgement reminder {stage} of 2 created from the approved schedule",
                     at=now, new_values={"messageId": message.id, "stage": stage, "templateVersion": "reminder-v1", "language": language})
        attempt_delivery(db, actor, message, provider)
        if message.status == MessageStatus.SENT.value:
            sent += 1
    return {"cases": len(cases), "created": created, "sent": sent}
