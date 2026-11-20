
import { apiEnvelope, apiRequest } from "../../services/api/apiClient";
import type {
  AISuggestionRecord,
  PagedResult,
} from "../../services/api/v6.types";
import type {
  AIApproveRequest,
  AIDocumentReadRequest,
  AIDocumentReadResult,
  AIRejectRequest,
  AIMessageDraftRequest,
  AIMessageDraftResult,
  AISuggestionCreateRequest,
  BackendAIKind,
  CaseSummaryPayload,
  SuggestionStatus,
} from "./ai.types";

const AI_BASE = "/api/ai/suggestions";

export interface AIListFilters {
  page?: number;
  pageSize?: number;
  kind?: BackendAIKind;
  status?: SuggestionStatus;
  caseId?: string;
}

export interface ApprovedCaseSummary extends AISuggestionRecord {
  approvedBy: string | null;
}

export const aiService = {
  async listSuggestions(
    filters: AIListFilters = {}
  ): Promise<PagedResult<AISuggestionRecord>> {
    const params = new URLSearchParams();

    if (filters.page !== undefined) params.set("page", String(filters.page));
    if (filters.pageSize !== undefined)
      params.set("pageSize", String(filters.pageSize));
    if (filters.kind) params.set("kind", filters.kind);
    if (filters.status) params.set("status", filters.status);
    if (filters.caseId) params.set("caseId", filters.caseId);

    const query = params.toString();
    const response = await apiEnvelope<AISuggestionRecord[]>(
      `${AI_BASE}${query ? `?${query}` : ""}`
    );
    return {
      items: response.data,
      total: Number(response.meta.total ?? response.data.length),
      page: Number(response.meta.page ?? 1),
      pageSize: Number(response.meta.pageSize ?? response.data.length),
    };
  },

  // Only the AI service account may submit suggestions.
  async createSuggestion(
    request: AISuggestionCreateRequest
  ): Promise<AISuggestionRecord> {
    return apiRequest<AISuggestionRecord>(AI_BASE, {
      method: "POST",
      body: JSON.stringify(request),
    });
  },

  // Deterministic rules-based generation (demo): staff trigger, staff approve.
  async generateSuggestions(
    request: { caseId?: string; kinds?: BackendAIKind[] } = {}
  ): Promise<{ items: AISuggestionRecord[]; cases: number }> {
    const response = await apiEnvelope<AISuggestionRecord[]>(
      `${AI_BASE}/generate`,
      {
        method: "POST",
        body: JSON.stringify(request),
      }
    );
    return {
      items: response.data,
      cases: Number(response.meta.cases ?? 0),
    };
  },

  async getSuggestion(id: string): Promise<AISuggestionRecord> {
    return apiRequest<AISuggestionRecord>(
      `${AI_BASE}/${encodeURIComponent(id)}`
    );
  },

  async approveSuggestion(
    id: string,
    request: AIApproveRequest = {}
  ): Promise<AISuggestionRecord> {
    return apiRequest<AISuggestionRecord>(
      `${AI_BASE}/${encodeURIComponent(id)}/approve`,
      {
        method: "POST",
        body: JSON.stringify(request),
      }
    );
  },

  async rejectSuggestion(
    id: string,
    request: AIRejectRequest
  ): Promise<AISuggestionRecord> {
    return apiRequest<AISuggestionRecord>(
      `${AI_BASE}/${encodeURIComponent(id)}/reject`,
      {
        method: "POST",
        body: JSON.stringify(request),
      }
    );
  },

  async getCaseSummary(caseId: string): Promise<ApprovedCaseSummary> {
    return apiRequest<ApprovedCaseSummary>(
      `${AI_BASE}/cases/${encodeURIComponent(caseId)}/summary`
    );
  },

  async readDocument(
    request: AIDocumentReadRequest
  ): Promise<AIDocumentReadResult> {
    return apiRequest<AIDocumentReadResult>(`${AI_BASE}/document-read`, {
      method: "POST",
      body: JSON.stringify(request),
    });
  },

  async createMessageDraft(
    request: AIMessageDraftRequest
  ): Promise<AIMessageDraftResult> {
    return apiRequest<AIMessageDraftResult>(
      `${AI_BASE}/message-draft`,
      {
        method: "POST",
        body: JSON.stringify(request),
      }
    );
  },
};

export type { CaseSummaryPayload };
