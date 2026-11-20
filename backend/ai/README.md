# AI helper service (Nimah)

Suggests only. A person decides. Everything is simulated.

Five helpers help staff with case intake, urgency, patient messages, case summaries and referral targets.
They never change a case. In **backend mode** (the real setup) the service submits each result to the Jusr AI backend as a
**PENDING suggestion**, and a staff member approves or rejects it there. In **standalone mode** the service keeps the
suggestions itself, so the AI part can be tried without the backend.

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
