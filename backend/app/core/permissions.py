"""Central role and facility rules. The backend, not the frontend, is the security boundary."""
from sqlalchemy import or_, select
from app.models.entities import Case, Consultation, Referral, ReferralStatus, Role

# Read across every facility.
GLOBAL_ROLES = {Role.NATIONAL_ADMIN, Role.AI_SERVICE}
# Roles that may see patient and clinical case content. FACILITY_ADMIN and PATIENT are excluded (R-09).
CLINICAL_ROLES = {Role.COORDINATOR, Role.REFERRING_CLINICIAN, Role.RECEIVING_CLINICIAN, Role.NATIONAL_ADMIN, Role.AI_SERVICE}
# Roles that may change workflow state. AI_SERVICE may suggest but never decide (R-02, R-08).
WORKFLOW_ROLES = {Role.COORDINATOR, Role.REFERRING_CLINICIAN, Role.RECEIVING_CLINICIAN, Role.NATIONAL_ADMIN}
ASSIGN_ROLES = {Role.COORDINATOR, Role.NATIONAL_ADMIN}
CREATE_ROLES = {Role.COORDINATOR, Role.REFERRING_CLINICIAN, Role.NATIONAL_ADMIN}

def role_values(roles) -> tuple[str, ...]:
    return tuple(r.value for r in roles)

def visible_cases(q, user):
    """Restrict a Query/Select on Case to what the user may see.

    Staff: own facility and cases they own (including cross-facility).
    Receiving clinicians: only cases referred to their facility or urgently routed to them, never the
    general facility worklist.
    """
    if user.role in GLOBAL_ROLES:
        return q
    # R-52: participants named in a consultation see the case, even at another facility.
    participant = Case.id.in_(select(Consultation.case_id).where(or_(Consultation.requester_id == user.id, Consultation.recipient_id == user.id)))
    if user.role == Role.RECEIVING_CLINICIAN:
        clauses = [Case.routed_clinician_id == user.id, Case.coordinator_id == user.id, participant]
        if user.facility_id:
            clauses.append(Case.id.in_(select(Referral.case_id).where(Referral.receiving_facility_id == user.facility_id)))
        return q.filter(or_(*clauses))
    return q.filter(or_(Case.facility_id == user.facility_id, Case.coordinator_id == user.id, participant))

def can_view_case(user, case, db=None) -> bool:
    if user.role not in CLINICAL_ROLES:
        return False
    if user.role in GLOBAL_ROLES:
        return True
    if db is not None and db.query(Consultation.id).filter(Consultation.case_id == case.id, or_(Consultation.requester_id == user.id, Consultation.recipient_id == user.id)).first():
        return True
    if user.role == Role.RECEIVING_CLINICIAN:
        if case.routed_clinician_id == user.id or case.coordinator_id == user.id:
            return True
        return bool(db is not None and user.facility_id and
                    db.query(Referral.id).filter(Referral.case_id == case.id, Referral.receiving_facility_id == user.facility_id).first())
    return case.coordinator_id == user.id or case.facility_id == user.facility_id

def visible_referrals(q, user):
    """Restrict a Query on Referral (already joined to Case) to referrals the user may see:
    outgoing from their facility or owned cases, and incoming to their facility."""
    if user.role in GLOBAL_ROLES:
        return q
    return q.filter(or_(Case.facility_id == user.facility_id, Case.coordinator_id == user.id, Referral.receiving_facility_id == user.facility_id))

def can_modify_case(user, case) -> bool:
    """Workflow changes need a workflow role plus own facility or named ownership (not just referral visibility)."""
    if user.role not in WORKFLOW_ROLES:
        return False
    return user.role == Role.NATIONAL_ADMIN or case.facility_id == user.facility_id or case.coordinator_id == user.id

def accepted_receiving_side(db, user, case) -> bool:
    """A coordinator or receiving clinician at the facility that accepted the referral (they book and record attendance, R-47)."""
    if user.role not in (Role.COORDINATOR, Role.RECEIVING_CLINICIAN) or not user.facility_id:
        return False
    return db.query(Referral.id).filter(Referral.case_id == case.id, Referral.status == ReferralStatus.ACCEPTED.value,
                                        Referral.receiving_facility_id == user.facility_id).first() is not None
