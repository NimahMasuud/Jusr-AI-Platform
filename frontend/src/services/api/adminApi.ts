import { apiRequest } from "./apiClient";
import type { FacilityRecord, PersonRef } from "./v6.types";

export interface StaffMember extends PersonRef {
  email: string;
  role: string;
  facilityId: string | null;
  specialty: string | null;
  authorisedToClose: boolean;
  isActive: boolean;
}

export function listFacilities() {
  return apiRequest<FacilityRecord[]>("/api/admin/facilities");
}

export function createFacility(payload: {
  name: string;
  type?: string;
  timeZone?: string;
  workingDays?: string[];
  connectorType?: "FEED_SIMULATOR" | "CSV";
}) {
  return apiRequest<FacilityRecord>("/api/admin/facilities", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateFacility(
  facilityId: string,
  payload: Partial<{
    name: string;
    type: string | null;
    timeZone: string;
    workingDays: string[] | null;
    connectorType: "FEED_SIMULATOR" | "CSV";
  }>
) {
  return apiRequest<FacilityRecord>(
    `/api/admin/facilities/${encodeURIComponent(facilityId)}`,
    { method: "PATCH", body: JSON.stringify(payload) }
  );
}

export function deleteFacility(facilityId: string) {
  return apiRequest<{ id: string; removed: boolean }>(
    `/api/admin/facilities/${encodeURIComponent(facilityId)}`,
    { method: "DELETE" }
  );
}

export function listStaff(params: {
  facilityId?: string;
  role?: string;
  specialty?: string;
} = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value) search.set(key, value);
  });
  const query = search.toString();
  return apiRequest<StaffMember[]>(`/api/admin/staff${query ? `?${query}` : ""}`);
}

export function createStaff(payload: {
  email: string;
  displayName: string;
  password: string;
  role: string;
  facilityId?: string;
  specialty?: string;
  authorisedToClose?: boolean;
}) {
  return apiRequest<StaffMember>("/api/admin/staff", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateStaff(
  userId: string,
  payload: Partial<{
    email: string;
    displayName: string;
    facilityId: string;
    role: string;
    specialty: string | null;
    authorisedToClose: boolean;
    isActive: boolean;
  }>
) {
  return apiRequest<StaffMember>(
    `/api/admin/staff/${encodeURIComponent(userId)}`,
    { method: "PATCH", body: JSON.stringify(payload) }
  );
}

export function deleteStaff(userId: string) {
  return apiRequest<{ id: string; removed: boolean; deactivated: boolean }>(
    `/api/admin/staff/${encodeURIComponent(userId)}`,
    { method: "DELETE" }
  );
}

export function importStaffCsv(csv: string) {
  return apiRequest<{
    created: StaffMember[];
    rejected: Array<{ row: number; email: string | null; message: string }>;
    counts: { created: number; rejected: number };
  }>("/api/admin/staff/csv", {
    method: "POST",
    headers: { "Content-Type": "text/csv" },
    body: csv,
  });
}

export function listClosureAuthorisedStaff() {
  return apiRequest<PersonRef[]>("/api/admin/closure-authorised-staff");
}

export function listAssignableStaff(facilityId?: string) {
  return listStaff({ facilityId });
}
