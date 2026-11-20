import { apiEnvelope, apiRequest } from "./apiClient";
import type {
  ConsultationRecord,
  ConsultationOutcomeType,
  ConsultationState,
  ConsultationType,
  PagedResult,
} from "./v6.types";

export interface ConsultationListParams {
  page?: number;
  pageSize?: number;
  state?: ConsultationState;
  type?: ConsultationType;
  caseId?: string;
  mine?: boolean;
}

export async function listConsultations(
  params: ConsultationListParams = {}
): Promise<PagedResult<ConsultationRecord>> {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "" && value !== false) {
      search.set(key, String(value));
    }
  });
  const query = search.toString();
  const response = await apiEnvelope<ConsultationRecord[]>(
    `/api/consultations${query ? `?${query}` : ""}`
  );
  return {
    items: response.data,
    total: Number(response.meta.total ?? response.data.length),
    page: Number(response.meta.page ?? 1),
    pageSize: Number(response.meta.pageSize ?? response.data.length),
  };
}

export function getConsultation(consultationId: string) {
  return apiRequest<ConsultationRecord>(
    `/api/consultations/${encodeURIComponent(consultationId)}`
  );
}

export function requestConsultation(payload: {
  caseId: string;
  type: ConsultationType;
  question?: string;
  recipientId?: string;
  recipientSpecialty?: string;
  preferredTime?: string;
}) {
  return apiRequest<ConsultationRecord>("/api/consultations", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function acceptConsultation(consultationId: string) {
  return apiRequest<ConsultationRecord>(
    `/api/consultations/${encodeURIComponent(consultationId)}/accept`,
    { method: "POST" }
  );
}

export function replyToConsultation(consultationId: string, text: string) {
  return apiRequest<ConsultationRecord>(
    `/api/consultations/${encodeURIComponent(consultationId)}/reply`,
    { method: "POST", body: JSON.stringify({ text }) }
  );
}

export function escalateConsultation(consultationId: string, reason: string) {
  return apiRequest<ConsultationRecord>(
    `/api/consultations/${encodeURIComponent(consultationId)}/escalate`,
    { method: "POST", body: JSON.stringify({ reason }) }
  );
}

export function recordConsultationOutcome(
  consultationId: string,
  outcomeType: ConsultationOutcomeType,
  note: string
) {
  return apiRequest<ConsultationRecord>(
    `/api/consultations/${encodeURIComponent(consultationId)}/outcome`,
    { method: "POST", body: JSON.stringify({ outcomeType, note }) }
  );
}
