import { apiRequest } from "./apiClient";
import type {
  AppointmentRecord,
  CaseDetail,
  CaseEvent,
  ClosureChecklist,
  ClosureType,
  ContactAttemptRecord,
  ContactRoute,
  DelayReasonCode,
  Priority,
  ResultRecord,
  SuggestedRouting,
  TreatmentStartRecord,
  WorklistQuery,
  WorklistResponse,
} from "./v6.types";

function queryString(params: Record<string, unknown>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    search.set(key, String(value));
  });
  const query = search.toString();
  return query ? `?${query}` : "";
}

export function getWorklist(params: WorklistQuery = {}) {
  return apiRequest<WorklistResponse>(
    `/api/worklist${queryString(params as Record<string, unknown>)}`
  );
}

export function createCase(payload: {
  patientId: string;
  caseId: string;
  facilityId?: string;
  priority?: Priority;
  nextActionCode?: string;
  nextActionLabel?: string;
  requiredSpecialty?: string;
  confirmatoryRequired?: boolean;
}) {
  return apiRequest<{ id: string; caseId: string; status: string }>(
    "/api/cases",
    { method: "POST", body: JSON.stringify(payload) }
  );
}

export function getCase(caseId: string) {
  return apiRequest<CaseDetail>(
    `/api/cases/${encodeURIComponent(caseId)}`
  );
}

export function getCaseTimeline(caseId: string) {
  return apiRequest<CaseEvent[]>(
    `/api/cases/${encodeURIComponent(caseId)}/events`
  );
}

export function getSuggestedRouting(caseId: string) {
  return apiRequest<SuggestedRouting | null>(
    `/api/cases/${encodeURIComponent(caseId)}/suggested-routing`
  );
}

export function confirmPatientMatch(caseId: string, patientId?: string) {
  return apiRequest<CaseDetail>(
    `/api/cases/${encodeURIComponent(caseId)}/confirm-match`,
    { method: "POST", body: JSON.stringify(patientId ? { patientId } : {}) }
  );
}

export function classifyCase(
  caseId: string,
  payload: {
    actionable: boolean;
    urgent?: boolean;
    priority?: Priority;
    specialty?: string;
    reason?: string;
    confirmatoryRequired?: boolean;
  }
) {
  return apiRequest<CaseDetail>(
    `/api/cases/${encodeURIComponent(caseId)}/classify`,
    { method: "POST", body: JSON.stringify(payload) }
  );
}

export function recordConfirmatoryOutcome(
  caseId: string,
  outcome: string,
  reason: string
) {
  return apiRequest<CaseDetail>(
    `/api/cases/${encodeURIComponent(caseId)}/confirmatory-outcome`,
    { method: "POST", body: JSON.stringify({ outcome, reason }) }
  );
}

export function recordDelayReason(
  caseId: string,
  code: DelayReasonCode,
  note?: string
) {
  return apiRequest<{ caseId: string; flags: string[] }>(
    `/api/cases/${encodeURIComponent(caseId)}/delay-reason`,
    { method: "POST", body: JSON.stringify({ code, note: note || undefined }) }
  );
}

export function recordExplained(caseId: string, note: string) {
  return apiRequest<{ caseId: string; flags: string[] }>(
    `/api/cases/${encodeURIComponent(caseId)}/explained`,
    { method: "POST", body: JSON.stringify({ note }) }
  );
}

export function confirmContact(
  caseId: string,
  route: ContactRoute,
  note?: string
) {
  return apiRequest<{ caseId: string; flags: string[] }>(
    `/api/cases/${encodeURIComponent(caseId)}/contact-confirmed`,
    { method: "POST", body: JSON.stringify({ route, note: note || undefined }) }
  );
}

export function assignCase(caseId: string, ownerId: string) {
  return apiRequest<{ caseId: string; ownerId: string; flags: string[] }>(
    `/api/cases/${encodeURIComponent(caseId)}/assign`,
    { method: "POST", body: JSON.stringify({ ownerId }) }
  );
}

export function transferCase(
  caseId: string,
  newFacilityId: string,
  reason: string,
  newOwnerId?: string
) {
  return apiRequest<{ caseId: string; trackerId: string; facilityId: string }>(
    `/api/cases/${encodeURIComponent(caseId)}/transfer`,
    {
      method: "POST",
      body: JSON.stringify({ newFacilityId, reason, newOwnerId }),
    }
  );
}

