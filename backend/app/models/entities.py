import enum
from app.core import clock
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Integer, Float, Text, Enum, JSON, false, event
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.core import audit_guard

def uid():
    return str(uuid.uuid4())

def _now():
    return clock.now()  # the demo clock (R-66), so backdated demo data and stored timestamps agree

class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetime on every backend.

    PostgreSQL returns aware values for timestamptz, but SQLite drops the offset
    and returns naive values. This normalises both directions so comparisons with
    datetime.now(timezone.utc) never mix naive and aware datetimes.
    """
    impl = DateTime
    cache_ok = True

    def __init__(self):
        super().__init__(timezone=True)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

class Role(str, enum.Enum):
    PATIENT = "PATIENT"
    COORDINATOR = "COORDINATOR"
    REFERRING_CLINICIAN = "REFERRING_CLINICIAN"
    RECEIVING_CLINICIAN = "RECEIVING_CLINICIAN"
    FACILITY_ADMIN = "FACILITY_ADMIN"
    NATIONAL_ADMIN = "NATIONAL_ADMIN"
    AI_SERVICE = "AI_SERVICE"

class CaseStatus(str, enum.Enum):
    """Developer Guide Part 1, section 3. One status per case; flags say what needs attention."""
    NEW = "NEW"
    AWAITING_CLASSIFICATION = "AWAITING_CLASSIFICATION"
    URGENT_ROUTING = "URGENT_ROUTING"
    NOTIFYING = "NOTIFYING"
    AWAITING_ACK = "AWAITING_ACK"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    REFERRAL_PENDING = "REFERRAL_PENDING"
    AWAITING_APPOINTMENT = "AWAITING_APPOINTMENT"
    AWAITING_TREATMENT = "AWAITING_TREATMENT"
    READY_TO_CLOSE = "READY_TO_CLOSE"
    CLOSED = "CLOSED"

class ReferralStatus(str, enum.Enum):
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    NOT_ACCEPTED_IN_TIME = "NOT_ACCEPTED_IN_TIME"

class DeclineCode(str, enum.Enum):
    """R-44: declining a referral needs a reason from this list."""
    WRONG_SPECIALTY = "WRONG_SPECIALTY"
    NO_CAPACITY = "NO_CAPACITY"
    INFORMATION_MISSING = "INFORMATION_MISSING"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    OTHER = "OTHER"

class DelayReason(str, enum.Enum):
    """R-18 reason-for-delay codes (Developer Guide Part 1)."""
    PATIENT_UNREACHABLE = "PATIENT_UNREACHABLE"
    PATIENT_DID_NOT_UNDERSTAND = "PATIENT_DID_NOT_UNDERSTAND"
    REFERRAL_DECLINED = "REFERRAL_DECLINED"
    NO_SLOT_AVAILABLE = "NO_SLOT_AVAILABLE"
    RESULT_OR_DATA_MISSING = "RESULT_OR_DATA_MISSING"
    PATIENT_MOVED = "PATIENT_MOVED"
    OTHER = "OTHER"

class ClosureType(str, enum.Enum):
    CARE_CONFIRMED = "CARE_CONFIRMED"
    NOT_ACTIONABLE = "NOT_ACTIONABLE"
    NO_FURTHER_CARE = "NO_FURTHER_CARE"
    PATIENT_DECLINED = "PATIENT_DECLINED"
    UNREACHABLE = "UNREACHABLE"
    MOVED_OR_TRANSFERRED = "MOVED_OR_TRANSFERRED"
    OTHER = "OTHER"

class ConsultationType(str, enum.Enum):
    PATIENT_CALLBACK = "PATIENT_CALLBACK"
    CLINICIAN_TO_CLINICIAN = "CLINICIAN_TO_CLINICIAN"

class ConsultationState(str, enum.Enum):
    REQUESTED = "REQUESTED"
    ACCEPTED = "ACCEPTED"
    OUTCOME_RECORDED = "OUTCOME_RECORDED"
    ESCALATED = "ESCALATED"

class ConsultationOutcomeType(str, enum.Enum):
    ADVICE_GIVEN = "ADVICE_GIVEN"
    TEST_ORDERED = "TEST_ORDERED"
    REFERRAL_MADE = "REFERRAL_MADE"
    NO_ACTION = "NO_ACTION"

class Attendance(str, enum.Enum):
    BOOKED = "BOOKED"
    ATTENDED = "ATTENDED"
    MISSED = "MISSED"

class LinkStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    LOCKED = "LOCKED"

class AiKind(str, enum.Enum):
    INTAKE = "INTAKE"
    URGENCY = "URGENCY"
    MESSAGE_DRAFT = "MESSAGE_DRAFT"
    CASE_SUMMARY = "CASE_SUMMARY"
    REFERRAL_TARGET = "REFERRAL_TARGET"

class RoutingStatus(str, enum.Enum):
    """Case-level status of urgent specialty routing."""
    AWAITING_ACCEPTANCE = "AWAITING_ACCEPTANCE"
    ACCEPTED = "ACCEPTED"
    EXCEPTION = "EXCEPTION"

class SuggestionStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class MessageStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    RETRYING = "RETRYING"
    SENT = "SENT"
    MESSAGE_FAILED = "MESSAGE_FAILED"
    REJECTED = "REJECTED"

class Priority(str, enum.Enum):
    URGENT = "URGENT"
    HIGH = "HIGH"
    NORMAL = "NORMAL"

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.COORDINATOR)
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("facilities.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    specialty: Mapped[str | None] = mapped_column(String(60), nullable=True)  # matched against a case's required specialty
    authorised_to_close: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

class Facility(Base):
    __tablename__ = "facilities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(40), unique=True)
    facility_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    connector_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # FEED_SIMULATOR or CSV
    connection_status: Mapped[str] = mapped_column(String(20), default="NOT_CONNECTED", server_default="NOT_CONNECTED")
    time_zone: Mapped[str | None] = mapped_column(String(60), nullable=True)
    working_days: Mapped[list | None] = mapped_column(JSON, nullable=True)  # e.g. ["MON","TUE",...]
    last_event_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # the administrator who added the facility (A-11)

class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    display_label: Mapped[str] = mapped_column(String(120))
    age_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    data_origin: Mapped[str] = mapped_column(String(30), default="SYNTHETIC")
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("facilities.id"), nullable=True)
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)  # used only to verify patient secure links; never returned by staff APIs
    record_number: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)  # facility record number, a patient-match identifier
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)  # SMS contact for the secure patient link (synthetic demo data)
    preferred_language: Mapped[str] = mapped_column(String(10), default="en", server_default="en")

class Screening(Base):
    __tablename__ = "screenings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"))
    screening_type: Mapped[str] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(100))
    display_label: Mapped[str] = mapped_column(String(200))

class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"))
    screening_id: Mapped[str | None] = mapped_column(ForeignKey("screenings.id"), nullable=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"))
    coordinator_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    priority: Mapped[Priority] = mapped_column(Enum(Priority), default=Priority.NORMAL)
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus, native_enum=False, length=30), default=CaseStatus.NEW)
    tracker_id: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)  # R-20, created at T2
    status_entered_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    confirmatory_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_confirmed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    flag_overdue: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    flag_exception: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    flag_data_missing: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    flag_message_failed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    flag_not_explained: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    closure_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    linked_case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), nullable=True)  # R-56: a new case linked to a closed one
    next_action_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    next_action_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    delay_reason_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    delay_reason_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    delay_reason_recorded_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    delay_reason_recorded_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # Urgent specialty routing
    required_specialty: Mapped[str | None] = mapped_column(String(60), nullable=True)
    routing_status: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    routed_clinician_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    routing_stage: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # 0 primary, 1 escalated to coordinator, 2 backup clinician
    routing_first_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    routing_second_limit_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    routing_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    routing_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    routing_accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    routing_exception_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    routing_tried: Mapped[list | None] = mapped_column(JSON, nullable=True)  # clinician ids already offered the case
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, onupdate=_now)

class Referral(Base):
    __tablename__ = "referrals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"))
    status: Mapped[str] = mapped_column(String(30), default=ReferralStatus.SENT.value)
    target_specialty: Mapped[str | None] = mapped_column(String(60), nullable=True)
    packet: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    accepted_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decline_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    receiving_facility_id: Mapped[str | None] = mapped_column(ForeignKey("facilities.id"), nullable=True)
    receiving_clinician_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    referred_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    escalation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, onupdate=_now)

class Consultation(Base):
    """A child object of the case with its own states (R-11). It never changes the case status."""
    __tablename__ = "consultations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    type: Mapped[str] = mapped_column(String(30), default=ConsultationType.CLINICIAN_TO_CLINICIAN.value)
    state: Mapped[str] = mapped_column(String(20), default=ConsultationState.REQUESTED.value, index=True)
    source: Mapped[str] = mapped_column(String(20), default="STAFF")  # STAFF or PATIENT_LINK
    requester_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    recipient_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    recipient_specialty: Mapped[str | None] = mapped_column(String(60), nullable=True)
    referral_id: Mapped[str | None] = mapped_column(ForeignKey("referrals.id"), nullable=True)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_time: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thread: Mapped[list | None] = mapped_column(JSON, nullable=True)
    urgent: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    escalation_stage: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    accepted_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    outcome_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    outcome_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    outcome_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500))
    old_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)


class PatientLink(Base):
    """Secure patient link. Only a SHA-256 hash of the random token is stored."""
    __tablename__ = "patient_links"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default=LinkStatus.ACTIVE.value)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    superseded_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    # Simulated SMS delivery of the link (demo only; no SMS gateway is connected)
    delivery_channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    delivered_to: Mapped[str | None] = mapped_column(String(60), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

class PatientResponse(Base):
    """A response about a case: submitted by the patient via link, or recorded by staff on their behalf."""
    __tablename__ = "patient_responses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(20))  # PATIENT_LINK or STAFF_ASSISTED
    link_id: Mapped[str | None] = mapped_column(ForeignKey("patient_links.id"), nullable=True)
    submission_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    recorded_by_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"))
    type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    assigned_to_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

class AiSuggestion(Base):
    """A read-only AI suggestion. Nothing changes until a staff member approves it."""
    __tablename__ = "ai_suggestions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default=SuggestionStatus.PENDING.value)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), nullable=True, index=True)
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("facilities.id"), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    decided_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied: Mapped[dict | None] = mapped_column(JSON, nullable=True)

class Message(Base):
    """Outbound patient message. It cannot be sent until a staff member approves it (R-28)."""
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"))
    channel: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(40), default="RESULT_NOTICE", server_default="RESULT_NOTICE")
    language: Mapped[str] = mapped_column(String(10), default="en", server_default="en")
    template_version: Mapped[str] = mapped_column(String(20), default="v1", server_default="v1")
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=MessageStatus.DRAFT.value)
    source: Mapped[str] = mapped_column(String(20), default="STAFF")
    suggestion_id: Mapped[str | None] = mapped_column(ForeignKey("ai_suggestions.id"), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now, onupdate=_now)


class Setting(Base):
    """R-23: one store for time limits, routing rules, reminder schedules; scoped global, facility or specialty."""
    __tablename__ = "settings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    key: Mapped[str] = mapped_column(String(100), index=True)
    scope: Mapped[str] = mapped_column(String(100), default="global")  # "global", "facility:<id>" or "specialty:<NAME>"
    value: Mapped[dict | list | int | float | str | None] = mapped_column(JSON)
    changed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)

class SpecialtyBackup(Base):
    """R-29: the clinician named as backup for a specialty; the second escalation tries them first."""
    __tablename__ = "specialty_backups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    specialty: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    clinician_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("facilities.id"), nullable=True)
    changed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)

class DelayFollowup(Base):
    """R-18: staff follow-up with a reason-for-delay code on an OVERDUE case or a missed appointment."""
    __tablename__ = "delay_followups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    flag: Mapped[str] = mapped_column(String(30))  # OVERDUE or MISSED_APPOINTMENT
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    code: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    staff_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)

class Result(Base):
    """Original and confirmatory results are both stored."""
    __tablename__ = "results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("facilities.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="ORIGINAL")  # ORIGINAL or CONFIRMATORY
    test_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    test_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    abnormal: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    issued_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="MANUAL")  # FEED, UPLOAD, MANUAL
    event_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)

class Appointment(Base):
    __tablename__ = "appointments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("facilities.id"), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(UTCDateTime())
    attendance: Mapped[str] = mapped_column(String(20), default=Attendance.BOOKED.value)
    recorded_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    recorded_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)

class TreatmentStart(Base):
    """Evidence for T15 (R-48): a start date and a note or attachment."""
    __tablename__ = "treatment_starts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # TREATMENT or MONITORING
    start_date: Mapped[datetime] = mapped_column(UTCDateTime())
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    recorded_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)

class ContactAttempt(Base):
    """Logged attempts to reach a patient, by route (R-55) and the staff confirmation that clears MESSAGE_FAILED."""
    __tablename__ = "contact_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    route: Mapped[str] = mapped_column(String(20))  # PHONE, SMS, EMAIL, VISIT, OTHER
    outcome: Mapped[str] = mapped_column(String(20))  # REACHED or NOT_REACHED
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)

class Closure(Base):
    """Closure record (section 10). status PENDING_SIGNOFF holds an 'Other' closure until a second authorised person approves (R-54)."""
    __tablename__ = "closures"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    closure_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="CLOSED")  # PENDING_SIGNOFF or CLOSED
    reason: Mapped[str] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    second_signoff_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    second_approver_id: Mapped[str | None] = mapped_column(
    ForeignKey("users.id"),
    nullable=True,
    )
    transition_id: Mapped[str | None] = mapped_column(String(4), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

class InboundEvent(Base):
    """An event received by a connector (section 5). The event id makes receipt idempotent (R-24)."""
    __tablename__ = "inbound_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(String(80), index=True)
    type: Mapped[str] = mapped_column(String(40))
    facility_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # ACCEPTED, REJECTED, DUPLICATE
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    case_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    received_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)


class RoutingRule(Base):
    """R-27: routing and urgency criteria are data, not code. One row per pathway and result category. Placeholder content, not clinical guidance."""
    __tablename__ = "routing_rules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    pathway: Mapped[str] = mapped_column(String(100))
    result_category: Mapped[str] = mapped_column(String(200))
    suggested_urgency: Mapped[str | None] = mapped_column(String(20), nullable=True)  # a suggestion only; a person sets urgency (R-28a)
    confirmatory_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    specialty: Mapped[str | None] = mapped_column(String(60), nullable=True)
    primary_pool: Mapped[str | None] = mapped_column(String(100), nullable=True)
    backup_pool: Mapped[str | None] = mapped_column(String(100), nullable=True)
    time_to_accept_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_to_appointment_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=_now)


# ---- R-21: audit events are append-only ----
@event.listens_for(AuditEvent, "before_update")
@event.listens_for(AuditEvent, "before_delete")
def _audit_is_append_only(mapper, connection, target):
    raise audit_guard.AuditImmutableError(audit_guard.MESSAGE)

@event.listens_for(AuditEvent.__table__, "after_create")
def _install_audit_triggers(target, connection, **kw):
    audit_guard.install(connection)
