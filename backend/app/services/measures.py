"""Measures M1 to M6 (section 12), always calculated from the event log and the records it points to, never from stored counters.
Every figure returns its numerator and denominator so the frontend and the hand calculation (A-22) can be checked against it."""
import math
import statistics
from datetime import timedelta
from sqlalchemy import or_
from app.core import clock
from app.core.permissions import GLOBAL_ROLES
from app.models.entities import (Appointment, AuditEvent, Attendance, Case, CaseStatus, Closure, ClosureType, Consultation, ConsultationState, DelayFollowup, PatientResponse,
                                 Referral, ReferralStatus, Result, Role, Screening, TreatmentStart)
from app.services import settings_store, state_machine as sm

DEFINITIONS = {
    "M1": "Time from the result being received (T1) to the patient being notified (T7), for cases that reached T7. Median and 90th percentile (nearest rank), in hours.",
    "M2": "Acknowledged within limit: of cases that reached T7, the share where the patient (or staff on the patient's behalf) acknowledged within the AWAITING_ACK limit counted from T7. "
          "Understood: of cases with an understanding answer, the share whose latest answer is YES.",
    "M3": "Referral accepted within limit: of referrals sent, the share ACCEPTED within the REFERRAL_PENDING limit of being sent. Attended: of appointments with attendance recorded, the share ATTENDED.",
    "M4": "Median hours from the result being received (T1) to: the confirmatory result being stored, the first consultation outcome recorded, attendance recorded (T14), and treatment or monitoring start (T15).",
    "M5": "Open cases by status and age (days since T1). Documented closure: of closed cases, the share whose closure record still meets its evidence rules. "
          "Reasons for delay: count of reason-for-delay codes recorded. Drop-off: closed cases by type PATIENT_DECLINED, UNREACHABLE, MOVED_OR_TRANSFERRED or OTHER.",
    "M6": "Understanding: share of YES answers (latest per case). Confidence: mean of the latest 1 to 5 rating per case. Reassurance: mean of the latest 1 to 5 reassurance rating per case, asked after attendance.",
}
DROP_OFF = (ClosureType.PATIENT_DECLINED.value, ClosureType.UNREACHABLE.value, ClosureType.MOVED_OR_TRANSFERRED.value, ClosureType.OTHER.value)
AGE_BUCKETS = (("0-2", 0, 2), ("3-7", 3, 7), ("8-14", 8, 14), ("15+", 15, 10**6))

def _h(delta) -> float:
    return round(delta.total_seconds() / 3600, 2)

def _ratio(n, d):
    return {"numerator": n, "denominator": d, "value": round(n / d, 4) if d else None}

def _dist(hours: list[float]):
    if not hours:
        return {"n": 0, "medianHours": None, "p90Hours": None}
    s = sorted(hours)
    return {"n": len(s), "medianHours": round(statistics.median(s), 2), "p90Hours": s[max(math.ceil(0.9 * len(s)) - 1, 0)]}

def _median(hours):
    return {"n": len(hours), "medianHours": round(statistics.median(hours), 2) if hours else None}

def scoped_cases(db, user, *, facility_id=None, pathway=None, since=None, until=None):
    q = db.query(Case)
    if user.role in GLOBAL_ROLES:
        if facility_id: q = q.filter(Case.facility_id == facility_id)
    elif user.role in (Role.COORDINATOR, Role.FACILITY_ADMIN):
        q = q.filter(Case.facility_id == user.facility_id)  # aggregates only; no case content is returned (R-09)
    else:  # clinicians see their own cases (Part 1 matrix)
        from sqlalchemy import select
        part = Case.id.in_(select(Consultation.case_id).where(or_(Consultation.requester_id == user.id, Consultation.recipient_id == user.id)))
        refd = Case.id.in_(select(Referral.case_id).where(or_(Referral.referred_by_id == user.id, Referral.receiving_clinician_id == user.id)))
        q = q.filter(or_(Case.coordinator_id == user.id, Case.routed_clinician_id == user.id, part, refd))
    if pathway:
        q = q.join(Screening, Case.screening_id == Screening.id).filter(Screening.screening_type.ilike(f"%{pathway}%"))
    if since: q = q.filter(Case.created_at >= since)
    if until: q = q.filter(Case.created_at <= until)
    return q.all()

