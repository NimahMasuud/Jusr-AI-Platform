"""Outbound messaging. Real delivery is not assumed to exist: the default provider is simulated.

R-28: nothing is sent unless approved. R-19: a failed send is retried, staff are alerted and the message is set to MESSAGE_FAILED.
"""
from datetime import datetime, timedelta, timezone
from app.core import clock
from app.models.entities import Case, CaseStatus, Message, MessageStatus
from app.services import settings_store, state_machine as sm
from app.services.audit import record_event
from app.services.tasks import create_task

class DeliveryError(Exception):
    pass

class SimulatedProvider:
    """Demo provider: reports success without contacting anyone."""
    def send(self, message: Message) -> None:
        return None

def get_message_provider():
    return SimulatedProvider()


def attempt_delivery(db, user, message: Message, provider) -> Message:
    """One delivery attempt for an APPROVED or due RETRYING message. Caller commits."""
    assert message.status in (MessageStatus.APPROVED.value, MessageStatus.RETRYING.value) and (message.approved_by_id or message.source == "SYSTEM")
    now = clock.now()
    message.attempts += 1
    case = db.get(Case, message.case_id)
    try:
        provider.send(message)
    except Exception as exc:  # any provider failure counts as a failed attempt
        message.last_error = str(exc)[:500] or exc.__class__.__name__
        if message.attempts < settings_store.get_int(db, "message.max_attempts", facility_id=message.facility_id):
            message.status = MessageStatus.RETRYING.value
            message.next_retry_at = now + settings_store.retry_delay(db, message.attempts, facility_id=message.facility_id)
            record_event(db, user, case_id=message.case_id, event_type="MESSAGE_SEND_FAILED", description="Message delivery failed; will retry",
                         new_values={"messageId": message.id, "attempt": message.attempts, "nextRetryAt": message.next_retry_at.isoformat(), "error": message.last_error})
        else:
            message.status = MessageStatus.MESSAGE_FAILED.value; message.next_retry_at = None
            case.flag_message_failed = True  # R-19: staff are alerted and MESSAGE_FAILED is set
            create_task(db, case, "MESSAGE_FAILED", "Message could not be delivered",
                        f"{message.attempts} attempts failed. Last error: {message.last_error}. Contact the patient another way.", source_ref=message.id)
            record_event(db, user, case_id=message.case_id, event_type="MESSAGE_FAILED", description="Message delivery failed after all retries; staff alerted",
                         new_values={"messageId": message.id, "attempts": message.attempts, "error": message.last_error})
    else:
        message.status = MessageStatus.SENT.value; message.sent_at = now; message.next_retry_at = None; message.last_error = None
        record_event(db, user, case_id=message.case_id, event_type="MESSAGE_SENT", description="Message sent", at=now,
                     new_values={"messageId": message.id, "attempt": message.attempts})
        if message.kind.startswith("RESULT_NOTICE") and case.status == CaseStatus.NOTIFYING:
            # T7: approved, sent, delivery confirmed. Approval was logged before sending (R-28).
            sm.apply(db, sm.SYSTEM, case, "T7", ctx={"message": message}, at=now, details={"messageId": message.id, "approvedById": message.approved_by_id})
    message.updated_at = now
    return message

def process_due_messages(db, actor, provider, message_query=None, now=None) -> dict:
    """Retry RETRYING messages whose retry time has arrived (R-19). Caller commits."""
    now = now or clock.now()
    q = message_query if message_query is not None else db.query(Message)
    due = q.filter(Message.status == MessageStatus.RETRYING.value, Message.next_retry_at <= now).with_for_update(skip_locked=True, of=Message).all()
    for m in due:
        attempt_delivery(db, actor, m, provider)
    return {"processed": len(due), "sent": sum(m.status == "SENT" for m in due), "retrying": sum(m.status == "RETRYING" for m in due),
            "failed": sum(m.status == "MESSAGE_FAILED" for m in due)}
