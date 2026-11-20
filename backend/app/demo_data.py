"""Simulated demonstration data (all synthetic). The case log is produced by driving the real API with the demo clock set
in the past, so every status change, flag and measure comes from the same state machine the live system uses."""
from datetime import datetime, timedelta
from app.core import clock
from app.core.security import hash_password
from app.models.entities import Facility, Patient, Role, User

PW = {"admin": "Admin123!", "coordinator": "Coordinator123!", "referring": "Referring123!", "receiving": "Receiving123!", "national": "National123!"}

BIRTH_YEARS: dict[str, int] = {}  # patient id -> birth year, so the driver can answer the secure-link check (the API never exposes it)

def build_org(db) -> dict:
    """Three facilities and a user for each role. Returns the ids by short name."""
    hc = Facility(name="Jusr Demo Health Centre", code="JUSR-DEMO", facility_type="HEALTH_CENTRE", connector_type="API", connection_status="CONNECTED")
    rrh = Facility(name="Demo Regional Referral Hospital", code="DEMO-RRH", facility_type="HOSPITAL", connector_type="API", connection_status="CONNECTED")
    dc = Facility(name="Demo District Clinic", code="DEMO-DC", facility_type="CLINIC", connector_type="MANUAL", connection_status="CONNECTED")
    db.add_all([hc, rrh, dc]); db.flush()
    def u(email, name, role, fac, pw, **kw):
        x = User(email=email, display_name=name, password_hash=hash_password(pw), role=role, facility_id=fac.id if fac else None, **kw); db.add(x); db.flush(); return x
    users = {
        "admin": u("admin@jusr.local", "Demo Facility Administrator", Role.FACILITY_ADMIN, hc, PW["admin"]),
        "coord": u("coordinator@jusr.local", "Demo Coordinator", Role.COORDINATOR, hc, PW["coordinator"], authorised_to_close=True),
        "coord2": u("coordinator2@jusr.local", "Demo Coordinator Two", Role.COORDINATOR, hc, PW["coordinator"]),
        "refer": u("referring@jusr.local", "Demo Referring Clinician", Role.REFERRING_CLINICIAN, hc, PW["referring"], authorised_to_close=True),
        "refer2": u("referring2@jusr.local", "Demo Referring Clinician Two", Role.REFERRING_CLINICIAN, dc, PW["referring"]),
        "coordR": u("coordinator.rrh@jusr.local", "Demo Hospital Coordinator", Role.COORDINATOR, rrh, PW["coordinator"]),
        "recv": u("receiving@jusr.local", "Demo Colposcopist", Role.RECEIVING_CLINICIAN, rrh, PW["receiving"], specialty="COLPOSCOPY"),
        "recv2": u("receiving2@jusr.local", "Demo Backup Colposcopist", Role.RECEIVING_CLINICIAN, rrh, PW["receiving"], specialty="COLPOSCOPY"),
        "recv3": u("receiving3@jusr.local", "Demo Oncology Clinician", Role.RECEIVING_CLINICIAN, rrh, PW["receiving"], specialty="ONCOLOGY"),
        "national": u("national@jusr.local", "Demo National Administrator", Role.NATIONAL_ADMIN, None, PW["national"]),
        "ai": u("ai@jusr.local", "Demo AI Service", Role.AI_SERVICE, None, PW["national"]),
    }
    ids = {k: v.id for k, v in users.items()}
    ids.update({"hc": hc.id, "rrh": rrh.id, "dc": dc.id})
    return ids

def add_patients(db, facility_id, n, start=1) -> list[str]:
    year = datetime.now().year
    out = []
    for i in range(start, start + n):
        age = 25 + (i * 7) % 35
        p = Patient(display_label=f"Patient {i:03d}", age_years=age, birth_year=year - age, sex="F", is_synthetic=True, data_origin="SYNTHETIC", facility_id=facility_id,
                    record_number=f"MRN{i:05d}", preferred_language="en" if i % 4 else "ar")
        db.add(p); db.flush(); out.append(p.id); BIRTH_YEARS[p.id] = year - age
    return out