def compute(db, user, *, facility_id=None, pathway=None, since=None, until=None) -> dict:
    now = clock.now()
    cases = scoped_cases(db, user, facility_id=facility_id, pathway=pathway, since=since, until=until)
    ids = [c.id for c in cases]
    by_id = {c.id: c for c in cases}
    t: dict[str, dict[str, object]] = {i: {} for i in ids}  # case id -> transition id -> first time it happened (from the event log)
    if ids:
        for e in db.query(AuditEvent).filter(AuditEvent.case_id.in_(ids), AuditEvent.event_type == "CASE_TRANSITION").order_by(AuditEvent.occurred_at, AuditEvent.id).all():
            tid = (e.new_values or {}).get("transition")
            if tid: t[e.case_id].setdefault(tid, e.occurred_at)
    def rows(model, col=None):
        return db.query(model).filter(model.case_id.in_(ids)).all() if ids else []

    # M1
    m1 = [_h(t[i]["T7"] - t[i]["T1"]) for i in ids if "T1" in t[i] and "T7" in t[i]]
    # M2 and M6: patient responses
    resp: dict[str, dict[str, list]] = {i: {} for i in ids}
    for r in sorted(rows(PatientResponse), key=lambda r: (r.created_at, r.id)):
        resp[r.case_id].setdefault(r.kind, []).append(r)
    ack_n = ack_d = 0
    for i in ids:
        if "T7" not in t[i]: continue
        ack_d += 1
        acks = [r for r in resp[i].get("ACKNOWLEDGEMENT", []) if (r.value or {}).get("acknowledged", True)]
        due = settings_store.add_limit(t[i]["T7"], settings_store.status_limit(db, CaseStatus.AWAITING_ACK, facility_id=by_id[i].facility_id))
        if acks and acks[0].created_at <= due: ack_n += 1
    und_n = und_d = 0
    conf, reas = [], []
    for i in ids:
        if resp[i].get("UNDERSTANDING"):
            und_d += 1
            und_n += sm.understanding_level(resp[i]["UNDERSTANDING"][-1]) == "YES"
        if resp[i].get("CONFIDENCE"): conf.append((resp[i]["CONFIDENCE"][-1].value or {}).get("rating"))
        if resp[i].get("REASSURANCE"): reas.append((resp[i]["REASSURANCE"][-1].value or {}).get("rating"))
    conf = [c for c in conf if isinstance(c, (int, float))]; reas = [c for c in reas if isinstance(c, (int, float))]
    # M3
    refs = rows(Referral)
    ref_ok = sum(1 for r in refs if r.status == ReferralStatus.ACCEPTED.value and r.decided_at and
                 r.decided_at <= settings_store.add_limit(r.created_at, settings_store.status_limit(db, CaseStatus.REFERRAL_PENDING, facility_id=by_id[r.case_id].facility_id)))
    appts = [a for a in rows(Appointment) if a.attendance in (Attendance.ATTENDED.value, Attendance.MISSED.value)]
    attended = sum(1 for a in appts if a.attendance == Attendance.ATTENDED.value)
    # M4
    first_conf, first_outcome = {}, {}
    for r in rows(Result):
        if r.kind == "CONFIRMATORY": first_conf.setdefault(r.case_id, r.received_at)
    for c in sorted(rows(Consultation), key=lambda c: (c.outcome_at or now, c.id)):
        if c.state == ConsultationState.OUTCOME_RECORDED.value and c.outcome_at: first_outcome.setdefault(c.case_id, c.outcome_at)
    def since_t1(i, when): return _h(when - t[i]["T1"]) if "T1" in t[i] and when else None
    m4 = {"toConfirmatoryResult": [v for v in (since_t1(i, first_conf.get(i)) for i in ids) if v is not None],
          "toConsultationOutcome": [v for v in (since_t1(i, first_outcome.get(i)) for i in ids) if v is not None],
          "toAttendance": [v for v in (since_t1(i, t[i].get("T14")) for i in ids) if v is not None],
          "toTreatmentStart": [v for v in (since_t1(i, t[i].get("T15")) for i in ids) if v is not None]}
    # M5
    open_cases = [c for c in cases if c.status != CaseStatus.CLOSED]
    by_status: dict[str, dict[str, int]] = {}
    for c in open_cases:
        age = max(0, (now - (t[c.id].get("T1") or c.created_at)).days)
        bucket = next(name for name, lo, hi in AGE_BUCKETS if lo <= age <= hi)
        by_status.setdefault(c.status.value, {}).setdefault(bucket, 0)
        by_status[c.status.value][bucket] += 1
    closures = {cl.case_id: cl for cl in rows(Closure) if cl.status == "CLOSED"}
    documented = sum(1 for cid, cl in closures.items()
                     if not sm.missing_for_closure(db, by_id[cid], ClosureType(cl.closure_type), decision=cl.decision, evidence=cl.evidence, reason=cl.reason))
    delay: dict[str, int] = {}
    for f in rows(DelayFollowup): delay[f.code] = delay.get(f.code, 0) + 1
    closed_by_type: dict[str, int] = {}
    for cl in closures.values(): closed_by_type[cl.closure_type] = closed_by_type.get(cl.closure_type, 0) + 1
    dropoff = sum(n for k, n in closed_by_type.items() if k in DROP_OFF)

    def base(key): return settings_store.get(db, f"baseline.{key}")
    baseline = {"assumed": True, "note": "Assumed comparison values set in settings. They are simulated, not clinical results.",
                "m1": {"medianHours": base("m1_median_hours"), "p90Hours": base("m1_p90_hours")},
                "m2": {"acknowledgedShare": base("m2_acknowledged_share"), "understoodShare": base("m2_understood_share")},
                "m3": {"referralAcceptedShare": base("m3_referral_accepted_share"), "attendedShare": base("m3_attended_share")},
                "m4": {"toTreatmentStartMedianHours": base("m4_treatment_median_hours")}, "m5": {"dropOffShare": base("m5_dropoff_share")}}
    return {
        "scope": {"caseCount": len(cases), "facilityId": facility_id, "pathway": pathway, "since": since, "until": until, "calculatedAt": now, "source": "event log"},
        "definitions": DEFINITIONS,
        "m1": {"resultToNotified": _dist(m1)},
        "m2": {"acknowledgedWithinLimit": _ratio(ack_n, ack_d), "understood": _ratio(und_n, und_d)},
        "m3": {"referralAcceptedWithinLimit": _ratio(ref_ok, len(refs)), "attended": _ratio(attended, len(appts))},
        "m4": {k: _median(v) for k, v in m4.items()},
        "m5": {"openByStatusAndAge": by_status, "openTotal": len(open_cases), "documentedClosure": _ratio(documented, len(closures)),
               "delayReasons": delay, "closedByType": closed_by_type, "dropOff": _ratio(dropoff, len(closures))},
        "m6": {"understood": _ratio(und_n, und_d), "meanConfidence": {"n": len(conf), "mean": round(sum(conf) / len(conf), 2) if conf else None},
               "meanReassurance": {"n": len(reas), "mean": round(sum(reas) / len(reas), 2) if reas else None}},
        "baseline": baseline,
    }
