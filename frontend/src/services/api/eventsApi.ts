import { apiEnvelope, apiRequest } from "./apiClient";

export interface OutboundEvent {
  eventId: string;
  type:
    | "RESULT_RECEIVED"
    | "CONFIRMATORY_RESULT_RECEIVED"
    | "APPOINTMENT_UPDATE"
    | "TREATMENT_START_RECORDED"
    | "PATIENT_TRANSFERRED"
    | "FEED_MISSING"
    | "TEST_EVENT";
  facilityId: string;
  payload?: Record<string, unknown>;
}

export interface RejectedEvent {
  id: string;
  eventId: string;
  type: string;
  facilityId: string | null;
  errorCode: string;
  message: string;
  payload: Record<string, unknown> | null;
  receivedAt: string;
}

export interface RejectedSummary {
  total: number;
  byErrorCode: Record<string, number>;
}

export interface RejectedResult {
  items: RejectedEvent[];
  total: number;
  byErrorCode?: Record<string, number>;
}

export function submitEvent(event: OutboundEvent) {
  return apiRequest<Record<string, unknown>>("/api/events", {
    method: "POST",
    body: JSON.stringify(event),
  });
}

export function importEventsCsv(csv: string) {
  return apiRequest<{
    results: Record<string, unknown>[];
    counts: Record<string, number>;
  }>("/api/events/csv", {
    method: "POST",
    headers: { "Content-Type": "text/csv" },
    body: csv,
  });
}

export function getEventsCsvTemplate() {
  return apiRequest<{ csv: string; facility: string; patient: string }>(
    "/api/events/csv/template"
  );
}

export async function getRejectedEvents(params: {
  facilityId?: string;
  page?: number;
  pageSize?: number;
} = {}): Promise<RejectedResult> {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });
  const query = search.toString();
  const response = await apiEnvelope<RejectedEvent[] | RejectedSummary>(
    `/api/events/rejected${query ? `?${query}` : ""}`
  );
  if (Array.isArray(response.data)) {
    return {
      items: response.data,
      total: Number(response.meta.total ?? response.data.length),
    };
  }
  return {
    items: [],
    total: response.data.total,
    byErrorCode: response.data.byErrorCode,
  };
}

export function eventLogExportUrl(format: "csv" | "json" = "csv") {
  return `/api/events/export?format=${format}`;
}
