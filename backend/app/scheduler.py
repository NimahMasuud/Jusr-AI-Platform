"""Background processing: message retries (R-19), urgent-routing deadlines, overdue flags, referral timeouts, consultation escalations and the feed monitor.

Runs inside the API process when SCHEDULER_ENABLED is true, or as its own process via `python -m app.worker`.
With several API workers, enable it on one instance only (or use the worker): row locks make an overlapping run skip
rows another run is handling, but a single scheduler is simpler to reason about.
"""
import asyncio
import logging
from app.core.config import settings
from app.core.database import SessionLocal
from app.services.messaging import get_message_provider, process_due_messages
from app.services.reminders import process_ack_reminders
from app.services.routing import SYSTEM_ACTOR, process_due_routing
from app.services import state_machine as sm
from app.services.workflow import process_referral_timeouts

def _consultations(db):
    from app.api.v1.endpoints.consultations import process_consultation_escalations
    return process_consultation_escalations(db)

def _feed_monitor(db):
    """R-26: a facility with an expected feed interval that has been silent for longer sets DATA_MISSING on its open cases."""
    from datetime import timedelta
    from app.core import clock
    from app.models.entities import Facility
    from app.services import settings_store
    from app.api.v1.endpoints.events import set_data_missing
    now, n = clock.now(), 0
    for f in db.query(Facility).all():
        hours = settings_store.get_int(db, "feed.expected_interval_hours", facility_id=f.id)
        if not hours or f.connection_status == "MISSING":
            continue
        last = f.last_event_at
        if last is not None and last.tzinfo is None:
            from datetime import timezone
            last = last.replace(tzinfo=timezone.utc)
        if last is not None and now - last > timedelta(hours=hours):
            n += set_data_missing(db, SYSTEM_ACTOR, f, now, "No events received within the expected interval")
    return n

logger = logging.getLogger("app.scheduler")

def run_once(session_factory=SessionLocal) -> dict:
    """One pass over everything that may be due. Never raises; failures are logged and rolled back."""
    result = {}
    for name, job in (("messages", lambda db: process_due_messages(db, SYSTEM_ACTOR, get_message_provider())),
                      ("ackReminders", lambda db: process_ack_reminders(db, SYSTEM_ACTOR, get_message_provider())),
                      ("urgentRouting", lambda db: process_due_routing(db, SYSTEM_ACTOR)),
                      ("overdue", lambda db: sm.process_overdue(db)),
                      ("referralTimeouts", lambda db: process_referral_timeouts(db)),
                      ("consultations", _consultations),
                      ("feedMonitor", _feed_monitor)):
        db = None
        try:
            db = session_factory()
            result[name] = job(db)
            db.commit()
        except Exception:
            logger.exception("Scheduled job %s failed", name)
            result[name] = {"error": True}
            try:
                if db is not None: db.rollback()
            except Exception:
                logger.exception("Rollback after failed job %s also failed", name)
        finally:
            try:
                if db is not None: db.close()
            except Exception:
                logger.exception("Closing the session for job %s failed", name)
    return result

async def run_forever(interval_seconds: int | None = None) -> None:
    interval = interval_seconds or settings.scheduler_interval_seconds
    while True:
        await asyncio.sleep(interval)
        await asyncio.to_thread(run_once)
