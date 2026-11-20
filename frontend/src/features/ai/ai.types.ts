
import type { AISuggestionRecord } from "../../services/api/v6.types";

export type AIHelperType =
  | "document_read"
  | "message_draft"
  | "urgency"
  | "summary"
  | "referral_target";

export type BackendAIKind =
  | "INTAKE"
  | "URGENCY"
  | "MESSAGE_DRAFT"
  | "CASE_SUMMARY"
  | "REFERRAL_TARGET";

export type SuggestionStatus = "PENDING" | "APPROVED" | "REJECTED";

export type SuggestionDecision = "accept" | "edit" | "reject";

export type SuggestionSourceType =
  | "CASE"
  | "SCREENING"
  | "AUDIT_EVENT"
  | "REFERRAL"
  | "CONSULTATION"
  | "PATIENT_RESPONSE";

export interface SuggestionCitation {
  sourceType: SuggestionSourceType;
  sourceId: string;
  excerpt?: string;
}

export interface AIBaseRequest {
  caseId?: string;
  model?: string;
  confidence?: number;
}

export interface IntakePayload {
  patientId: string;
  caseId: string;
  facilityId?: string;
  priority?: "LOW" | "NORMAL" | "HIGH" | "URGENT";
  nextActionCode?: string;
  nextActionLabel?: string;
  rationale?: string;
}

export interface UrgencyPayload {
  priority: "LOW" | "NORMAL" | "HIGH" | "URGENT";
  actionability: "ACTIONABLE" | "NEEDS_REVIEW" | "NOT_ACTIONABLE";
  rationale: string;
}

export interface MessageDraftPayload {
  channel: "SMS" | "EMAIL";
  body: string;
  purpose?: string;
  language?: "en" | "ar";
  templateVersion?: string;
}

export interface CaseSummaryPayload {
  summary: string;
  citations: SuggestionCitation[];
}

export interface ReferralAlternative {
  receivingFacilityId: string;
  rationale: string;
}

export interface ReferralTargetPayload {
  receivingFacilityId: string;
  receivingClinicianId?: string;
  rationale: string;
  alternatives?: ReferralAlternative[];
}

export interface AISuggestionCreateRequest extends AIBaseRequest {
  kind: BackendAIKind;
  payload:
    | IntakePayload
    | UrgencyPayload
    | MessageDraftPayload
    | CaseSummaryPayload
    | ReferralTargetPayload;
}

export type AISuggestion = AISuggestionRecord;

export interface AIApproveRequest {
  editedBody?: string;
  note?: string;
}

export interface AIRejectRequest {
  reason: string;
}

export interface AIDocumentReadRequest {
  caseId: string;
  documentId?: string;
  documentText: string;
  patientId?: string;
  facilityId?: string;
}

export interface AIDocumentReadResult {
  extractedText: string;
  patientMatchCandidates: Array<{
    patientId: string;
    displayName: string;
    matchReason: string;
  }>;
  extractedFields: Record<string, string | number | null>;
  notices: string[];
  simulated: boolean;
}

export interface AIHelperResult<T = unknown> {
  status: "suggested" | "no_suggestion" | "unavailable";
  helper: AIHelperType;
  content?: T;
  sources: SuggestionCitation[];
  notices: string[];
  simulated: true;
}

export interface AIHelperDecision {
  suggestionId: string;
  decision: SuggestionDecision;
  decisionNote?: string;
  editedContent?: string;
}

export interface AIMessageDraftRequest {
  caseId: string;
  language: "en" | "ar";
  channel: "SMS" | "EMAIL";
  urgency: "routine" | "urgent";
  nextStep: string;
  contact: string;
}

export type AIMessageDraftResult = AISuggestionRecord & {
  payload: MessageDraftPayload;
};
