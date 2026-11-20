# Jusr AI backend (v6): notes for frontend integration

**This version is a breaking change from v5.** Statuses, referral statuses, delay codes and several endpoints changed to follow the Developer Guide. Read "What changed" first.

## Basics
Routes are served under `/api` (for example `/api/worklist`) and `/api/v1`. Patient secure links are at `/p/{token}`. Docs: `/docs`; OpenAPI: `/api/v1/openapi.json`.
Sign in with `POST /api/auth/login` (form fields `username`, `password`) and send `Authorization: Bearer <data.accessToken>`. Success: `{ success: true, data, meta }`. Error: `{ success: false, error: { code, message, details }, meta: { requestId } }`; use `error.code` for logic. Demo accounts are in the README.
A case can be addressed by its id, its case number (`caseId`) or its tracker id (`JU-...`) in any `{case_id}` path.

## What changed from v5
- **Case statuses (11):** `NEW, AWAITING_CLASSIFICATION, URGENT_ROUTING, NOTIFYING, AWAITING_ACK, AWAITING_CONFIRMATION, REFERRAL_PENDING, AWAITING_APPOINTMENT, AWAITING_TREATMENT, READY_TO_CLOSE, CLOSED`. The old `OPEN/ASSIGNED/IN_PROGRESS/RESOLVED` are gone.
- **`POST /cases/{id}/transition` is removed.** Status only changes through the named actions below. `GET /cases/transitions` returns the T1 to T17 table (who may do each and what it is refused unless).
- **Flags** are a list on every case: `URGENT, OVERDUE, EXCEPTION, UNASSIGNED, DATA_MISSING, MESSAGE_FAILED, NOT_EXPLAINED`. The worklist has a tab for each.
- **Referral statuses:** `SENT, ACCEPTED, DECLINED, NOT_ACCEPTED_IN_TIME` (was PENDING/REJECTED). A decline needs a `code` (`WRONG_SPECIALTY, NO_CAPACITY, INFORMATION_MISSING, NOT_ELIGIBLE, OTHER`) and a reason. `/reject` still works as an alias.
- **Reason-for-delay codes (7):** `PATIENT_UNREACHABLE, PATIENT_DID_NOT_UNDERSTAND, REFERRAL_DECLINED, NO_SLOT_AVAILABLE, RESULT_OR_DATA_MISSING, PATIENT_MOVED, OTHER` (`GET /cases/delay-reasons`). An overdue case no longer blocks other actions; the code is a follow-up recorded with `POST /cases/{id}/delay-reason`, which clears OVERDUE.
- **Limits are no longer 30/30 minutes.** They are per status and set in `/settings`.
- **Messages and AI approvals:** only coordinators draft, approve and send patient messages. AI intake is approved by a coordinator; urgency by a clinician.
- **The receiving clinician sees a case only after accepting the referral** (or when routed an urgent case or asked in a consultation).
- **Patient "understood" is yes / partly / no** (`{"understood": "PARTLY"}`; true/false still accepted). Partly or no sets NOT_EXPLAINED.

## Case flow and the action that moves it
| Step | Call | Who |
|---|---|---|
| T1/T2 case created | `POST /events` (RESULT_RECEIVED) or `POST /cases` | coordinator, system |
| T2 confirm weak patient match | `POST /cases/{id}/confirm-match` | coordinator |
| T3/T4/T6 classify | `POST /cases/{id}/classify` `{actionable, urgent, specialty, reason, confirmatoryRequired}` | clinicians |
| T5 urgent accepted | `POST /urgent-cases/{id}/accept` | receiving clinician with the matching specialty |
| T7 notify | `POST /messages`, `/messages/{id}/approve`, `/send` (moves on delivery) | coordinator |
| T8 acknowledged and understood | patient link (`/p/{token}/ack`, `/understanding`) or `POST /cases/{id}/assisted-responses` | patient, coordinator |
| T9/T10 refer | `POST /referrals` | referring clinician |
| T11 no further care after confirmatory test | `POST /cases/{id}/confirmatory-outcome` | clinicians |
| T12/T13 accept or decline | `POST /referrals/{id}/accept`, `/decline` | receiving clinician |
| T14 attendance | `POST /cases/{id}/appointments`, `/appointments/{id}/attendance` | receiving side |
| T15 treatment started | `POST /cases/{id}/treatment-start` | receiving clinician |
| T16/T17 close | `GET /cases/{id}/closure-checklist`, `POST /cases/{id}/close`, `/close/sign-off` | named person |

## Other endpoints
- **Worklist:** `GET /worklist?tab=ALL|URGENT|OVERDUE|EXCEPTIONS|UNASSIGNED|MESSAGE_FAILED|NOT_EXPLAINED|DATA_MISSING`. Rows add `trackerId, flags, patientInitials, owner, timeInStatusHours, timeLeftHours`. Urgent first, then longest overdue. Closed cases are excluded unless `includeClosed=true`.
- **Consultations:** `/consultations` (create, list, get, `/accept`, `/reply`, `/escalate`, `/outcome`). Outcome needs an outcome type and a note.
- **Events:** `POST /events`, `/events/batch`, `GET /events/rejected`, `GET /events/export?format=json|csv`.
- **Measures:** `GET /measures?facilityId=&pathway=&since=&until=` returns M1 to M6 with numerator, denominator and value, plus the definitions and an assumed-baseline block.
- **Settings and routing table:** `GET/PUT/DELETE /settings`, `/settings/routing-rules`. **Administration:** `/admin/facilities`, `/admin/staff`.
- **Demo clock:** `GET /demo/clock`, `POST /demo/clock/advance {minutes}`, `POST /demo/clock/reset`. While `active` is true show a banner (also in `/dashboard/summary` as `demoClock`).
- **Patient page** `/p/{token}`: `progress` (four steps), `urgencyText`, `contact`, `language`, plus `POST /p/{token}/reassurance`.

## Status of testing
49 automated tests pass on SQLite. PostgreSQL (audit triggers, scheduler row locks) has not been run. The seeded log, time limits, closure evidence rules and reason codes follow the Developer Guide as read; a few choices were made where the guide is silent (listed in the README under Known gaps and in the hand-over message).
