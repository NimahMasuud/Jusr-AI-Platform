import { apiRequest } from "./apiClient";
import type { CaseFlag, CaseStatus, Priority } from "./v6.types";

export interface PriorityCase {
  id: string;
  caseId: string;
  patientLabel: string;
  age: number | null;
  screeningType: string | null;
  screeningResult: string | null;
  priority: Priority;
  status: CaseStatus;
  nextStep: string;
  nextActionCode: string | null;
  owner: string;
  dueAt: string | null;
  overdue: boolean;
}

export interface RecentActivityItem {
  id: string;
  description: string;
  actor: string;
  actorRole: string | null;
  eventType: string;
  timestamp: string;
}

export interface DashboardSummary {
  role: string;
  generatedAt: string;
  demoClock?: { active: boolean; offsetMinutes: number };
  stats?: {
    activeCases?: number;
    assignedCases?: number;
    urgentCases?: number;
    overdueCases?: number;
    unassignedCases?: number;
    exceptionCases?: number;
    messageFailedCases?: number;
    notExplainedCases?: number;
    dataMissingCases?: number;
    missingDelayReason?: number;
    awaitingUrgentAcceptance?: number;
    urgentRoutingExceptions?: number;
    closuresAwaitingSignOff?: number;
  };
  byStatus?: Record<string, number>;
  priorityCases?: PriorityCase[];
  careProgress?: { label: string; count: number; percentage: number }[];
  referrals?: Record<string, number>;
  recentActivity?: RecentActivityItem[];
  closureApprovals?: {
    id: string;
    caseNumber: string;
    patientLabel: string;
    closureType: string;
    reason: string;
    requestedBy: string;
    requestedAt: string;
  }[];
  urgentRouting?: { awaitingAcceptance: number; accepted: number };
  facility?: { id: string; name: string; code: string } | null;
  staffAccess?: {
    totalStaff: number;
    activeStaff: number;
    inactiveStaff: number;
    byRole: Record<string, number>;
  };
  connection?: {
    status: string;
    connectorType: string | null;
    lastEventAt: string | null;
  };
}

export function getDashboardSummary() {
  return apiRequest<DashboardSummary>("/api/dashboard/summary");
}

export type { CaseFlag };
