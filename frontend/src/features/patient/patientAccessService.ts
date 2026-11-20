import { apiRequest } from "../../services/api/apiClient";
import type {
  GeneratedPatientLink,
  PatientLinkRecord,
  PatientPortalContext,
  PatientResponseRecord,
  UnderstandingLevel,
} from "../../services/api/v6.types";

export type {
  GeneratedPatientLink,
  PatientLinkRecord,
  PatientPortalContext,
  PatientResponseRecord,
};

export interface AssistedResponsePayload {
  acknowledged: boolean;
  understood_level: UnderstandingLevel;
  confidence: number;
  explanationStatus: "EXPLAINED" | "NOT_EXPLAINED";
  callbackRequested: boolean;
  note?: string;
}

export interface PatientVerificationResult {
  verificationRequired: boolean;
  verified: boolean;
  sessionToken: string | null;
  expiresInMinutes?: number;
}

const publicRequest = <T>(path: string, options: RequestInit = {}) =>
  apiRequest<T>(path, { ...options, authenticated: false });

const patientRequest = <T>(
  token: string,
  path: string,
  sessionToken: string | null,
  options: RequestInit = {}
) => {
  const headers = new Headers(options.headers);
  if (sessionToken) headers.set("X-Patient-Session", sessionToken);
  return publicRequest<T>(`/api/p/${encodeURIComponent(token)}${path}`, {
    ...options,
    headers,
  });
};

export async function generatePatientLink(
  caseId: string
): Promise<GeneratedPatientLink> {
  return apiRequest<GeneratedPatientLink>(
    `/api/cases/${encodeURIComponent(caseId)}/links`,
    { method: "POST" }
  );
}

export async function getPatientLinks(
  caseId: string
): Promise<PatientLinkRecord[]> {
  return apiRequest<PatientLinkRecord[]>(
    `/api/cases/${encodeURIComponent(caseId)}/links`
  );
}

export interface PatientPreviewLink {
  token: string;
  path: string;
  url: string;
  expiresAt: string;
  note: string;
}

export async function createPatientPreviewLink(
  caseId: string
): Promise<PatientPreviewLink> {
  return apiRequest<PatientPreviewLink>(
    `/api/cases/${encodeURIComponent(caseId)}/preview-link`,
    { method: "POST" }
  );
}

export async function getPatientResponses(
  caseId: string
): Promise<PatientResponseRecord[]> {
  return apiRequest<PatientResponseRecord[]>(
    `/api/cases/${encodeURIComponent(caseId)}/patient-responses`
  );
}

export async function recordAssistedPatientResponse(
  caseId: string,
  payload: AssistedResponsePayload
) {
  return apiRequest<{
    submissionId: string;
    source: "STAFF_ASSISTED";
    submittedByPatient: false;
    recordedBy: { id: string; displayName: string; role: string };
    recordedAt: string;
    responses: PatientResponseRecord[];
  }>(`/api/cases/${encodeURIComponent(caseId)}/assisted-responses`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function verifyPatientLink(
  token: string,
  birthYear: number
): Promise<PatientVerificationResult> {
  return publicRequest<PatientVerificationResult>(
    `/api/p/${encodeURIComponent(token)}/verify`,
    {
      method: "POST",
      body: JSON.stringify({ birthYear }),
    }
  );
}

export async function getPatientPortalContext(
  token: string,
  sessionToken: string | null
): Promise<PatientPortalContext> {
  return patientRequest<PatientPortalContext>(token, "", sessionToken);
}

export async function acknowledgePatientInformation(
  token: string,
  sessionToken: string | null
) {
  return patientRequest(token, "/ack", sessionToken, { method: "POST" });
}

export async function submitPatientUnderstanding(
  token: string,
  sessionToken: string | null,
  level: UnderstandingLevel
) {
  return patientRequest(token, "/understanding", sessionToken, {
    method: "POST",
    body: JSON.stringify({ understood: level }),
  });
}

export async function submitPatientConfidence(
  token: string,
  sessionToken: string | null,
  rating: number
) {
  return patientRequest(token, "/confidence", sessionToken, {
    method: "POST",
    body: JSON.stringify({ rating }),
  });
}

export async function reportPatientNotExplained(
  token: string,
  sessionToken: string | null
) {
  return patientRequest(token, "/not-explained", sessionToken, {
    method: "POST",
  });
}

export async function requestPatientCallback(
  token: string,
  sessionToken: string | null,
  payload?: { preferredTime?: string; note?: string }
) {
  return patientRequest(token, "/callback", sessionToken, {
    method: "POST",
    ...(payload ? { body: JSON.stringify(payload) } : {}),
  });
}

export async function submitPatientReassurance(
  token: string,
  sessionToken: string | null,
  rating: number
) {
  return patientRequest(token, "/reassurance", sessionToken, {
    method: "POST",
    body: JSON.stringify({ rating }),
  });
}