export function startLinkedCase(caseId: string, caseNumber: string, reason: string) {
  return apiRequest<CaseDetail>(
    `/api/cases/${encodeURIComponent(caseId)}/linked-case`,
    { method: "POST", body: JSON.stringify({ caseId: caseNumber, reason }) }
  );
}

export function listResults(caseId: string) {
  return apiRequest<ResultRecord[]>(
    `/api/cases/${encodeURIComponent(caseId)}/results`
  );
}

export function addResult(
  caseId: string,
  payload: {
    kind: "ORIGINAL" | "CONFIRMATORY";
    testCode: string;
    testName?: string;
    value: string;
    abnormal?: boolean;
  }
) {
  return apiRequest<ResultRecord>(
    `/api/cases/${encodeURIComponent(caseId)}/results`,
    { method: "POST", body: JSON.stringify(payload) }
  );
}

export function listAppointments(caseId: string) {
  return apiRequest<AppointmentRecord[]>(
    `/api/cases/${encodeURIComponent(caseId)}/appointments`
  );
}

export function bookAppointment(caseId: string, scheduledAt: string) {
  return apiRequest<AppointmentRecord>(
    `/api/cases/${encodeURIComponent(caseId)}/appointments`,
    { method: "POST", body: JSON.stringify({ scheduledAt }) }
  );
}

export function recordAttendance(
  caseId: string,
  appointmentId: string,
  attendance: "ATTENDED" | "MISSED",
  reasonCode?: DelayReasonCode,
  note?: string
) {
  return apiRequest<{ appointment: AppointmentRecord; caseStatus: string }>(
    `/api/cases/${encodeURIComponent(
      caseId
    )}/appointments/${encodeURIComponent(appointmentId)}/attendance`,
    {
      method: "POST",
      body: JSON.stringify({ attendance, reasonCode, note: note || undefined }),
    }
  );
}

export function listTreatmentStarts(caseId: string) {
  return apiRequest<TreatmentStartRecord[]>(
    `/api/cases/${encodeURIComponent(caseId)}/treatment-start`
  );
}

export function recordTreatmentStart(
  caseId: string,
  payload: {
    kind: "TREATMENT" | "MONITORING";
    startDate: string;
    note?: string;
    attachmentRef?: string;
  }
) {
  return apiRequest<{ treatmentStart: TreatmentStartRecord; caseStatus: string }>(
    `/api/cases/${encodeURIComponent(caseId)}/treatment-start`,
    { method: "POST", body: JSON.stringify(payload) }
  );
}

export function listContactAttempts(caseId: string) {
  return apiRequest<ContactAttemptRecord[]>(
    `/api/cases/${encodeURIComponent(caseId)}/contact-attempts`
  );
}

export function addContactAttempt(
  caseId: string,
  payload: {
    route: ContactRoute;
    outcome: "REACHED" | "NOT_REACHED";
    note?: string;
  }
) {
  return apiRequest<ContactAttemptRecord>(
    `/api/cases/${encodeURIComponent(caseId)}/contact-attempts`,
    { method: "POST", body: JSON.stringify(payload) }
  );
}

export function getClosureChecklist(
  caseId: string,
  closureType: ClosureType,
  fields: { reason?: string; decision?: string; evidence?: string } = {}
) {
  return apiRequest<ClosureChecklist>(
    `/api/cases/${encodeURIComponent(
      caseId
    )}/closure-checklist${queryString({ closureType, ...fields })}`
  );
}

export function closeCase(
  caseId: string,
  payload: {
    closureType: ClosureType;
    reason: string;
    decision?: string;
    evidence?: string;
    secondApproverId?: string;
  }
) {
  return apiRequest<{
    caseId: string;
    status: string;
    closureType?: string;
    closedAt?: string;
    pendingSignOff: boolean;
    message?: string;
  }>(`/api/cases/${encodeURIComponent(caseId)}/close`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function signOffClosure(caseId: string) {
  return apiRequest<{ caseId: string; status: string; pendingSignOff: boolean }>(
    `/api/cases/${encodeURIComponent(caseId)}/close/sign-off`,
    { method: "POST" }
  );
}

export function getDelayReasonCodes() {
  return apiRequest<DelayReasonCode[]>("/api/cases/delay-reasons");
}

export function getTransitionTable() {
  return apiRequest<{
    statuses: string[];
    transitions: { id: string; from: string[]; to: string; who: string[]; refusedUnless: string }[];
  }>("/api/cases/transitions");
}