class Driver:
    """Acts as the staff and the patient through the HTTP API. `client` is a Starlette TestClient."""
    def __init__(self, client, ids):
        self.c, self.ids, self.h = client, ids, {}
        self.emails = {"coord": "coordinator@jusr.local", "coord2": "coordinator2@jusr.local", "refer": "referring@jusr.local", "refer2": "referring2@jusr.local",
                       "coordR": "coordinator.rrh@jusr.local", "recv": "receiving@jusr.local", "recv2": "receiving2@jusr.local", "recv3": "receiving3@jusr.local",
                       "admin": "admin@jusr.local", "national": "national@jusr.local", "ai": "ai@jusr.local"}

    def auth(self, who):
        if who not in self.h:
            pw = PW["coordinator"] if who.startswith("coord") else PW["referring"] if who.startswith("refer") else PW["receiving"] if who.startswith("recv") else PW["admin"] if who == "admin" else PW["national"]  # national and ai share a password
            r = self.c.post("/api/v1/auth/login", data={"username": self.emails[who], "password": pw}); assert r.status_code == 200, r.text
            self.h[who] = {"Authorization": "Bearer " + r.json()["data"]["accessToken"]}
        return self.h[who]

    def call(self, who, method, path, ok=(200, 201), **kw):
        r = self.c.request(method, "/api/v1" + path, headers=self.auth(who), **kw)
        assert r.status_code in ok, f"{method} {path} as {who}: {r.status_code} {r.text}"
        return r.json().get("data") if r.headers.get("content-type", "").startswith("application/json") else r

    def wait(self, **delta):
        clock.advance(timedelta(**delta).total_seconds() / 60)

    def feed(self, event_id, facility, *, patient, case_number, screening="Cervical screening", confirmatory=False, test=("HPV16", "Positive"), who="coord"):
        body = {"eventId": event_id, "type": "RESULT_RECEIVED", "facilityId": self.ids[facility],
                "payload": {"caseNumber": case_number, "screeningType": screening, "outcome": "Abnormal", "confirmatoryRequired": confirmatory,
                            "patient": patient, "test": {"code": test[0], "name": test[0], "value": test[1], "abnormal": True}}}
        return self.call(who, "POST", "/events", json=body)

    def patient_link(self, case):
        d = self.call("coord", "POST", f"/cases/{case}/links")
        return d["url"].rsplit("/", 1)[-1] if "url" in d else d["token"]

    def notify(self, case, who="coord", urgent=False):
        """Coordinator drafts, approves and sends the result notice; delivery confirmation moves the case to AWAITING_ACK (T7)."""
        m = self.call(who, "POST", "/messages", json={"caseId": case, "channel": "SMS", "body": "Your result is ready. Open your secure link to read it."})
        self.call(who, "POST", f"/messages/{m['id']}/approve", json={})
        self.call(who, "POST", f"/messages/{m['id']}/send", json={})
        return m["id"]

    def patient_replies(self, token, *, understood="YES", confidence=4, case=None, birth_year=None):
        """The patient opens the secure link, acknowledges, says whether the result was understood and rates confidence."""
        hdr = {}
        if case and not birth_year:
            pid = self.call("coord", "GET", f"/cases/{case}")["patientId"]
            birth_year = BIRTH_YEARS.get(pid)
        if birth_year:
            r = self.c.post(f"/p/{token}/verify", json={"birthYear": birth_year}); assert r.status_code == 200, r.text
            sess = r.json()["data"]["sessionToken"]
            hdr = {"X-Patient-Session": sess} if sess else {}
        for path, body in (("ack", None), ("understanding", {"understood": understood}), ("confidence", {"rating": confidence})):
            r = self.c.post(f"/p/{token}/{path}", json=body, headers=hdr) if body else self.c.post(f"/p/{token}/{path}", headers=hdr)
            assert r.status_code in (200, 201), f"{path}: {r.status_code} {r.text}"

# ---------------------------------------------------------------- scenario log

