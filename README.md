# Jusr AI Prototype (v6)

Jusr AI is a prototype built to the Jusr AI Developer Guide (Part 1: scope, roles and the case state machine; Part 2: requirements R-01 to R-74 and acceptance tests). It has three parts: a FastAPI backend (SQLAlchemy 2, Alembic, PostgreSQL), a React + TypeScript + Vite frontend, and a separate suggest-only AI helper service (Nimah). **All data is simulated**: every patient, result and clinician is synthetic and no real EMR is connected.

Start the backend first. The frontend and the AI service both talk to it, and the app works without the AI service.

## Contents
- [Backend](#backend)
- [Frontend](#frontend)
- [AI helper service (Nimah)](#ai-helper-service-nimah)

---

# Backend

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

---

# Frontend

The frontend is a React + TypeScript app built with Vite, using HMR and ESLint. It talks to the backend API described above (default http://localhost:8000), so start the backend first.

## Run
From the frontend directory:
```bash
npm install
npm run dev       # development server with HMR
npm run build     # production build into dist/
npm run lint      # ESLint
```

## Vite plugins
Two official plugins are available for React:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler
The React Compiler is not enabled because of its impact on dev and build performance. To add it, see [the React documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration
For a production application, enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://npmx.dev/package/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://npmx.dev/package/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

---

# AI helper service (Nimah)

Suggests only. A person decides. Everything is simulated.

Five helpers help staff with case intake, urgency, patient messages, case summaries and referral targets. They never change a case. In **backend mode** (the real setup) the service submits each result to the Jusr AI backend as a **PENDING suggestion**, and a staff member approves or rejects it there. In **standalone mode** the service keeps the suggestions itself, so the AI part can be tried without the backend.

## Quick start

```bash
cd ai
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
pytest                             # 75 tests should pass
uvicorn app.main:app --reload --port 8100
```

Open http://localhost:8100/docs for the interactive API page. Use the headers `X-Staff-Id` and `X-Role` (placeholder login).

**With this project:** run the backend first (`uvicorn app.main:app` on port 8000, seeded with `python -m app.seed`). The demo seed creates the `ai@jusr.local` AI_SERVICE account and `.env.example` already points at it. Any suggestion submitted through this service appears as PENDING in the app's **AI review** page, where a staff member approves or rejects it. The app works without this service; the backend's own message-draft and document-extraction helpers stay available.

## The helpers

| Helper | What it does | Approved by (Kafilat, 12 Nov) | Model or rules |
|---|---|---|---|
| Intake (`document_read`) | Reads a referral letter or lab report and fills in the case details. In backend mode it proposes a new case | Coordinator | Rules read labelled lines. A model can read free text; every field must come with an exact quote found in the document or it is dropped |
| Urgency | Suggests urgent, clinician decides, routine, or no suggestion | Referring clinician | **Rules only**, from `config/urgency_criteria.json` |
| Patient message | Drafts a plain-language message | Coordinator | Template. A model can also translate; any non-English text is flagged for review |
| Case summary | One line per event, each citing its event | Referring clinician | Rules. A model can summarise; lines citing no real event are dropped |
| Referral target | Suggests where to refer, with a backup | Referring clinician | **Rules only**, from `config/routing_table.json` |

**Urgency and referral targets never use a model.** The thresholds are Kafilat's **draft mock values** (her Urgency rules and Routing sheets, mock list of 7 Nov 2026). They are not verified against Abu Dhabi medical standards, and the end users decide the real ones. The helper never guesses: a value with no rule, an unknown unit, a missing value, or an unnamed sub-test (for example "FULL BLOOD COUNT" with no analyte) goes under `notEvaluated` and staff handle it by hand.

## Two modes

**Backend mode** (needs `BACKEND_URL`, `AI_SERVICE_EMAIL`, `AI_SERVICE_PASSWORD`). The backend must have an `AI_SERVICE` user.

| Endpoint | Sends to the backend as |
|---|---|
| `POST /ai/v1/submit/intake` | `INTAKE` (needs `patientId` and `facilityId`) |
| `POST /ai/v1/submit/urgency` | `URGENCY` (priority URGENT, HIGH or NORMAL, plus ACTIONABLE, NEEDS_REVIEW or NOT_ACTIONABLE) |
| `POST /ai/v1/submit/message-draft` | `MESSAGE_DRAFT` (channel SMS or EMAIL; English only until a translation is reviewed) |
| `POST /ai/v1/submit/summary` | `CASE_SUMMARY` (citations are the case's audit event IDs) |
| `POST /ai/v1/submit/referral-target` | `REFERRAL_TARGET` (needs `config/facility_ids.json`) |

Mapping: urgent becomes URGENT, "clinician decides" becomes HIGH with NEEDS_REVIEW, routine becomes NORMAL, and a negative or normal result becomes NOT_ACTIONABLE. This is our proposal. Confirm it with the backend owner.

The client has only two methods, `login` and `submit_suggestion`, so it cannot change a status, owner, urgency or closure (R-08, R-15). A test enforces this.

The loop was tested end to end against the v4 backend package: urgency submitted, shown as PENDING, approved by the referring clinician, case priority changed.

**Standalone mode** (no backend needed): `POST /ai/v1/suggestions/{document-read|message-draft|urgency|summary|referral-target}`, `GET /ai/v1/suggestions` (filters `caseId`, `status`, `helper`), `POST /ai/v1/suggestions/{id}/decision` with `approve`, `edit` or `reject`, and `GET /ai/v1/audit`. Approvals follow `config/approver_roles.json`.

Errors always look like `{"success": false, "error": {"code": "ROLE_CANNOT_DECIDE", "message": "...", "details": {}}}`. All keys are camelCase.

## Using a model (optional)

| Setting | What it does |
|---|---|
| `AI_PROVIDER=openai_compatible` | Calls any server with an OpenAI-style `/chat/completions`. For **Qwen 2.5 on Ollama**: `ollama pull qwen2.5:7b`, then keep `LLM_BASE_URL=http://localhost:11434/v1` and `LLM_MODEL=qwen2.5:7b`. Use a smaller size if your laptop is slow. |
| `AI_PROVIDER=anthropic` | Calls Anthropic's API. `pip install -e ".[llm]"` and set `ANTHROPIC_API_KEY`. |

**No real model has been tested.** The plumbing is tested against a stub server and the checks on a model's output are tested (invented fields are dropped, summary lines must cite real events). Small models are weaker, especially at translation. If the model is down or answers badly, the service falls back to the rules (R-04). Hack2skill confirmed that open-source models and platforms other than Azure are allowed.

## Rules this service follows

| Rule | Where |
|---|---|
| R-01 every action stamped, cannot be edited | `app/audit.py`: append-only, hash-chained |
| R-02 AI suggests, a person decides | every suggestion starts pending, carries its sources, and the choice is logged |
| R-03 limits and routing are settings | `config/*.json` |
| R-04 flow works by hand if a helper fails | model fails, then rules fallback, then `status: "unavailable"` with a `manualInstruction` |
| R-05 says it is simulated | `simulated: true` and a notice in every message draft |
| R-08, R-15 AI cannot change or close anything | `app/guard.py` and `app/backend_client.py` |

## Config files

| File | What | Source |
|---|---|---|
| `urgency_criteria.json` | Bands per test, units, reference ranges | Kafilat, draft mock |
| `routing_table.json` | Specialty to facility, backup, urgent recipient, time to accept (placeholder). Colposcopy and Oncology rows were added for this project's cervical-screening demo | Kafilat, draft mock |
| `approver_roles.json` | Who approves each kind | Kafilat, confirmed 12 Nov |
| `facility_ids.json` | Mock routing label to real facility code (`codeAliases`); the IDs are looked up in the backend at submit time | Filled for this project's demo facilities; replace the codes for another deployment |

Where Kafilat's chat said "outside the normal range is urgent" and her sheet gives bands, the code follows the sheet. Decimals between two bands (for example PCV 22.5) are treated as the next band up. Confirm both with her.

## For the front end and back end

- `examples/ai.types.ts` and `examples/ai.mock.ts`: types and real sample responses (type-checked). `examples/examples.json` has plain JSON. The screens should read suggestions from the **backend**, whose own types are the source of truth.
- This backend already has an `AI_SERVICE` demo user (`ai@jusr.local`) and a read-only facility lookup (`GET /api/v1/ai/suggestions/facilities`) for this service.

## Not done

- Backend mode and the model providers have not been run against real production services. The backend loop was verified against the mock backend in `tests/fake_backend.py`.
- Other languages: no reviewed translations exist.
- Real thresholds: Kafilat's values are mock. The users supply the real ones.
- Standalone mode keeps suggestions in memory or a file, not a database.
