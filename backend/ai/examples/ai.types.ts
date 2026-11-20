// Types for the Jusr AI helper service. Every key is camelCase.
// The service only SUGGESTS. A person approves, edits or rejects (R-02).
// The backend will wrap these in its own { success, data, meta } envelope.

export type HelperType =
  | "document_read"
  | "message_draft"
  | "urgency"
  | "summary"
  | "referral_target";

export type SuggestionStatus = "pending" | "accepted" | "edited" | "rejected";
export type HelperResponseStatus = "suggested" | "no_suggestion" | "unavailable";
export type Completeness = "complete" | "partial"; // set by rules, not guessed by the AI

export interface SuggestionSource {
  kind: "document" | "event" | "config" | "input";
  ref: string; // document id, event id, rule id, or input name
  quote: string | null; // exact text from the document, when there is one
}

// ---- Content, one shape per helper ----
export interface DocumentReadContent {
  fields: Partial<
    Record<
      | "patientRef"
      | "facility"
      | "resultDate"
      | "testName"
      | "resultValue"
      | "orderingClinician"
      | "specialtyNeeded",
      string
    >
  >;
}

export interface MessageDraftContent {
  language: string;
  text: string;
  requestedLanguage: string;
  needsTranslationReview: boolean; // true = a person must check the language before sending
}

export type UrgencySuggestion = "urgent" | "clinician_decides" | "routine" | "no_suggestion";

export interface UrgencyContent {
  suggestedUrgency: UrgencySuggestion; // no_suggestion = not actionable (for example a negative result)
  reason: string;
  matchedRules: {
    ruleId: string;
    test: string;
    value: number | string;
    suggestion: UrgencySuggestion;
    reason: string;
    specialty: string;
    lookFor: string;
    confidential?: boolean;
  }[];
  notEvaluated: { test: string; why: string }[]; // never guessed: shown to staff as a data-quality task
  specialties: string[];
  lookFor: string[]; // prompts for the clinician (pregnancy, symptoms ...)
  confidential: boolean; // true for HIV: extra confidentiality in messages
}

export interface SummaryContent {
  bullets: { text: string; sources: string[] }[]; // sources are event IDs
}

export interface FacilityTarget { facilityCode: string; text: string }

export interface ReferralTargetContent {
  options: {
    specialty: string;
    service: string;
    primary: FacilityTarget;
    backup: FacilityTarget;
    urgentRecipient: string;
    urgentRole: string;
    timeToAcceptUrgent: string; // a placeholder from the mock list
  }[];
  reason: string;
}

export type SuggestionContent =
  | DocumentReadContent
  | MessageDraftContent
  | UrgencyContent
  | SummaryContent
  | ReferralTargetContent;

export interface Suggestion<C = SuggestionContent> {
  id: string;
  caseId: string;
  helper: HelperType;
  content: C; // the original. Never overwritten.
  sources: SuggestionSource[];
  completeness: Completeness;
  provider: string; // "rules", "anthropic", or "rules (fallback)"
  notices: string[]; // show these next to the suggestion
  status: SuggestionStatus;
  requestedBy: string; // staff ID
  createdAt: string;
  decidedBy: string | null;
  decidedRole: string | null;
  decidedAt: string | null;
  decisionNote: string | null;
  editedContent: Partial<C> | Record<string, unknown> | null; // what the person changed it to
  simulated: boolean; // show a "simulated" label when true (R-05)
}

export interface HelperResponse<C = SuggestionContent> {
  status: HelperResponseStatus;
  message: string; // plain language, safe to show on screen
  suggestion: Suggestion<C> | null; // null when status is no_suggestion or unavailable
  manualInstruction: string | null; // what staff do by hand when there is no suggestion
}

// ---- Requests ----
export interface DocumentReadRequest {
  caseId: string;
  documentId: string;
  documentText: string;
  patientId?: string; // backend patient ID, needed only to submit an intake suggestion
  facilityId?: string;
}
export interface MessageDraftRequest {
  caseId: string;
  language?: string;
  channel?: "SMS" | "EMAIL"; // used when submitting to the backend
  urgency: "routine" | "urgent";
  nextStep: string;
  contact: string;
  plainResultSummary?: string; // only text a clinician has approved
}
export interface UrgencyResultItem {
  test: string; // the test name as listed, for example "PCV - HAEM"
  value?: number; // numeric result
  text?: string; // qualitative result, for example "Negative"
  unit?: string;
  upperLimit?: number; // the lab's own upper limit, needed for ALT and AST
}
export interface UrgencyRequest { caseId: string; results: UrgencyResultItem[] }
export interface SummaryRequest {
  caseId: string;
  events: { eventId: string; timestamp: string; type: string; actorStaffId?: string | null; text: string }[];
}
export interface ReferralTargetRequest { caseId: string; specialtyNeeded: string }

export interface DecisionRequest {
  decision: "approve" | "edit" | "reject";
  editedContent?: Record<string, unknown>; // required when decision is "edit"
  note?: string;
}

export interface ApiErrorBody {
  success: false;
  error: { code: string; message: string; details: Record<string, unknown> };
}

// ---- Backend mode: POST /ai/v1/submit/{intake|urgency|message-draft|summary|referral-target} ----
// The helper runs, then the result is sent to the backend as a PENDING suggestion.
// Staff approve or reject it in the BACKEND (POST /api/v1/ai/suggestions/{id}/approve or /reject).
// The screens should read suggestions from the backend. The backend's own types are the source of truth.
export interface SubmitResponse {
  status: "submitted" | "no_suggestion" | "unavailable";
  message: string;
  backendSuggestion: {
    id: string;
    kind: "INTAKE" | "URGENCY" | "MESSAGE_DRAFT" | "CASE_SUMMARY" | "REFERRAL_TARGET";
    status: "PENDING";
    caseId: string | null;
    payload: Record<string, unknown>;
    model: string | null;
    requiresStaffApproval: boolean;
  } | null;
  preview: Record<string, unknown> | null;
  notices: string[];
  manualInstruction: string | null;
}
