import { apiRequest } from "./apiClient";

export interface SettingOverride {
  key: string;
  scope: string;
  value: unknown;
  changedById: string | null;
  changedAt: string | null;
}

export interface SettingsResponse {
  defaults: Record<string, unknown>;
  overrides: SettingOverride[];
}

export interface RoutingRule {
  id: string;
  pathway: string;
  resultCategory: string;
  suggestedUrgency: string | null;
  confirmatoryRequired: boolean;
  specialty: string | null;
  primaryPool: string | null;
  backupPool: string | null;
  timeToAcceptMinutes: number | null;
  timeToAppointmentDays: number | null;
  notes: string | null;
  changedAt: string | null;
}

export type RoutingRuleInput = Omit<RoutingRule, "id" | "changedAt">;

export function getSettings() {
  return apiRequest<SettingsResponse>("/api/settings");
}

export function getEffectiveSetting(
  key: string,
  params: { facilityId?: string; specialty?: string } = {}
) {
  const search = new URLSearchParams({ key });
  if (params.facilityId) search.set("facilityId", params.facilityId);
  if (params.specialty) search.set("specialty", params.specialty);
  return apiRequest<{ key: string; value: unknown }>(
    `/api/settings/effective?${search.toString()}`
  );
}

export function putSetting(key: string, scope: string, value: unknown) {
  return apiRequest<SettingOverride>(
    `/api/settings/${encodeURIComponent(key)}`,
    { method: "PUT", body: JSON.stringify({ scope, value }) }
  );
}

export function deleteSetting(key: string, scope: string) {
  return apiRequest<{ key: string; scope: string; removed: boolean }>(
    `/api/settings/${encodeURIComponent(key)}?scope=${encodeURIComponent(
      scope
    )}`,
    { method: "DELETE" }
  );
}

export interface SpecialtyBackupRecord {
  specialty: string;
  clinicianId: string;
  clinicianName: string | null;
  facilityId: string | null;
  changedById: string | null;
  changedAt: string | null;
}

export function listSpecialtyBackups() {
  return apiRequest<SpecialtyBackupRecord[]>("/api/settings/specialty-backups");
}

export function putSpecialtyBackup(specialty: string, clinicianId: string) {
  return apiRequest<SpecialtyBackupRecord>(
    `/api/settings/specialty-backups/${encodeURIComponent(specialty)}`,
    { method: "PUT", body: JSON.stringify({ clinicianId }) }
  );
}

export function deleteSpecialtyBackup(specialty: string) {
  return apiRequest<{ specialty: string; removed: boolean }>(
    `/api/settings/specialty-backups/${encodeURIComponent(specialty)}`,
    { method: "DELETE" }
  );
}

export interface SpecialtyCatalogEntry {
  name: string;
  label: string;
  scope: string;
  editable: boolean;
}

export function listSpecialtyCatalog() {
  return apiRequest<SpecialtyCatalogEntry[]>("/api/settings/specialties");
}

export function createSpecialtyEntry(payload: { name: string; label?: string }) {
  return apiRequest<SpecialtyCatalogEntry>("/api/settings/specialties", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateSpecialtyEntry(
  name: string,
  payload: { name: string; label?: string }
) {
  return apiRequest<SpecialtyCatalogEntry>(
    `/api/settings/specialties/${encodeURIComponent(name)}`,
    { method: "PUT", body: JSON.stringify(payload) }
  );
}

export function deleteSpecialtyEntry(name: string) {
  return apiRequest<{ name: string; removed: boolean }>(
    `/api/settings/specialties/${encodeURIComponent(name)}`,
    { method: "DELETE" }
  );
}

export function listRoutingRules() {
  return apiRequest<RoutingRule[]>("/api/settings/routing-rules");
}

export function createRoutingRule(payload: RoutingRuleInput) {
  return apiRequest<RoutingRule>("/api/settings/routing-rules", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateRoutingRule(id: string, payload: RoutingRuleInput) {
  return apiRequest<RoutingRule>(
    `/api/settings/routing-rules/${encodeURIComponent(id)}`,
    { method: "PUT", body: JSON.stringify(payload) }
  );
}

export function deleteRoutingRule(id: string) {
  return apiRequest<{ id: string; removed: boolean }>(
    `/api/settings/routing-rules/${encodeURIComponent(id)}`,
    { method: "DELETE" }
  );
}
