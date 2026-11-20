import { apiEnvelope, apiRequest } from "./apiClient";
import type {
  PagedResult,
  Priority,
  RoutingStatus,
  RoutingSummary,
} from "./v6.types";

export interface UrgentCaseItem {
  id: string;
  caseId: string;
  priority: Priority;
  status: string;
  patientLabel: string;
  age: number | null;
  sex: string | null;
  screening: { type: string; outcome: string; displayLabel: string } | null;
  facility: { id: string; name: string };
  nextAction: { code: string | null; label: string | null } | null;
  specialty: string | null;
  routingStatus: RoutingStatus | null;
  routingDueAt: string | null;
  dueAt: string | null;
  routing: RoutingSummary | null;
}

export async function listMyUrgentCases(
  params: { page?: number; pageSize?: number; status?: RoutingStatus } = {}
): Promise<PagedResult<UrgentCaseItem>> {
  const search = new URLSearchParams();
  if (params.page) search.set("page", String(params.page));
  if (params.pageSize) search.set("pageSize", String(params.pageSize));
  if (params.status) search.set("status", params.status);
  const query = search.toString();
  const response = await apiEnvelope<UrgentCaseItem[]>(
    `/api/urgent-cases${query ? `?${query}` : ""}`
  );
  return {
    items: response.data,
    total: Number(response.meta.total ?? response.data.length),
    page: Number(response.meta.page ?? 1),
    pageSize: Number(response.meta.pageSize ?? response.data.length),
  };
}

export function acceptUrgentCase(caseId: string) {
  return apiRequest<UrgentCaseItem>(
    `/api/urgent-cases/${encodeURIComponent(caseId)}/accept`,
    { method: "POST" }
  );
}

export function processDueRouting() {
  return apiRequest<{
    processed: number;
    escalated: number;
    reassigned: number;
    exceptions: number;
  }>("/api/urgent-cases/process-due", { method: "POST" });
}

export function routeUrgentCase(
  caseId: string,
  payload: {
    receivingClinicianId?: string;
    specialty?: string;
    firstLimitMinutes?: number;
    secondLimitMinutes?: number;
  } = {}
) {
  return apiRequest<{
    id: string;
    caseId: string;
    priority: Priority;
    routing: RoutingSummary;
  }>(`/api/cases/${encodeURIComponent(caseId)}/urgent-routing`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getUrgentRouting(caseId: string) {
  return apiRequest<{ id: string; caseId: string; routing: RoutingSummary | null }>(
    `/api/cases/${encodeURIComponent(caseId)}/urgent-routing`
  );
}

export function reassignUrgentCase(
  caseId: string,
  payload: { receivingClinicianId: string; reason: string }
) {
  return apiRequest<{ id: string; caseId: string; routing: RoutingSummary }>(
    `/api/cases/${encodeURIComponent(caseId)}/urgent-routing/reassign`,
    { method: "POST", body: JSON.stringify(payload) }
  );
}
