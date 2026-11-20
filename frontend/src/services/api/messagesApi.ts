import { apiEnvelope, apiRequest } from "./apiClient";
import type { MessageRecord, PagedResult } from "./v6.types";

export async function listMessages(
  params: {
    caseId?: string;
    status?: string;
    page?: number;
    pageSize?: number;
  } = {}
): Promise<PagedResult<MessageRecord>> {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });
  const query = search.toString();
  const response = await apiEnvelope<MessageRecord[]>(
    `/api/messages${query ? `?${query}` : ""}`
  );
  return {
    items: response.data,
    total: Number(response.meta.total ?? response.data.length),
    page: Number(response.meta.page ?? 1),
    pageSize: Number(response.meta.pageSize ?? response.data.length),
  };
}

export function createMessage(payload: {
  caseId: string;
  channel: "SMS" | "EMAIL";
  body: string;
  kind?: string;
  language?: "en" | "ar";
}) {
  return apiRequest<MessageRecord>("/api/messages", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function approveMessage(messageId: string, editedBody?: string) {
  return apiRequest<MessageRecord>(
    `/api/messages/${encodeURIComponent(messageId)}/approve`,
    {
      method: "POST",
      body: JSON.stringify(editedBody ? { editedBody } : {}),
    }
  );
}

export function rejectMessage(messageId: string, reason: string) {
  return apiRequest<MessageRecord>(
    `/api/messages/${encodeURIComponent(messageId)}/reject`,
    { method: "POST", body: JSON.stringify({ reason }) }
  );
}

export function sendMessage(messageId: string) {
  return apiRequest<MessageRecord>(
    `/api/messages/${encodeURIComponent(messageId)}/send`,
    { method: "POST" }
  );
}

export function processDueMessages() {
  return apiRequest<Record<string, number>>("/api/messages/process-due", {
    method: "POST",
  });
}
