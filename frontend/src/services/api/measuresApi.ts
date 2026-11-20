import { apiRequest } from "./apiClient";

export interface Ratio {
  numerator: number;
  denominator: number;
  value: number | null;
}

export interface Distribution {
  n: number;
  medianHours: number | null;
  p90Hours: number | null;
}

export interface MeasuresResponse {
  scope: {
    caseCount: number;
    facilityId: string | null;
    pathway: string | null;
    since: string | null;
    until: string | null;
    calculatedAt: string;
    source: string;
  };
  definitions: Record<string, string>;
  m1: { resultToNotified: Distribution };
  m2: {
    acknowledgedWithinLimit: Ratio;
    understood: Ratio;
  };
  m3: {
    referralAcceptedWithinLimit: Ratio;
    attended: Ratio;
  };
  m4: {
    toConfirmatoryResult: { n: number; medianHours: number | null };
    toConsultationOutcome: { n: number; medianHours: number | null };
    toAttendance: { n: number; medianHours: number | null };
    toTreatmentStart: { n: number; medianHours: number | null };
  };
  m5: {
    openByStatusAndAge: Record<string, Record<string, number>>;
    openTotal: number;
    documentedClosure: Ratio;
    delayReasons: Record<string, number>;
    closedByType: Record<string, number>;
    dropOff: Ratio;
  };
  m6: {
    understood: Ratio;
    meanConfidence: { n: number; mean: number | null };
    meanReassurance: { n: number; mean: number | null };
  };
  baseline: {
    assumed: boolean;
    note: string;
    m1: { medianHours: number | null; p90Hours: number | null };
    m2: { acknowledgedShare: number | null; understoodShare: number | null };
    m3: { referralAcceptedShare: number | null; attendedShare: number | null };
    m4: { toTreatmentStartMedianHours: number | null };
    m5: { dropOffShare: number | null };
  };
}

export function getMeasures(params: {
  facilityId?: string;
  pathway?: string;
  since?: string;
  until?: string;
} = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value) search.set(key, value);
  });
  const query = search.toString();
  return apiRequest<MeasuresResponse>(
    `/api/measures${query ? `?${query}` : ""}`
  );
}
