import { apiEnvelope, apiRequest } from "./apiClient";
import type {
  DeclineCode,
  PagedResult,
  ReferralRecord,
  ReferralStatus,
} from "./v6.types";

export interface ReferralListParams {
  page?: number;
  pageSize?: number;
  status?: ReferralStatus;
  direction?: "incoming" | "outgoing";
  escalated?: boolean;
  caseId?: string;
}

export async function listReferrals(
  params: ReferralListParams = {}
): Promise<PagedResult<ReferralRecord>> {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });
  const query = search.toString();
  const response = await apiEnvelope<ReferralRecord[]>(
    `/api/referrals${query ? `?${query}` : ""}`
  );
  return {
    items: response.data,
    total: Number(response.meta.total ?? response.data.length),
    page: Number(response.meta.page ?? 1),
    pageSize: Number(response.meta.pageSize ?? response.data.length),
  };
}

export function getReferral(referralId: string) {
  return apiRequest<ReferralRecord>(
    `/api/referrals/${encodeURIComponent(referralId)}`
  );
}

export function createReferral(payload: {
  caseId: string;
  receivingFacilityId: string;
  receivingClinicianId?: string;
  reason?: string;
  targetSpecialty?: string;
  packet?: Record<string, unknown>;
}) {
  return apiRequest<ReferralRecord>("/api/referrals", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function assignReferralClinician(
  referralId: string,
  receivingClinicianId: string
) {
  return apiRequest<ReferralRecord>(
    `/api/referrals/${encodeURIComponent(referralId)}/assign`,
    { method: "POST", body: JSON.stringify({ receivingClinicianId }) }
  );
}

export function acceptReferral(referralId: string, note?: string) {
  return apiRequest<ReferralRecord>(
    `/api/referrals/${encodeURIComponent(referralId)}/accept`,
    { method: "POST", body: JSON.stringify({ note: note || undefined }) }
  );
}

export function declineReferral(
  referralId: string,
  payload: { code: DeclineCode; reason?: string }
) {
  return apiRequest<ReferralRecord>(
    `/api/referrals/${encodeURIComponent(referralId)}/decline`,
    { method: "POST", body: JSON.stringify(payload) }
  );
}

export function markReferralNotAccepted(referralId: string) {
  return apiRequest<ReferralRecord>(
    `/api/referrals/${encodeURIComponent(referralId)}/mark-not-accepted`,
    { method: "POST" }
  );
}

export function escalateReferral(referralId: string, reason: string) {
  return apiRequest<ReferralRecord>(
    `/api/referrals/${encodeURIComponent(referralId)}/escalate`,
    { method: "POST", body: JSON.stringify({ reason }) }
  );
}

export function reassignReferral(
  referralId: string,
  receivingFacilityId: string,
  reason: string
) {
  return apiRequest<ReferralRecord>(
    `/api/referrals/${encodeURIComponent(referralId)}/reassign`,
    { method: "POST", body: JSON.stringify({ receivingFacilityId, reason }) }
  );
}

export function recordReferralConsultation(
  referralId: string,
  outcome: string
) {
  return apiRequest<ReferralRecord>(
    `/api/referrals/${encodeURIComponent(referralId)}/consultation`,
    { method: "POST", body: JSON.stringify({ outcome }) }
  );
}
