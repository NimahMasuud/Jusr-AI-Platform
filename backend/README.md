# Jusr AI FastAPI Backend (v6)

Backend for the Jusr AI prototype, built to the Jusr AI Developer Guide (Part 1: scope, roles and the case state machine; Part 2: requirements R-01 to R-74 and acceptance tests). FastAPI, SQLAlchemy 2, Alembic, PostgreSQL. **All data is simulated**: every patient, result and clinician is synthetic and no real EMR is connected.

## What it does
- **Case state machine (section 3).** Eleven statuses and transitions T1 to T17 held in one table (`app/services/state_machine.py`, readable at `GET /api/v1/cases/transitions`). No screen sets a status directly. Each transition checks who may do it, that the case is in the right status and that its guard holds. A refused move changes nothing and is logged (R-12).
- **Seven flags:** URGENT, OVERDUE, EXCEPTION, UNASSIGNED, DATA_MISSING, MESSAGE_FAILED, NOT_EXPLAINED.
- **Time limits per status live in a settings store (R-23)** with scope specialty > facility > global > built-in default. A changed limit applies to cases already in the status (A-28). Every change is logged.
- **Referrals, appointments, treatment start, closure** with evidence rules per closure type (section 10), a checklist endpoint (R-53) and the two-step "Other" closure.
- **Consultations** (clinician to clinician, and patient call-back) with their own states, limits and escalation (R-49 to R-51).
- **Event ingestion** (`POST /events`, `/events/batch`): idempotent (R-24), invalid events refused, logged and listed (R-25), patient matching by a fixed rule (R-37), a feed monitor that sets DATA_MISSING.
- **Measures M1 to M6** (`GET /measures`) calculated from the event log only, each as numerator, denominator and value. `GET /events/export` (json or csv) lets anyone recompute them by hand (A-22). Baseline values are marked as assumptions.
- **Patient secure link**, assisted (staff-recorded) responses, AI suggestions that staff must approve, approved-before-sent messages with retries, urgent routing with escalation, append-only audit log, scheduler.
- **Demo clock (R-66):** `POST /demo/clock/advance` moves time forward so overdue cases appear without waiting (national admin only, `DEMO_MODE=true`).
- **Seeded log:** about 60 cases covering every status, flag and closure type, built by driving the real API with the clock set in the past.

## Run with Docker
```bash
cp .env.example .env
docker compose up --build
```
API http://localhost:8000, Swagger http://localhost:8000/docs, OpenAPI http://localhost:8000/api/v1/openapi.json. Routes are also served under `/api/...` (same handlers). Patient links are served at `/p/{token}`.

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python -m app.seed          # org, users and ~60 simulated cases (takes about 20 seconds; skipped if users exist)
uvicorn app.main:app --reload
```

## Demo accounts
| Account | Password | Role / facility |
|---|---|---|
| `coordinator@jusr.local` | `Coordinator123!` | Coordinator, Health Centre (authorised to close) |
| `coordinator2@jusr.local` | `Coordinator123!` | Coordinator, Health Centre |
| `referring@jusr.local` | `Referring123!` | Referring clinician, Health Centre (authorised to close) |
| `referring2@jusr.local` | `Referring123!` | Referring clinician, District Clinic |
| `coordinator.rrh@jusr.local` | `Coordinator123!` | Coordinator, Referral Hospital |
| `receiving@jusr.local`, `receiving2@jusr.local` | `Receiving123!` | Receiving clinicians, Referral Hospital (colposcopy) |
| `receiving3@jusr.local` | `Receiving123!` | Receiving clinician, Referral Hospital (oncology) |
| `admin@jusr.local` | `Admin123!` | Facility administrator (staff and facility data only, no cases) |
| `national@jusr.local` | `National123!` | National administrator (all facilities, settings, demo clock) |
| `ai@jusr.local` | `National123!` | AI service (can only submit suggestions) |

Login uses OAuth2 form fields: `username` is the email.

## Roles and access
`COORDINATOR`, `REFERRING_CLINICIAN`, `RECEIVING_CLINICIAN`, `FACILITY_ADMIN`, `NATIONAL_ADMIN`, `AI_SERVICE`, `PATIENT`. Role and facility come from the signed-in user, never from a parameter. Rules are in `app/core/permissions.py`. A case is visible to the facility that owns it, its named owner, a consultation participant (R-52), and the receiving side once a referral is accepted. The facility administrator receives 403 on every patient and case endpoint (R-09). Patient messages are drafted, approved and sent by coordinators only (R-28).

## Tests
```bash
pytest          # 49 tests, about 10 seconds, SQLite
```
Covers the golden path, allowed and refused transitions, closure rules, time limits and the demo clock, settings, event idempotency and refusal, access control, urgent routing deadlines, referral time-outs, consultations, patient links, AI approvals, the audit log, measures against the exported log, the seeded log and the OpenAPI contract. **PostgreSQL has not been run**: the audit-log triggers and the row locks in the scheduler are written for it but untested there.

## Layout
`app/services/state_machine.py` (T1 to T17, guards, closure rules, OVERDUE) · `settings_store.py` · `measures.py` · `workflow.py` (shared by staff calls, AI approvals and events) · `routing.py` (urgent routing) · `messaging.py` · `app/api/v1/endpoints/*` · `app/demo_data.py` and `app/seed.py` · `migrations/versions/0006_state_machine_rebuild.py`.

## Upgrading an older database
`alembic upgrade head`. Revision 0006 adds the new tables and columns, maps the old case statuses (OPEN to AWAITING_CLASSIFICATION, ASSIGNED to NOTIFYING, RESOLVED to CLOSED) and referral statuses (PENDING to SENT, REJECTED to DECLINED), and replaces the old consultations table. This path was checked on SQLite with a hand-damaged schema, not on a real legacy Postgres database. For the prototype it is simpler to start from an empty database.

## Known gaps
Reminders at 50% and 100% of a limit (R-32) and a named backup clinician per specialty are not built. The unreachable closure checks attempts and routes but not the "more than 7 days" window against the first attempt. Working days are Monday to Friday for every facility. CSV staff import and a CSV connector are not built. Message delivery is simulated.