class Seeder:
    """Builds the demonstration case log. Time starts 35 days in the past and moves forward as cases progress; the
    clock is reset at the end, so the newest cases are recent and the oldest finished long ago."""
    def __init__(self, d: Driver):
        self.d, self.n, self.pat = d, 0, 0
        self.window_days = 30
        self.log = []

    def _next(self, facility="hc"):
        self.n += 1; self.pat += 1
        pid = f"{self.pat:03d}"
        return f"JD-{self.n:04d}", {"name": f"Patient {pid}", "recordNumber": f"MRN{pid.zfill(5)}"}

    def start(self, label, *, confirmatory=False, screening="Cervical screening", facility="hc"):
        case, ident = self._next(facility)
        r = self.d.feed(f"EV-{case}", facility, patient=ident, case_number=case, confirmatory=confirmatory, screening=screening)
        self.d.wait(minutes=20)
        self.log.append((case, label)); return case

    def classify(self, case, *, urgent=False, who="refer", specialty="COLPOSCOPY"):
        body = {"actionable": True, "urgent": urgent}
        if urgent: body["specialty"] = specialty
        self.d.call(who, "POST", f"/cases/{case}/classify", json=body); self.d.wait(minutes=30)

    def to_ack(self, case, *, understood="YES", respond=True, confidence=4):
        self.d.notify(case); self.d.wait(minutes=15)
        if respond:
            self.d.patient_replies(self.d.patient_link(case), understood=understood, confidence=confidence, case=case); self.d.wait(hours=3)

    def refer(self, case, specialty="COLPOSCOPY", who="refer"):
        self.d.call(who, "POST", "/referrals", json={"caseId": case, "receivingFacilityId": self.d.ids["rrh"], "targetSpecialty": specialty, "reason": "Abnormal result needing specialist care"})
        self.d.wait(hours=2)

    def referral_of(self, case):
        referrals = self.d.call(
            "recv2",
            "GET",
            "/referrals",
            params={"caseId": case, "status": "SENT", "pageSize": 100}
        )
        for referral in referrals:
            return referral["id"]
        raise RuntimeError(f"No SENT referral found for case {case}")

    def accept(self, case, who="recv2"):
        rid = self.referral_of(case)
        self.d.call(who, "POST", f"/referrals/{rid}/accept", json={}); self.d.wait(hours=4)

    def book_attend(self, case, attended=True, days=3):
        a = self.d.call("coordR", "POST", f"/cases/{case}/appointments", json={"scheduledAt": (clock.now() + timedelta(days=days)).isoformat()}); self.d.wait(days=days)
        body = {"attendance": "ATTENDED"} if attended else {"attendance": "MISSED", "reasonCode": "PATIENT_UNREACHABLE", "note": "Did not attend"}
        self.d.call("coordR", "POST", f"/cases/{case}/appointments/{a['id']}/attendance", json=body); self.d.wait(hours=6)

    def treat(self, case, kind="TREATMENT"):
        self.d.call("recv2", "POST", f"/cases/{case}/treatment-start", json={"kind": kind, "startDate": clock.now().isoformat(), "note": "Start recorded by the treating clinician"}); self.d.wait(hours=8)

    def close(self, case, ctype="CARE_CONFIRMED", reason="Care confirmed", who="coord"):
        body = {"closureType": ctype, "reason": reason}
        if ctype in ("NO_FURTHER_CARE", "NOT_ACTIONABLE", "PATIENT_DECLINED", "UNREACHABLE"):
            body["decision"] = reason
        self.d.call(who, "POST", f"/cases/{case}/close", json=body); self.d.wait(hours=1)

    # -- scenarios
    def s_full(self, i):
        c = self.start("S1 routine referral to treatment, closed")
        self.classify(c)
        self.to_ack(c, confidence=3 + i % 3)
        self.refer(c)
        self.accept(c)
        self.book_attend(c)
        self.treat(c)
        self.close(c)

    def s_confirm_no_care(self, i):
        c = self.start("S2 confirmatory test shows no care needed", confirmatory=True); self.classify(c); self.to_ack(c)
        self.d.call("coord", "POST", "/events", json={"eventId": f"CONF-{c}", "type": "CONFIRMATORY_RESULT_RECEIVED", "facilityId": self.d.ids["hc"],
                                                     "payload": {"caseId": c, "test": {"code": "COLPO", "name": "Colposcopy", "value": "Normal", "abnormal": False}}}); self.d.wait(days=2)
        self.d.call("refer", "POST", f"/cases/{c}/confirmatory-outcome", json={"outcome": "Normal", "reason": "Confirmatory test is normal"}); self.d.wait(hours=2)
        self.close(c, "NO_FURTHER_CARE", "Confirmatory test normal, no further care", who="refer")

    def s_confirm_refer(self, i):
        c = self.start("S3 confirmatory then referral, treated", confirmatory=True); self.classify(c); self.to_ack(c)
        self.d.call("coord", "POST", "/events", json={"eventId": f"CONF-{c}", "type": "CONFIRMATORY_RESULT_RECEIVED", "facilityId": self.d.ids["hc"],
                                                     "payload": {"caseId": c, "test": {"code": "COLPO", "name": "Colposcopy", "value": "CIN2", "abnormal": True}}}); self.d.wait(days=2)
        self.refer(c); self.accept(c); self.book_attend(c); self.treat(c, "MONITORING" if i % 2 else "TREATMENT")
        if i % 2 == 0: self.close(c)

    def s_not_actionable(self, i):
        c = self.start("S4 not actionable")
        self.d.call("refer", "POST", f"/cases/{c}/classify", json={"actionable": False, "reason": "Result is a false alarm on review"}); self.d.wait(hours=1)

    def s_urgent(self, i):
        c = self.start("S5 urgent routed and accepted"); self.classify(c, urgent=True)
        routed = self.d.call("coord", "GET", f"/cases/{c}/urgent-routing")["routing"]["routedClinician"]["id"]
        self.d.call("recv" if routed == self.d.ids["recv"] else "recv2", "POST", f"/urgent-cases/{c}/accept", json={}); self.d.wait(minutes=40)
        self.to_ack(c, respond=i % 2 == 0)
        if i % 2 == 0:
            self.refer(c); 
            if i % 4 == 0: self.accept(c)

    def s_open_notifying(self, i):
        c = self.start("S6 waiting at notification"); self.classify(c)
        if i % 2: self.d.notify(c)

    def s_not_explained(self, i):
        c = self.start("S7 patient did not understand"); self.classify(c); self.to_ack(c, understood="PARTLY", confidence=2)

    def s_declined(self, i):
        c = self.start("S8 referral declined"); self.classify(c); self.to_ack(c); self.refer(c)
        rid = self.referral_of(c)
        self.d.call("recv2", "POST", f"/referrals/{rid}/decline", json={"code": "NO_CAPACITY", "reason": "No capacity this month"}); self.d.wait(hours=6)
        if i % 3 != 0:
            self.refer(c); self.accept(c, "recv2")
            if i % 3 == 1: self.book_attend(c)

    def s_missed(self, i):
        c = self.start("S9 missed appointment"); self.classify(c); self.to_ack(c); self.refer(c); self.accept(c); self.book_attend(c, attended=False)

    def s_unreachable(self, i):
        c = self.start("S10 unreachable and closed"); self.classify(c); self.to_ack(c, respond=False)
        self.d.wait(days=8)
        for route in ("PHONE", "PHONE", "SMS"):
            self.d.call("coord", "POST", f"/cases/{c}/contact-attempts", json={"route": route, "outcome": "NOT_REACHED", "note": "No answer"}); self.d.wait(days=1)
        self.d.call("coord", "POST", f"/cases/{c}/assign", json={"ownerId": self.d.ids["refer"]})  # the clinician who decides becomes the named owner
        self.d.call("refer", "POST", f"/cases/{c}/close", json={"closureType": "UNREACHABLE", "reason": "Patient could not be reached", "decision": "Close as unreachable", "evidence": "3 attempts on 2 routes"})

    def s_low_match(self, i):
        case, ident = self._next()
        self.d.feed(f"EV-{case}", "hc", patient={"name": ident["name"]}, case_number=case)
        self.log.append((case, "S11 weak patient match waiting for a coordinator")); self.d.wait(hours=2)

    def s_consult(self, i):
        c = self.start("S12 clinician consultation"); self.classify(c); self.to_ack(c)
        k = self.d.call("refer", "POST", "/consultations", json={"caseId": c, "type": "CLINICIAN_TO_CLINICIAN", "recipientSpecialty": "COLPOSCOPY", "question": "Is a colposcopy needed before a referral?"})
        self.d.wait(hours=3)
        if i % 3 != 2:
            self.d.call("recv2", "POST", f"/consultations/{k['id']}/accept", json={}); self.d.wait(hours=2)
            if i % 3 == 0:
                self.d.call("recv2", "POST", f"/consultations/{k['id']}/outcome", json={"outcomeType": "ADVICE_GIVEN", "note": "Refer directly for colposcopy"}); self.d.wait(hours=1)
        self.refer(c)

    def extras(self):
        """Feed problems and one case at a second facility: a repeated event, refused events, a silent feed (DATA_MISSING), a patient who moved."""
        ids = self.d.ids
        self.n += 1; case = f"JD-{self.n:04d}"
        self.d.feed(f"EV-{case}", "dc", patient={"name": "Patient 101", "recordNumber": "MRN00101"}, case_number=case, who="national"); self.log.append((case, "S13 case at the district clinic"))
        self.d.wait(hours=4)
        dup = {"eventId": f"EV-{case}", "type": "RESULT_RECEIVED", "facilityId": ids["dc"], "payload": {}}
        self.d.call("national", "POST", "/events", json=dup)                                       # duplicate: logged, nothing changes
        for k, bad in enumerate(({"patient": {"name": "Unknown Person", "recordNumber": "NOPE"}, "test": {"code": "HPV16", "value": "Positive"}},
                                 {"patient": {"name": "Patient 102", "recordNumber": "MRN00102"}, "test": {"code": "", "value": ""}})):
            r = self.d.c.post("/api/v1/events", headers=self.d.auth("coord"), json={"eventId": f"BAD-{k}", "type": "RESULT_RECEIVED", "facilityId": ids["hc"], "payload": bad})
            assert r.status_code == 422, r.text
        self.d.wait(days=1)
        self.d.call("national", "POST", "/events", json={"eventId": "FEED-GAP-1", "type": "FEED_MISSING", "facilityId": ids["dc"], "payload": {}})
        self.d.wait(hours=1)

    def run(self):
        plan = [(self.s_full, 12), (self.s_confirm_no_care, 5), (self.s_confirm_refer, 7), (self.s_not_actionable, 4), (self.s_urgent, 7), (self.s_not_explained, 3), (self.s_consult, 4),
                (self.s_declined, 4), (self.s_missed, 3), (self.s_unreachable, 2), (self.s_low_match, 2), (self.s_open_notifying, 8)]
        # interleave so the log does not read in blocks
        queue = []
        for fn, n in plan:
            queue += [(fn, i) for i in range(n)]
        order = sorted(range(len(queue)), key=lambda k: (queue[k][1], k))
        # Each scenario starts far enough back that it finishes before now; the later ones start more recently.
        span = {"s_full": 5, "s_confirm_no_care": 5, "s_confirm_refer": 9, "s_not_actionable": 0.2, "s_urgent": 5, "s_not_explained": 1, "s_consult": 1,
                "s_declined": 4, "s_missed": 6, "s_unreachable": 12, "s_low_match": 0.2, "s_open_notifying": 1}
        total = len(order)
        for n, k in enumerate(order):
            fn, i = queue[k]
            need = span[fn.__name__]
            window = {"s_open_notifying": 6, "s_not_explained": 8, "s_consult": 8, "s_low_match": 4, "s_missed": 14, "s_declined": 14, "s_urgent": 14}.get(fn.__name__, self.window_days)
            days_ago = need + max(0, window - need) * (1 - n / total)
            clock.reset(); clock.advance(-days_ago * 1440)
            fn(i)
        clock.reset(); clock.advance(-0.5 * 1440)
        self.extras()
        return self.log
