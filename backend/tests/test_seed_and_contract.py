from collections import Counter
from app import demo_data
from app.core import clock

def test_seeded_log_has_about_sixty_cases_across_the_states_and_flags(client, org):
    d = demo_data.Driver(client, org["ids"])
    s = demo_data.Seeder(d)
    s.window_days = 30
    s.run(); clock.reset()
    from app.scheduler import run_once
    run_once(client.session_factory)
    rows = d.call("national", "GET", "/cases", params={"pageSize": 100})
    assert 55 <= len(rows) <= 70
    states = Counter(r["status"] for r in rows)
    assert len(states) >= 9 and states["CLOSED"] >= 15
    flags = Counter(f for r in rows for f in r["flags"])
    for f in ("URGENT", "OVERDUE", "EXCEPTION", "UNASSIGNED", "NOT_EXPLAINED", "DATA_MISSING"):
        assert flags[f] >= 1, f
    m = d.call("national", "GET", "/measures")
    for k in ("m1", "m2", "m3", "m4", "m5", "m6"):
        assert k in m
    assert m["m3"]["referralAcceptedWithinLimit"]["denominator"] > 0
    assert len(d.call("coord", "GET", "/events/rejected")) == 2
    # the same cases are visible through the unversioned /api path the register uses
    assert d.c.get("/api/worklist", headers=d.auth("coord")).status_code == 200

def test_openapi_lists_the_new_areas(client):
    spec = client.get("/api/v1/openapi.json").json()
    paths = spec["paths"]
    for p in ("/api/v1/events", "/api/v1/measures", "/api/v1/settings/{key}", "/api/v1/consultations", "/api/v1/cases/{case_id}/close",
              "/api/v1/cases/{case_id}/appointments", "/api/v1/demo/clock/advance", "/api/v1/cases/transitions"):
        assert p in paths, p
    assert "/api/v1/cases/{case_id}/transition" not in paths

def test_error_envelope_and_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    r = client.get("/api/v1/cases")
    assert r.status_code == 401 and r.json()["success"] is False
